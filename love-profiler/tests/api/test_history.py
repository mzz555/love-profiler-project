"""
Tests for GET /history and _extract_type_name helper.
"""

import json

import pytest

from app.api.history import _extract_type_name
from app.models.assessment import Assessment
from app.models.user import User


# ── mock Assessment for unit tests ───────────────────────────────────────────

class _FakeAssessment:
    def __init__(self, diagnosis_json=None):
        self.diagnosis_json = diagnosis_json


# ── _extract_type_name unit tests ────────────────────────────────────────────

def test_extract_type_name_from_diagnosis_json():
    diag = json.dumps({"type_name": "矛盾守护者"})
    assert _extract_type_name(_FakeAssessment(diag)) == "矛盾守护者"


def test_extract_type_name_empty_when_no_type_name():
    diag = json.dumps({"type_code": "MA-CL-MH"})
    assert _extract_type_name(_FakeAssessment(diag)) == ""


def test_extract_type_name_empty_when_diagnosis_none():
    assert _extract_type_name(_FakeAssessment(None)) == ""


def test_extract_type_name_empty_when_invalid_json():
    assert _extract_type_name(_FakeAssessment("not json")) == ""


# ── endpoint integration tests ───────────────────────────────────────────────

def _make_user_and_headers(db_session, openid="o_history_test"):
    from app.middleware.auth import create_access_token
    user = User(openid=openid)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


def test_history_returns_type_name(client, db_session):
    user, headers = _make_user_and_headers(db_session)
    diag = json.dumps({"type_name": "矛盾守护者", "type_code": "MA-CL-MH"})
    assessment = Assessment(
        user_id=user.id,
        session_id="sess-hist-1",
        signals="{}",
        status="complete",
        personality_type="MA-CL-MH",
        diagnosis_json=diag,
        report_text="你是矛盾守护者，在感情中展现出矛盾性。",
    )
    db_session.add(assessment)
    db_session.commit()

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["type_name"] == "矛盾守护者"
    assert items[0]["personality_type"] == "MA-CL-MH"


def test_history_type_name_empty_when_no_diagnosis(client, db_session):
    user, headers = _make_user_and_headers(db_session, "o_history_empty")
    assessment = Assessment(
        user_id=user.id,
        session_id="sess-hist-2",
        signals="{}",
        status="complete",
        personality_type="S-BL-HP",
        report_text=None,
    )
    db_session.add(assessment)
    db_session.commit()

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert items[0]["type_name"] == ""


def test_history_only_returns_complete_assessments(client, db_session):
    user, headers = _make_user_and_headers(db_session, "o_history_status")
    db_session.add(Assessment(
        user_id=user.id, session_id="sess-pending",
        signals="{}", status="pending",
    ))
    diag = json.dumps({"type_name": "稳定者"})
    db_session.add(Assessment(
        user_id=user.id, session_id="sess-complete",
        signals="{}", status="complete",
        personality_type="S-BL-HP",
        diagnosis_json=diag,
        report_text="你是稳定者。",
    ))
    db_session.commit()

    response = client.get("/history", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["session_id"] == "sess-complete"


def test_history_requires_auth(client):
    response = client.get("/history")
    assert response.status_code in (401, 403)
