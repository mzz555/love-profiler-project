"""
WebSocket chat endpoint — streams LLM tokens to the client in real time.
GET /ws/chat?token=<jwt>

Rounds 1-4: LLM tokens streamed directly as they are generated.
Round 5:    Full reply collected (JSON extraction needed), then clean text
            pushed character-by-character.

Message protocol (server → client JSON):
  {"type": "chunk", "text": "..."}          — one or more characters
  {"type": "done",  "round_num": N, "is_complete": bool}
  {"type": "error", "code": 4xx}
"""

import asyncio
import json
import logging

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.agents.agent1_chat import _BASE_SYSTEM_PROMPT
from app.database import get_db
from app.middleware.auth import TOKEN_ALGORITHM, _jwt_secret
from app.models.assessment import Assessment
from app.services.content_safety import is_safe
from app.services.dimension_bank import get_dimension_for_round
from app.services.json_validator import extract_and_validate
from app.services.llm_client import LLMError, chat_completion, stream_chat_completion
from app.services.round_controller import get_round_directive, is_final_round, is_status_round
from app.services.session_store import (
    SessionData,
    append_message,
    get_session,
    record_dimension,
    set_relationship_status,
    update_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    """Accept a WebSocket connection and stream AI replies token by token."""
    token = websocket.query_params.get("token", "")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[TOKEN_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info("[ws/chat] user_id=%s 连接建立", user_id)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            session_id = data.get("session_id", "")
            message = data.get("message", "")

            if not is_safe(message):
                await websocket.send_text(json.dumps({"type": "error", "code": 422}))
                continue

            session = get_session(session_id)
            if session is None:
                await websocket.send_text(json.dumps({"type": "error", "code": 404}))
                continue

            logger.info("[ws/chat] user_id=%s session=%s round=%s", user_id, session_id[:8], session.round_num)

            try:
                if is_final_round(session.round_num):
                    await _ws_final(websocket, session, message, db)
                else:
                    await _ws_stream(websocket, session, message)
            except LLMError:
                await websocket.send_text(json.dumps({"type": "error", "code": 502}))

    except WebSocketDisconnect:
        logger.info("[ws/chat] user_id=%s 连接断开", user_id)
    except Exception as exc:
        logger.exception("[ws/chat] 未预期错误: %s", exc)


async def _ws_stream(websocket: WebSocket, session: SessionData, message: str) -> None:
    """Rounds 1-4: stream LLM tokens as they arrive."""
    original_round = session.round_num

    if is_status_round(original_round):
        session = set_relationship_status(
            append_message(session, {"role": "user", "content": message}), message
        )
        directive = get_round_directive(round_num=1, status=message, used_questions=list(session.dimension_history))
    else:
        session = append_message(session, {"role": "user", "content": message})
        directive = get_round_directive(
            round_num=original_round,
            status=session.relationship_status or "",
            used_questions=list(session.dimension_history),
        )

    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{directive}"

    full_reply = ""
    async for chunk in stream_chat_completion(system_prompt, session.messages):
        full_reply += chunk
        await websocket.send_text(json.dumps({"type": "chunk", "text": chunk}))

    session = append_message(session, {"role": "assistant", "content": full_reply})

    if is_status_round(original_round):
        new_round = 2
    else:
        new_round = original_round + 1
        dim = get_dimension_for_round(original_round)
        if dim is not None:
            session = record_dimension(session, dim.value)

    updated = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=new_round,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=session.expires_at,
        relationship_status=session.relationship_status,
        dimension_history=session.dimension_history,
    )
    update_session(updated)
    await websocket.send_text(json.dumps({"type": "done", "round_num": new_round, "is_complete": False}))


async def _ws_final(websocket: WebSocket, session: SessionData, message: str, db: Session) -> None:
    """Round 5: collect full reply, extract JSON, stream clean text char by char."""
    session = append_message(session, {"role": "user", "content": message})
    directive = get_round_directive(
        round_num=5,
        status=session.relationship_status or "",
        used_questions=list(session.dimension_history),
    )
    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{directive}"

    raw_reply = await chat_completion(system_prompt, session.messages)
    signals, clean_text = extract_and_validate(raw_reply)

    for char in clean_text:
        await websocket.send_text(json.dumps({"type": "chunk", "text": char}))
        await asyncio.sleep(0.015)

    session = append_message(session, {"role": "assistant", "content": clean_text})
    updated = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=5,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=session.expires_at,
        relationship_status=session.relationship_status,
        dimension_history=session.dimension_history,
    )
    update_session(updated)

    is_complete = signals is not None
    if is_complete:
        assessment = (
            db.query(Assessment)
            .filter(Assessment.session_id == session.session_id)
            .first()
        )
        if assessment:
            assessment.signals = json.dumps(signals, ensure_ascii=False)
            assessment.status = "complete"
            db.commit()
            logger.info("[ws/chat] 5轮完成，信号已写库")
        else:
            logger.error("[ws/chat] session=%s 5轮完成但找不到assessment记录，信号丢失", session.session_id[:8])

    await websocket.send_text(json.dumps({"type": "done", "round_num": 5, "is_complete": is_complete}))
