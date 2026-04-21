"""
Chat API — receive a user message and return Agent 1's reply.
POST /chat  { session_id: str, message: str }
         →  { message: str, round_num: int, is_complete: bool }
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.limiter import limiter

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.agent1_chat import SessionNotFoundError, run_chat_turn
from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.services.content_safety import ContentSafetyError
from app.services.llm_client import LLMError

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    message: str
    round_num: int
    is_complete: bool
    options: list[str] | None = None


@router.post("", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Forward the user message to Agent 1 and return the reply."""
    logger.info("[/chat] session=%s round=%s 消息长度=%s字", body.session_id[:8], "?", len(body.message))
    try:
        reply, updated_session, signals = await run_chat_turn(
            session_id=body.session_id,
            user_message=body.message,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ContentSafetyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="消息包含不安全内容，请重新输入。",
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI服务暂时不可用，请稍后再试。",
        ) from exc

    is_complete = signals is not None
    logger.info("[/chat] session=%s round=%s complete=%s", body.session_id[:8], updated_session.round_num, is_complete)

    if is_complete:
        # Persist extracted signals to the assessment record
        assessment = (
            db.query(Assessment)
            .filter(Assessment.session_id == body.session_id)
            .first()
        )
        if assessment:
            assessment.signals = json.dumps(signals, ensure_ascii=False)
            assessment.status = "complete"
            db.commit()
            logger.info("[/chat] 5轮完成，信号已写库 signals=%s", signals)

    return ChatResponse(
        message=reply,
        round_num=updated_session.round_num,
        is_complete=is_complete,
    )
