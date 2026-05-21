"""
Result API — trigger Agent B to generate the personality report.
POST /result         { session_id }  →  polling flow (background task)
POST /result/stream  { session_id }  →  SSE streaming flow

Status flow: pending → analyzed (Agent A) → generating (Agent B launched) → complete (Agent B done)
Repeated calls when complete return cached result immediately.
While generating, returns {status:"generating"} so the frontend can poll.
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.report_writer import ReportWriterError, run as write_report
from app.database import SessionLocal, get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.services import report_writer_runner
from app.services.access_control import is_unlocked
from app.services.llm_client import LLMError
from app.services.token_quota import QuotaExceededError, check_quota

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/result", tags=["result"])

# SSE replay tuning — chunk-level instead of char-level so a 2000-char report
# isn't gated by 2000 × sleep(20ms) = 40s of synthetic latency.
_SSE_CHUNK = 32
_SSE_DELAY = 0.01


class ResultRequest(BaseModel):
    session_id: str


class ResultResponse(BaseModel):
    status: str  # "generating" | "complete"
    personality_type: str = ""
    report_text: str = ""
    report_json: dict = {}
    sections: dict = {}


@router.post("", response_model=ResultResponse)
@limiter.limit("30/minute")
async def get_result(
    request: Request,
    body: ResultRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResultResponse:
    """Trigger or poll Agent B report generation.

    - already complete  → 200 with full report (cached)
    - generating        → 200 {status:"generating"}  (frontend polls again)
    - analyzed          → starts background Agent B, returns {status:"generating"}
    """
    t0 = time.monotonic()
    logger.info("[result] 开始 user_id=%s session=%s", user_id, body.session_id[:8])

    t_db = time.monotonic()
    assessment = (
        db.query(Assessment)
        .filter(
            Assessment.session_id == body.session_id,
            Assessment.user_id == user_id,
        )
        .first()
    )
    logger.info("[result] db_query: %.0fms", (time.monotonic() - t_db) * 1000)

    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz not yet submitted",
        )

    if not is_unlocked(db, assessment.id, user_id):
        logger.warning("[result] user_id=%s 未解锁", user_id)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="报告未解锁，请付费或观看广告后获取。",
        )

    if assessment.status == "complete" and assessment.report_json:
        logger.info(
            "[result] 命中缓存 type=%s total=%.0fms",
            assessment.personality_type, (time.monotonic() - t0) * 1000,
        )
        rj = json.loads(assessment.report_json)
        return ResultResponse(
            status="complete",
            personality_type=assessment.personality_type or "",
            report_text=assessment.report_text or "",
            report_json=rj,
            sections=rj,
        )

    if assessment.status == "generating":
        return ResultResponse(status="generating")

    if not assessment.diagnosis_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diagnosis not available",
        )

    try:
        check_quota(db, user_id=user_id)
    except QuotaExceededError as exc:
        logger.warning("[result] user_id=%s 配额超限 used=%d limit=%d",
                       user_id, exc.used, exc.limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="今日测评次数已达上限，请明天再来",
        ) from exc

    diagnosis = json.loads(assessment.diagnosis_json)
    assessment.status = "generating"
    db.commit()
    logger.info("[result] 启动 agent_b 后台任务 assessment_id=%s", assessment.id)
    report_writer_runner.schedule(
        assessment.id, body.session_id, diagnosis,
        log_prefix="result/bg", user_id=user_id,
    )

    return ResultResponse(status="generating")


# ── SSE streaming endpoint ────────────────────────────────────────────────────

@router.post("/stream")
@limiter.limit("10/minute")
async def stream_result(
    request: Request,
    body: ResultRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE endpoint — runs Agent B then streams report_text character by character.

    Protocol (server → client):
      data: {"type": "chunk", "text": "X"}\\n\\n
      data: {"type": "done",  "personality_type": "MA-CL-MH"}\\n\\n
      data: {"type": "error", "message": "..."}\\n\\n

    Coexists with the polling endpoint; neither replaces the other.
    """
    t0 = time.monotonic()
    logger.info("[result/stream] 开始 user_id=%s session=%s", user_id, body.session_id[:8])

    assessment = (
        db.query(Assessment)
        .filter(
            Assessment.session_id == body.session_id,
            Assessment.user_id == user_id,
        )
        .first()
    )

    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.status == "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz not yet submitted")

    if not is_unlocked(db, assessment.id, user_id):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="报告未解锁")

    # 缓存命中不计配额；只在需要现走 LLM 时预检
    if assessment.status != "complete" or not assessment.report_text:
        try:
            check_quota(db, user_id=user_id)
        except QuotaExceededError as exc:
            logger.warning("[result/stream] user_id=%s 配额超限 used=%d limit=%d",
                           user_id, exc.used, exc.limit)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日测评次数已达上限，请明天再来",
            ) from exc

    # Snapshot all DB data before leaving the request-scoped session
    assessment_id = assessment.id
    session_id_str = body.session_id

    if assessment.status == "complete" and assessment.report_text:
        _report_text_ready: str | None = assessment.report_text
        _personality_type_ready: str = assessment.personality_type or ""
        _diagnosis_data: dict | None = None
    elif assessment.diagnosis_json:
        _report_text_ready = None
        _personality_type_ready = ""
        _diagnosis_data = json.loads(assessment.diagnosis_json)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diagnosis not available")

    logger.info(
        "[result/stream] 准备 %.0fms need_llm=%s",
        (time.monotonic() - t0) * 1000, _report_text_ready is None,
    )

    async def _generate():
        if _report_text_ready is not None:
            text = _report_text_ready
            ptype = _personality_type_ready
        else:
            try:
                text = await write_report(_diagnosis_data, session_id=session_id_str)
            except (ReportWriterError, LLMError) as exc:
                logger.error("[result/stream] agent_b 失败: %s", exc)
                yield f"data: {json.dumps({'type': 'error', 'message': 'Agent B failed'}, ensure_ascii=False)}\n\n"
                return

            ptype = _diagnosis_data.get("type_code", "")

            _db = SessionLocal()
            try:
                rec = _db.query(Assessment).filter(Assessment.id == assessment_id).first()
                if rec and rec.status != "complete":
                    rec.report_json = json.dumps({"raw_llm_output": text}, ensure_ascii=False)
                    rec.personality_type = ptype
                    rec.report_text = text
                    rec.status = "complete"
                    _db.commit()
                    logger.info("[result/stream] 写库完成 type=%s chars=%d", ptype, len(text))
            except Exception as exc:
                logger.warning("[result/stream] 写库失败: %s", exc)
            finally:
                _db.close()

        for i in range(0, len(text), _SSE_CHUNK):
            piece = text[i:i + _SSE_CHUNK]
            yield f"data: {json.dumps({'type': 'chunk', 'text': piece}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(_SSE_DELAY)

        yield f"data: {json.dumps({'type': 'done', 'personality_type': ptype}, ensure_ascii=False)}\n\n"
        logger.info("[result/stream] 完成 type=%s chars=%d", ptype, len(text))

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
