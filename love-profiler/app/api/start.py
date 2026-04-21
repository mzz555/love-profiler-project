"""
Start API — create a new assessment session and return the opening message.
POST /start  →  { session_id: str, message: str, round_num: int }
"""

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.limiter import limiter

logger = logging.getLogger(__name__)

from app.agents.agent1_chat import AGENT1_OPENING_MESSAGE, STATUS_OPTIONS
from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.services.session_store import create_session

router = APIRouter(prefix="/start", tags=["start"])


class StartResponse(BaseModel):
    session_id: str
    assessment_id: int
    message: str
    round_num: int
    options: list[str]


@router.post("", response_model=StartResponse)
@limiter.limit("5/minute")
async def start_assessment(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StartResponse:
    """Create a new session and return Agent 1's opening message."""
    logger.info("[/start] user_id=%s 开始新测评", user_id)
    session = create_session(user_id=str(user_id))

    # Persist a pending assessment record
    assessment = Assessment(
        user_id=user_id,
        session_id=session.session_id,
        signals="{}",
        status="pending",
    )
    db.add(assessment)
    db.commit()

    logger.info("[/start] session_id=%s assessment_id=%s 创建成功", session.session_id, assessment.id)
    return StartResponse(
        session_id=session.session_id,
        assessment_id=assessment.id,
        message=AGENT1_OPENING_MESSAGE,
        round_num=1,
        options=STATUS_OPTIONS,
    )
