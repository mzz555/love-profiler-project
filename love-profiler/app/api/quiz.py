"""
Quiz API — serve questions from Supabase and submit answers.
POST /quiz/start   →  { session_id, assessment_id, questions: [...] }
POST /quiz/submit  →  { assessment_id, status: "complete" }
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.services.quiz_scorer import compute_scores
from app.services.supabase_client import fetch_questions

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
    answers: list[AnswerItem]


class SubmitResponse(BaseModel):
    assessment_id: int
    status: str


@router.post("/start", response_model=StartResponse)
@limiter.limit("5/minute")
async def quiz_start(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StartResponse:
    """Create a quiz assessment and return all 30 questions."""
    questions = await fetch_questions()
    session_id = str(uuid.uuid4())
    assessment = Assessment(
        user_id=user_id,
        session_id=session_id,
        mode="quiz",
        status="pending",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    logger.info("[/quiz/start] user_id=%s assessment_id=%s", user_id, assessment.id)
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
    """Submit quiz answers, compute scores, mark assessment complete."""
    assessment = (
        db.query(Assessment)
        .filter(Assessment.session_id == body.session_id, Assessment.user_id == user_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    questions = await fetch_questions()
    answers = [a.model_dump() for a in body.answers]
    dimension_scores = compute_scores(answers, questions)

    assessment.dimension_scores = json.dumps(dimension_scores, ensure_ascii=False)
    assessment.status = "complete"
    db.commit()
    logger.info("[/quiz/submit] assessment_id=%s scores=%s", assessment.id, dimension_scores)
    return SubmitResponse(assessment_id=assessment.id, status="complete")
