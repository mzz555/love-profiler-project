"""
Tests for POST /result — personality report generation endpoint.
"""

import json
from unittest.mock import AsyncMock, patch

from app.models.assessment import Assessment
from app.models.user import User


def _make_user_and_token(db_session, openid="o_result_test"):
    from app.middleware.auth import create_access_token

    user = User(openid=openid)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


def _make_complete_assessment(db_session, user_id: int) -> Assessment:
    signals = {
        "attachment_signal": "secure",
        "conflict_signal": "collaborative",
        "need_signal": "connection",
        "boundary_signal": "clear",
        "expression_signal": "direct",
    }
    a = Assessment(
        user_id=user_id,
        session_id="sess-result-test",
        signals=json.dumps(signals),
        status="complete",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


MOCK_REPORT = "你是一个情感稳定、善于沟通的伴侣，属于安全型依恋风格。"


# ---------------------------------------------------------------------------
# Successful report generation
# ---------------------------------------------------------------------------


def test_result_returns_report(client, db_session):
    user, headers = _make_user_and_token(db_session)
    assessment = _make_complete_assessment(db_session, user.id)

    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT),
    ):
        response = client.post(
            "/result",
            json={"session_id": assessment.session_id},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["report_text"] == MOCK_REPORT
    assert data["personality_type"] in ["安全型", "焦虑型", "回避型", "混乱型"]
    assert "summary" in data


def test_result_caches_on_second_call(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_result_cache")
    assessment = _make_complete_assessment(db_session, user.id)
    assessment.session_id = "sess-cache"
    db_session.commit()

    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT),
    ) as mock_llm:
        client.post("/result", json={"session_id": assessment.session_id}, headers=headers)
        client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

    # LLM called only once; second call returns cached result
    assert mock_llm.call_count == 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_result_returns_404_for_unknown_session(client, db_session):
    _, headers = _make_user_and_token(db_session, "o_result_404")

    response = client.post(
        "/result", json={"session_id": "nonexistent"}, headers=headers
    )

    assert response.status_code == 404


def test_result_returns_400_when_assessment_pending(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_result_pending")

    a = Assessment(
        user_id=user.id,
        session_id="sess-pending",
        signals="{}",
        status="pending",
    )
    db_session.add(a)
    db_session.commit()

    response = client.post(
        "/result", json={"session_id": a.session_id}, headers=headers
    )

    assert response.status_code == 400


def test_result_requires_auth(client):
    response = client.post("/result", json={"session_id": "any"})
    assert response.status_code in (401, 403)
