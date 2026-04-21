"""
Unlock API — grant basic report access via incentive video ad.
POST /unlock/ad  { assessment_id: int, ad_token: str }  →  { unlocked: bool }

The Douyin mini-program sends an ad_token after tt.createRewardedVideoAd
completes. We verify it server-side before unlocking.
"""

import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.models.order import Order

router = APIRouter(prefix="/unlock", tags=["unlock"])

AD_VERIFY_SECRET_ENV = "DOUYIN_AD_SECRET"


class AdUnlockRequest(BaseModel):
    assessment_id: int
    ad_token: str


class AdUnlockResponse(BaseModel):
    unlocked: bool


def _verify_ad_token(ad_token: str) -> bool:
    """Verify the ad completion token using HMAC-SHA256.

    Returns True if verification passes or if the secret is not configured
    (development mode).
    """
    secret = os.environ.get(AD_VERIFY_SECRET_ENV, "")
    if not secret:
        return True  # development: skip verification

    expected = hmac.new(secret.encode(), ad_token.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, ad_token)


@router.post("/ad", response_model=AdUnlockResponse)
async def unlock_via_ad(
    body: AdUnlockRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AdUnlockResponse:
    """Unlock the basic report after a verified incentive video ad view."""
    if not _verify_ad_token(body.ad_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ad token verification failed",
        )

    assessment = (
        db.query(Assessment)
        .filter(Assessment.id == body.assessment_id, Assessment.user_id == user_id)
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    # Check if already unlocked (paid order or prior ad unlock)
    existing = (
        db.query(Order)
        .filter(Order.assessment_id == body.assessment_id, Order.user_id == user_id)
        .first()
    )
    if existing:
        return AdUnlockResponse(unlocked=True)

    # Record the ad-based unlock as a zero-amount order
    unlock_record = Order(
        user_id=user_id,
        assessment_id=body.assessment_id,
        out_trade_no=f"AD-{user_id}-{body.assessment_id}",
        amount=0,
        status="paid",
    )
    db.add(unlock_record)
    db.commit()

    return AdUnlockResponse(unlocked=True)
