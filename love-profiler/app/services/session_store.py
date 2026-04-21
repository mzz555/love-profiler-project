"""
Session store — file-based session storage with TTL expiry.
Sessions are written as JSON files under SESSIONS_DIR (default: ./sessions/).
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SESSION_TTL_SECONDS: int = 3600
SESSIONS_DIR: Path = Path(os.environ.get("SESSIONS_DIR", "./sessions"))


@dataclass(frozen=True)
class SessionData:
    session_id: str
    user_id: str
    round_num: int
    messages: list[dict]
    created_at: float
    expires_at: float
    relationship_status: str | None = None
    dimension_history: tuple[str, ...] = field(default_factory=tuple)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _write(session: SessionData) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _session_path(session.session_id).write_text(
        json.dumps({
            "session_id": session.session_id,
            "user_id": session.user_id,
            "round_num": session.round_num,
            "messages": session.messages,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "relationship_status": session.relationship_status,
            "dimension_history": list(session.dimension_history),
        }),
        encoding="utf-8",
    )


def _from_dict(data: dict) -> SessionData:
    """Construct SessionData tolerating missing fields from older sessions."""
    return SessionData(
        session_id=data["session_id"],
        user_id=data["user_id"],
        round_num=data["round_num"],
        messages=data["messages"],
        created_at=data["created_at"],
        expires_at=data["expires_at"],
        relationship_status=data.get("relationship_status"),
        dimension_history=tuple(data.get("dimension_history", [])),
    )


def create_session(user_id: str) -> SessionData:
    now = time.time()
    session = SessionData(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        round_num=1,
        messages=[],
        created_at=now,
        expires_at=now + SESSION_TTL_SECONDS,
    )
    _write(session)
    return session


def get_session(session_id: str) -> SessionData | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        session = _from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError):
        return None
    if is_session_expired(session):
        delete_session(session_id)
        return None
    return session


def update_session(session: SessionData) -> None:
    _write(session)


def delete_session(session_id: str) -> None:
    try:
        _session_path(session_id).unlink(missing_ok=True)
    except OSError:
        pass


def is_session_expired(session: SessionData) -> bool:
    return time.time() > session.expires_at


def cleanup_expired_sessions() -> int:
    if not SESSIONS_DIR.exists():
        return 0
    removed = 0
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() > data.get("expires_at", 0):
                path.unlink(missing_ok=True)
                removed += 1
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def append_message(session: SessionData, message: dict) -> SessionData:
    """Return a new SessionData with message appended; original unchanged."""
    return SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=session.round_num,
        messages=[*session.messages, message],
        created_at=session.created_at,
        expires_at=session.expires_at,
        relationship_status=session.relationship_status,
        dimension_history=session.dimension_history,
    )


def set_relationship_status(session: SessionData, status: str) -> SessionData:
    """Return a new SessionData with relationship_status set."""
    return SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=session.round_num,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=session.expires_at,
        relationship_status=status,
        dimension_history=session.dimension_history,
    )


def record_dimension(session: SessionData, dim_name: str) -> SessionData:
    """Return a new SessionData with dim_name appended to dimension_history."""
    return SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=session.round_num,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=session.expires_at,
        relationship_status=session.relationship_status,
        dimension_history=(*session.dimension_history, dim_name),
    )
