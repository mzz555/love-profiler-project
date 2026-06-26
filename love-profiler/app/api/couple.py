"""Couple API — 双人异步配对：create / join / answer / result。"""
import json
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.couple_scoring_engine import CoupleScoringError, run as couple_score_run
from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.couple_session import CoupleSession
from app.services import couple_report_runner
from app.services.couple_answer_package_builder import build_couple_answer_package
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


class AnswerItem(BaseModel):
    question_id: str
    value: float


class AnswerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_id: str
    self_answers: list[AnswerItem] = Field(default_factory=list, alias="self")
    predicted: list[AnswerItem] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


async def _compute_and_launch(db: Session, session_id: str, a_json: str, b_json: str) -> None:
    pkg = build_couple_answer_package(json.loads(a_json), json.loads(b_json))
    try:
        briefing = await couple_score_run(pkg, session_id=session_id)
    except CoupleScoringError as exc:
        db.query(CoupleSession).filter(CoupleSession.session_id == session_id).update(
            {"status": "waiting_partner"}, synchronize_session=False)
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="计算失败") from exc
    db.query(CoupleSession).filter(CoupleSession.session_id == session_id).update(
        {"briefing_json": json.dumps(briefing, ensure_ascii=False), "status": "generating"},
        synchronize_session=False)
    db.commit()
    couple_report_runner.schedule(session_id, briefing)


@router.post("/answer")
@limiter.limit("5/minute")
async def couple_answer(request: Request, body: AnswerRequest,
                        user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.session_id == body.session_id).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="测评不存在")
    raw = {"self": [{"question_id": i.question_id, "value": i.value} for i in body.self_answers],
           "predicted": [{"question_id": i.question_id, "value": i.value} for i in body.predicted],
           "skipped": body.skipped}
    if user_id == sess.initiator_user_id:
        sess.a_answers_json = json.dumps(raw, ensure_ascii=False)
        sess.a_status = "done"
    elif user_id == sess.partner_user_id:
        sess.b_answers_json = json.dumps(raw, ensure_ascii=False)
        sess.b_status = "done"
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权作答该测评")
    db.commit()
    if sess.a_status == "done" and sess.b_status == "done":
        triggered = db.query(CoupleSession).filter(
            CoupleSession.session_id == body.session_id, CoupleSession.status == "waiting_partner"
        ).update({"status": "computing"}, synchronize_session=False)
        db.commit()
        if triggered:
            await _compute_and_launch(db, body.session_id, sess.a_answers_json, sess.b_answers_json)
    db.refresh(sess)
    return {"status": sess.status}


@router.get("/result")
@limiter.limit("30/minute")
async def couple_result(request: Request, session_id: str,
                        user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.session_id == session_id).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="测评不存在")
    if user_id not in (sess.initiator_user_id, sess.partner_user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权查看")
    if sess.status in ("waiting_partner", "computing"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="对方尚未完成作答")
    if sess.status != "complete" or not sess.report_json:
        return {"status": "generating"}
    return {"status": "complete", "report": json.loads(sess.report_json)}
