"""
Result API — trigger Agent 2 to generate the personality report.
POST /result  { session_id: str }
           →  { personality_type: str, report_text: str, summary: str }
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.agent2_analysis import generate_report
from app.limiter import limiter
from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.models.order import Order
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/result", tags=["result"])


class ResultRequest(BaseModel):
    session_id: str


class ResultResponse(BaseModel):
    personality_type: str
    report_text: str
    summary: str


@router.post("", response_model=ResultResponse)
@limiter.limit("10/minute")
async def get_result(
    request: Request,
    body: ResultRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResultResponse:
    """Generate and return the personality analysis report."""
    assessment = (
        db.query(Assessment)
        .filter(
            Assessment.session_id == body.session_id,
            Assessment.user_id == user_id,
        )
        .first()
    )

    logger.info("[/result] user_id=%s session=%s 请求报告", user_id, body.session_id[:8])

    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment is not yet complete",
        )

    # 付费墙守卫：DEV_MODE 下跳过，生产环境必须有已支付订单
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
            logger.warning("[/result] user_id=%s 未解锁，拒绝返回报告", user_id)
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="报告未解锁，请付费或观看广告后获取。",
            )

    # Return cached report if already generated
    if assessment.personality_type and assessment.report_text:
        logger.info("[/result] 命中缓存报告 personality_type=%s", assessment.personality_type)
        cached_summary = assessment.summary or (
            assessment.report_text.split("。")[0] + "。"
            if "。" in assessment.report_text
            else assessment.report_text[:50]
        )
        return ResultResponse(
            personality_type=assessment.personality_type,
            report_text=assessment.report_text,
            summary=cached_summary,
        )

    try:
        signals = json.loads(assessment.signals)
        analysis = await generate_report(signals)
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI服务暂时不可用，请稍后再试。",
        ) from exc

    assessment.personality_type = analysis.personality_type
    assessment.report_text = analysis.report_text
    assessment.summary = analysis.summary
    db.commit()
    logger.info("[/result] 报告生成完成 personality_type=%s", analysis.personality_type)

    return ResultResponse(
        personality_type=analysis.personality_type,
        report_text=analysis.report_text,
        summary=analysis.summary,
    )
