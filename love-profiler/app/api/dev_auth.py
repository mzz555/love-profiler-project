"""
Dev-only login — 仅在 DEV_MODE=true 时可用，生产环境不注册此路由。
POST /auth/dev-login  →  { token: str }

用途：无抖音 AppID/Secret 时，在本地跑通完整业务流程。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import create_access_token
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["dev"])

_DEV_OPENID = "dev_test_user_openid"


class DevLoginResponse(BaseModel):
    token: str
    user_id: int
    note: str


@router.post("/dev-login", response_model=DevLoginResponse)
def dev_login(db: Session = Depends(get_db)) -> DevLoginResponse:
    """开发专用登录，返回固定测试用户的 JWT，无需抖音凭据。"""
    if not settings.dev_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    user = db.query(User).filter(User.openid == _DEV_OPENID).first()
    if user is None:
        user = User(openid=_DEV_OPENID)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    logger.info("[/auth/dev-login] DEV登录成功 user_id=%s", user.id)
    return DevLoginResponse(
        token=token,
        user_id=user.id,
        note="DEV MODE — 此接口仅开发环境可用",
    )
