"""
Auth API — exchange Douyin code2session result for a JWT.
POST /auth/login  { code: str }  →  { token: str }
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import create_access_token
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

_CODE2SESSION_URL = "https://developer.toutiao.com/api/apps/v2/jscode2session"


class LoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    token: str


async def _code2session(code: str) -> str:
    """Exchange a Douyin login code for an openid.

    Raises:
        HTTPException 502: If the Douyin API call fails or returns an error.
    """
    app_id = settings.douyin_app_id
    app_secret = settings.douyin_app_secret

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                _CODE2SESSION_URL,
                json={"appid": app_id, "secret": app_secret, "code": code},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Douyin API error") from exc

    data = response.json()
    openid = data.get("data", {}).get("openid") or data.get("openid")
    if not openid:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No openid in response: {data}",
        )
    return openid


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Authenticate a Douyin user and return a JWT."""
    openid = await _code2session(body.code)

    user = db.query(User).filter(User.openid == openid).first()
    if user is None:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(token=token)
