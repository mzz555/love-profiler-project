"""
Quiz API — serve questions from Supabase and submit answers.
POST /quiz/start   →  { session_id, assessment_id, questions: [...] }
POST /quiz/submit  →  { assessment_id, status: "analyzed", img_path }
"""

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agents.scoring_engine import ScoringError, run as score_run
from app.database import get_db
from app.schemas.diagnosis import Diagnosis
from app.services.llm_client import LLMError
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.services.answer_package_builder import build_answer_package
from app.services.supabase_client import (
    fetch_all_love_types,
    fetch_d4_details,
    fetch_d5_guide,
    fetch_highlights_by_codes,
    fetch_love_type,
    fetch_questions,
    fetch_segment_decode,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quiz", tags=["quiz"])


class StartResponse(BaseModel):
    session_id: str
    assessment_id: int
    questions: list[dict]


class AnswerItem(BaseModel):
    question_id: str
    chosen_option: str


class SubmitRequest(BaseModel):
    session_id: str
    question_set_version: str = "V2"
    answers: list[AnswerItem]


class SubmitResponse(BaseModel):
    assessment_id: int
    status: str
    img_path: str = ""


@router.post("/start", response_model=StartResponse)
@limiter.limit("5/minute")
async def quiz_start(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StartResponse:
    """Create a quiz assessment and return all 30 questions."""
    t0 = time.monotonic()

    t_fetch = time.monotonic()
    questions = await fetch_questions()
    logger.info("[quiz/start] fetch_questions: %d题 %.0fms", len(questions), (time.monotonic() - t_fetch) * 1000)

    session_id = str(uuid.uuid4())
    t_db = time.monotonic()
    assessment = Assessment(
        user_id=user_id,
        session_id=session_id,
        mode="quick",
        status="pending",
        signals="{}",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    logger.info("[quiz/start] db_write: assessment_id=%s %.0fms", assessment.id, (time.monotonic() - t_db) * 1000)

    logger.info(
        "[quiz/start] 完成 user_id=%s assessment_id=%s session=%s total=%.0fms",
        user_id, assessment.id, session_id[:8], (time.monotonic() - t0) * 1000,
    )
    return StartResponse(
        session_id=session_id,
        assessment_id=assessment.id,
        questions=questions,
    )


@router.post("/submit", response_model=SubmitResponse)
@limiter.limit("5/minute")
async def quiz_submit(
    request: Request,
    body: SubmitRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SubmitResponse:
    """Submit quiz answers, run Agent A diagnosis, store results."""
    t0 = time.monotonic()
    logger.info("[quiz/submit] 开始 session=%s answers=%d", body.session_id[:8], len(body.answers))

    assessment = (
        db.query(Assessment)
        .filter(Assessment.session_id == body.session_id, Assessment.user_id == user_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    t_fetch = time.monotonic()
    questions = await fetch_questions()
    logger.info("[quiz/submit] fetch_questions: %.0fms", (time.monotonic() - t_fetch) * 1000)

    t_build = time.monotonic()
    raw_answers = [a.model_dump() for a in body.answers]
    answer_package = build_answer_package(raw_answers, questions)
    answers_json_str = json.dumps(answer_package, ensure_ascii=False)
    logger.info("[quiz/submit] build_answer_package: %.0fms", (time.monotonic() - t_build) * 1000)

    sid_short = body.session_id[:8]
    logger.info(
        "[agent_a/in] session=%s package=%s",
        sid_short, json.dumps(answer_package, ensure_ascii=False),
    )

    t_agent = time.monotonic()
    try:
        diagnosis = await score_run(answer_package, session_id=body.session_id, question_set_version=body.question_set_version)
    except (ScoringError, LLMError) as exc:
        logger.error("[quiz/submit] agent_a 失败 %.0fms: %s", (time.monotonic() - t_agent) * 1000, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Diagnosis service temporarily unavailable",
        ) from exc
    logger.info(
        "[quiz/submit] agent_a 完成 type_code=%s %.0fms",
        diagnosis.get("type_code", "?"), (time.monotonic() - t_agent) * 1000,
    )

    # 从 base_love_type 表查权威 type_name
    type_code = diagnosis.get("type_code", "")
    if not type_code:
        logger.error("[quiz/submit] Agent A 未返回 type_code")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="人格类型识别失败，请重试",
        )

    love_type = await fetch_love_type(type_code)
    if love_type is None:
        logger.error("[quiz/submit] base_love_type 查无 type_code=%s", type_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="人格类型匹配失败，请重试",
        )

    diagnosis["type_name"]    = love_type["type_name"]
    diagnosis["type_tagline"] = love_type.get("tagline", "") or ""
    diagnosis["type_anchor"]  = love_type.get("detail", "") or ""
    diagnosis["img_path"]     = love_type.get("img_path", "") or ""
    logger.info("[quiz/submit] base_love_type 命中 type_code=%s type_name=%s", type_code, love_type["type_name"])

    # 查 D1/D2/D3 段落解码，随 meta 消息下发前端展示人格卡标签
    segment_decode = await fetch_segment_decode(type_code)
    diagnosis["segment_decode"] = segment_decode
    logger.info("[quiz/submit] segment_decode 命中 %d 段", len(segment_decode))

    # 从 base_D4_type 查 top2 爱的语言释义，避免在 system prompt 里硬编码全部 5 类
    d4_block = diagnosis.get("dimensions", {}).get("D4", {}) or {}
    d4_top2 = d4_block.get("top2") or []
    if d4_top2:
        d4_rows = await fetch_d4_details(d4_top2)
        d4_map = {r["code"]: r for r in d4_rows}
        diagnosis["D4_details"] = [d4_map[c] for c in d4_top2 if c in d4_map]
        logger.info("[quiz/submit] base_D4_type 命中 %d/%d", len(diagnosis["D4_details"]), len(d4_top2))

    # 从 base_D5_quadrant 查 9 宫格写作方向，agent_b 不再硬编码字典
    d5_block = diagnosis.get("dimensions", {}).get("D5", {}) or {}
    d5_quadrant = d5_block.get("quadrant", "")
    if d5_quadrant:
        d5_row = await fetch_d5_guide(d5_quadrant)
        if d5_row:
            diagnosis["D5_guide"]      = d5_row["guide"]
            diagnosis["D5_style_name"] = d5_row.get("style_name", "")  # 前端人格卡标签用
            logger.info("[quiz/submit] base_D5_quadrant 命中 quadrant=%s style=%s", d5_quadrant, d5_row.get("style_name", ""))
        else:
            logger.warning("[quiz/submit] base_D5_quadrant 查无 quadrant=%s", d5_quadrant)

    # 从 highlights 表查权威亮点信息
    raw_highlights: list[dict] = diagnosis.get("highlights", [])
    if raw_highlights:
        codes = [h["code"] for h in raw_highlights]
        db_highlights = await fetch_highlights_by_codes(codes)
        hl_map = {h["code"]: h for h in db_highlights}
        enriched: list[dict] = []
        for rh in raw_highlights:
            dbh = hl_map.get(rh["code"])
            if dbh is None:
                logger.error("[quiz/submit] highlights 查无 code=%s", rh["code"])
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="亮点数据匹配失败，请重试",
                )
            enriched.append({
                "code":         dbh["code"],
                "name_cn":      dbh["name_cn"],
                "severity":     dbh["severity"],
                "is_positive":  dbh["is_positive"],
                "report_seed":  dbh["report_seed"],
                "interp_path":  dbh["interp_path"],
                "trigger_condition": dbh["trigger_condition"],
            })
        diagnosis["highlights"] = enriched
        logger.info("[quiz/submit] highlights 命中 %d/%d 条", len(enriched), len(codes))

    logger.info(
        "[agent_a/out] session=%s diagnosis=%s",
        sid_short, json.dumps(diagnosis, ensure_ascii=False),
    )

    try:
        Diagnosis.model_validate(diagnosis)
    except ValidationError as exc:
        logger.error(
            "[quiz/submit] diagnosis schema 校验失败 session=%s errors=%s",
            sid_short, exc.errors(),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="诊断数据不完整，请重试",
        ) from exc

    t_db = time.monotonic()
    assessment.answers_json = answers_json_str
    assessment.diagnosis_json = json.dumps(diagnosis, ensure_ascii=False)
    assessment.status = "analyzed"
    db.commit()
    logger.info("[quiz/submit] db_write: %.0fms", (time.monotonic() - t_db) * 1000)

    # Agent B is launched lazily by /ws/result (or /result polling), not here —
    # avoids the double-run that happens when both quiz/submit and the WS endpoint
    # would each kick off Agent B for the same assessment.
    logger.info(
        "[quiz/submit] 完成 assessment_id=%s type_code=%s total=%.0fms",
        assessment.id, diagnosis.get("type_code", "?"), (time.monotonic() - t0) * 1000,
    )
    img_path = love_type.get("img_path", "") or ""
    return SubmitResponse(assessment_id=assessment.id, status="analyzed", img_path=img_path)


@router.get("/types")
async def list_types(_uid: int = Depends(get_current_user_id)) -> dict:
    """返回 16 类恋爱人格的展示字段（按 id ASC），供首页轮播 portrait 使用。

    img_path 与现有 chat→loading→report 链路保持一致：单字符串字段，
    内容形如 "man路径,woman路径"，客户端按性别 split 取段。
    """
    rows = await fetch_all_love_types()
    types = [
        {
            "id": r["id"],
            "type_code": r["type_code"],
            "type_name": r["type_name"],
            "img_path": r.get("img_path") or "",
        }
        for r in rows
    ]
    return {"types": types}
