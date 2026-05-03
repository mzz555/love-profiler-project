"""
Tests for GET /history and _extract_type_name helper.
"""

import pytest

from app.api.history import _extract_type_name
from app.models.assessment import Assessment
from app.models.user import User


# ── 纯函数测试 ────────────────────────────────────────────────────────────────

def test_extract_type_name_chinese_corner_bracket():
    assert _extract_type_name('你是「矛盾守护者」，在感情中') == '矛盾守护者'

def test_extract_type_name_white_corner_bracket():
    assert _extract_type_name('你是『安稳探索者』，拥有') == '安稳探索者'

def test_extract_type_name_curly_quotes():
    assert _extract_type_name('你是“细腻感知者”，') == '细腻感知者'

def test_extract_type_name_none_input():
    assert _extract_type_name(None) == ''

def test_extract_type_name_empty_string():
    assert _extract_type_name('') == ''

def test_extract_type_name_no_match():
    assert _extract_type_name('这是一段没有类型名的普通文字') == ''


# ── 端点集成测试 ──────────────────────────────────────────────────────────────

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
    assessment = Assessment(
        user_id=user.id,
        session_id="sess-hist-1",
        signals="{}",
        status="complete",
        personality_type="MA-CL-MH",
        report_text='你是「矛盾守护者」，在感情中展现出矛盾性。',
    )
    db_session.add(assessment)
    db_session.commit()

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["type_name"] == "矛盾守护者"
    assert items[0]["personality_type"] == "MA-CL-MH"


def test_history_type_name_empty_when_report_text_missing(client, db_session):
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
    db_session.add(Assessment(
        user_id=user.id, session_id="sess-complete",
        signals="{}", status="complete",
        personality_type="S-BL-HP",
        report_text='你是「稳定者」。',
    ))
    db_session.commit()

    response = client.get("/history", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["session_id"] == "sess-complete"


def test_history_requires_auth(client):
    response = client.get("/history")
    assert response.status_code in (401, 403)
