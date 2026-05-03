"""
Result API — trigger Agent B to generate the personality report.
POST /result  { session_id: str }
           →  { status: "generating"|"complete", personality_type, report_text, report_json }

Status flow: pending → analyzed (Agent A) → generating (Agent B launched) → complete (Agent B done)
Repeated calls when complete return cached result immediately.
While generating, returns {status:"generating"} so the frontend can poll.
"""

import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.agent_b import AgentBError, run as agent_b_run
from app.database import SessionLocal, get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.models.order import Order
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/result", tags=["result"])


class ResultRequest(BaseModel):
    session_id: str


class ResultResponse(BaseModel):
    status: str  # "generating" | "complete"
    personality_type: str = ""
    report_text: str = ""
    report_json: dict = {}


async def _run_agent_b_background(assessment_id: int, session_id: str, diagnosis: dict) -> None:
    """Run Agent B and persist the report; resets status to 'analyzed' on failure so the next poll retries."""
    t0 = time.monotonic()
    db = SessionLocal()
    try:
        report = await agent_b_run(diagnosis, session_id=session_id)
        personality_type = (diagnosis.get("personality_typing", {}) or {}).get("type_code", "")
        report_text = report.get("report_text", "")

        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if assessment and assessment.status == "generating":
            assessment.report_json = json.dumps(report, ensure_ascii=False)
            assessment.personality_type = personality_type
            assessment.report_text = report_text
            assessment.status = "complete"
            db.commit()
        logger.info(
            "[result/bg] 完成 assessment_id=%s type=%s %.0fms",
            assessment_id, personality_type, (time.monotonic() - t0) * 1000,
        )
    except (AgentBError, LLMError) as exc:
        logger.error(
            "[result/bg] agent_b 失败 assessment_id=%s %.0fms: %s",
            assessment_id, (time.monotonic() - t0) * 1000, exc,
        )
        # Reset so the next frontend poll triggers a fresh attempt
        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if assessment and assessment.status == "generating":
            assessment.status = "analyzed"
            db.commit()
    finally:
        db.close()


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

    # Payment wall: skip in DEV_MODE, require paid order in production
    if os.environ.get("DEV_MODE", "").lower() != "true":
        paid_order = (
            db.query(Order)
            .filter(
                Order.assessment_id == assessment.id,
                Order.user_id == user_id,
                Order.status == "paid",
            )
            .first()
        )
        if paid_order is None:
            logger.warning("[result] user_id=%s 未解锁", user_id)
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="报告未解锁，请付费或观看广告后获取。",
            )

    # Return cached report if already complete
    if assessment.status == "complete" and assessment.report_json:
        logger.info(
            "[result] 命中缓存 type=%s total=%.0fms",
            assessment.personality_type, (time.monotonic() - t0) * 1000,
        )
        return ResultResponse(
            status="complete",
            personality_type=assessment.personality_type or "",
            report_text=assessment.report_text or "",
            report_json=json.loads(assessment.report_json),
        )

    # Agent B already running in background — client should poll
    if assessment.status == "generating":
        return ResultResponse(status="generating")

    # Launch Agent B as a background task (analyzed → generating)
    if not assessment.diagnosis_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diagnosis not available",
        )

    diagnosis = json.loads(assessment.diagnosis_json)
    assessment.status = "generating"
    db.commit()
    logger.info("[result] 启动 agent_b 后台任务 assessment_id=%s", assessment.id)
    asyncio.create_task(
        _run_agent_b_background(assessment.id, body.session_id, diagnosis)
    )

    return ResultResponse(status="generating")
