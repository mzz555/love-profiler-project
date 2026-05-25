"""
Unlock API — grant basic report access via incentive video ad.
POST /unlock/ad  { assessment_id, ad_token, signature }  →  { unlocked }

前端在激励视频 onClose(isEnded=true) 后取 transId 作为 ad_token，
用本地密钥签名后传 signature。后端用 DOUYIN_AD_SECRET 验签。
DEV_MODE 时允许绕过验签（开发体验），生产环境缺密钥直接拒绝。
TODO: 长期应改为抖音服务端到服务端回调验证，彻底消除客户端伪造可能。
"""

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.limiter import limiter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment
from app.models.order import Order

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/unlock", tags=["unlock"])

AD_VERIFY_SECRET_ENV = "DOUYIN_AD_SECRET"


class AdUnlockRequest(BaseModel):
    assessment_id: int
    ad_token: str
    signature: str = ""


class AdUnlockResponse(BaseModel):
    unlocked: bool


def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() == "true"


def _verify_ad_token(ad_token: str, signature: str) -> bool:
    """HMAC-SHA256 验签：hmac(secret, ad_token) == signature。

    - DEV_MODE=true 时跳过验签（开发绕过）
    - 生产环境缺 DOUYIN_AD_SECRET → 拒绝（fail-closed）
    - signature 为空 → 拒绝
    """
    if _is_dev_mode():
        return True

    secret = os.environ.get(AD_VERIFY_SECRET_ENV, "")
    if not secret:
        logger.error("[unlock] DOUYIN_AD_SECRET 未配置，拒绝解锁请求（fail-closed）")
        return False

    if not signature:
        return False

    expected = hmac.new(secret.encode(), ad_token.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/ad", response_model=AdUnlockResponse)
@limiter.limit("5/minute")
async def unlock_via_ad(
    request: Request,
    body: AdUnlockRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AdUnlockResponse:
    """Unlock the basic report after a verified incentive video ad view."""
    if not _verify_ad_token(body.ad_token, body.signature):
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
