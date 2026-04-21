"""
Tests for POST /chat — single-turn dialogue endpoint.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.assessment import Assessment
from app.models.user import User


def _make_assessment(db_session, user_id: int, session_id: str = "sess-test") -> Assessment:
    a = Assessment(user_id=user_id, session_id=session_id, signals="{}", status="pending")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _make_user_and_token(db_session):
    from app.middleware.auth import create_access_token

    user = User(openid="o_chat_test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Normal turn
# ---------------------------------------------------------------------------


def test_chat_returns_reply(client, db_session):
    user, headers = _make_user_and_token(db_session)
    from app.services.session_store import create_session

    session = create_session(user_id=str(user.id))
    _make_assessment(db_session, user.id, session.session_id)

    with patch(
        "app.agents.agent1_chat.chat_completion",
        new=AsyncMock(return_value="你好！让我来了解你。"),
    ):
        response = client.post(
            "/chat",
            json={"session_id": session.session_id, "message": "嗨"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "你好！让我来了解你。"
    assert data["round_num"] >= 1
    assert data["is_complete"] is False


def test_chat_increments_round_num(client, db_session):
    user, headers = _make_user_and_token(db_session)
    from app.services.session_store import create_session

    session = create_session(user_id=str(user.id))
    _make_assessment(db_session, user.id, session.session_id)

    with patch(
        "app.agents.agent1_chat.chat_completion",
        new=AsyncMock(return_value="回复"),
    ):
        r1 = client.post("/chat", json={"session_id": session.session_id, "message": "hi"}, headers=headers)
        r2 = client.post("/chat", json={"session_id": session.session_id, "message": "hi2"}, headers=headers)

    assert r2.json()["round_num"] > r1.json()["round_num"]


# ---------------------------------------------------------------------------
# Session not found
# ---------------------------------------------------------------------------


def test_chat_returns_404_for_unknown_session(client, db_session):
    _, headers = _make_user_and_token(db_session)

    response = client.post(
        "/chat",
        json={"session_id": "nonexistent-session", "message": "hi"},
        headers=headers,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------


def test_chat_returns_422_for_unsafe_input(client, db_session):
    user, headers = _make_user_and_token(db_session)
    from app.services.session_store import create_session

    session = create_session(user_id=str(user.id))
    _make_assessment(db_session, user.id, session.session_id)

    response = client.post(
        "/chat",
        json={"session_id": session.session_id, "message": "我想自杀"},
        headers=headers,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


def test_chat_returns_403_without_token(client):
    response = client.post("/chat", json={"session_id": "any", "message": "hi"})
    assert response.status_code in (401, 403)
