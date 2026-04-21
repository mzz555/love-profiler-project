"""
JWT auth middleware — validates Bearer tokens on protected routes.
"""

import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=True)

TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def create_access_token(user_id: int) -> str:
    """Encode a JWT for the given user_id."""
    import time

    payload = {
        "sub": str(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=TOKEN_ALGORITHM)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> int:
    """FastAPI dependency — decode JWT and return the user_id (int).

    Raises:
        HTTPException 401: If the token is missing, invalid, or expired.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[TOKEN_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
