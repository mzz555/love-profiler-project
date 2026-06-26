"""Couple API — 双人异步配对：create / join / answer / result。"""
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.couple_session import CoupleSession
from app.services.supabase_client import fetch_couple_questions

router = APIRouter(prefix="/couple", tags=["couple"])


class JoinRequest(BaseModel):
    pairing_token: str


@router.post("/create")
@limiter.limit("5/minute")
async def couple_create(request: Request, user_id: int = Depends(get_current_user_id),
                        db: Session = Depends(get_db)) -> dict:
    sess = CoupleSession(session_id=str(uuid.uuid4()), pairing_token=secrets.token_urlsafe(24),
                         initiator_user_id=user_id, status="waiting_partner",
                         a_status="pending", b_status="pending")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return {"session_id": sess.session_id, "pairing_token": sess.pairing_token,
            "questions": await fetch_couple_questions()}


@router.post("/join")
@limiter.limit("10/minute")
async def couple_join(request: Request, body: JoinRequest,
                      user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.pairing_token == body.pairing_token).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="邀请无效")
    if sess.initiator_user_id == user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="不能和自己配对")
    if sess.partner_user_id is not None and sess.partner_user_id != user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该测评已有搭档")
    sess.partner_user_id = user_id
    db.commit()
    return {"session_id": sess.session_id, "questions": await fetch_couple_questions()}
