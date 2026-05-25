"""
History API -- return the authenticated user's completed assessments.
GET /history  ->  list[HistoryItem]
"""

import json
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


def _extract_type_name(assessment: "Assessment") -> str:
    if assessment.diagnosis_json:
        try:
            diag = json.loads(assessment.diagnosis_json)
            name = diag.get("type_name", "")
            if name:
                return name
        except (json.JSONDecodeError, TypeError):
            pass
    return ""


class HistoryItem(BaseModel):
    id: int
    session_id: str
    personality_type: str
    type_name: str
    summary: str
    created_at: str


@router.get("", response_model=list[HistoryItem])
@limiter.limit("20/minute")
async def get_history(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    """Return the last 20 completed assessments for the authenticated user."""
    assessments = (
        db.query(Assessment)
        .filter(Assessment.user_id == user_id, Assessment.status == "complete")
        .order_by(Assessment.created_at.desc())
        .limit(20)
        .all()
    )
    logger.info("[/history] user_id=%s count=%d", user_id, len(assessments))
    return [
        HistoryItem(
            id=a.id,
            session_id=a.session_id,
            personality_type=a.personality_type or "",
            type_name=_extract_type_name(a),
            summary=a.summary or (
                a.report_text.split("。")[0] + "。"
                if a.report_text and "。" in a.report_text
                else (a.report_text or "")[:50]
            ),
            created_at=a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        )
        for a in assessments
    ]
