"""
Tests for POST /auth/login — Douyin code2session → JWT flow.
"""

import pytest
import respx
import httpx

from app.api.auth import _CODE2SESSION_URL


FAKE_OPENID = "o_test_12345"
FAKE_CODE = "tt_login_code_abc"


def _mock_code2session_success(openid: str = FAKE_OPENID):
    return httpx.Response(
        200,
        json={"data": {"openid": openid}, "err_no": 0},
    )


# ---------------------------------------------------------------------------
# Successful login — new user
# ---------------------------------------------------------------------------


@respx.mock
def test_login_new_user_returns_token(client):
    respx.post(_CODE2SESSION_URL).mock(return_value=_mock_code2session_success())

    response = client.post("/auth/login", json={"code": FAKE_CODE})

    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert isinstance(data["token"], str)
    assert len(data["token"]) > 20


@respx.mock
def test_login_creates_user_in_db(client, db_session):
    from app.models.user import User

    respx.post(_CODE2SESSION_URL).mock(return_value=_mock_code2session_success())

    client.post("/auth/login", json={"code": FAKE_CODE})

    user = db_session.query(User).filter(User.openid == FAKE_OPENID).first()
    assert user is not None


# ---------------------------------------------------------------------------
# Idempotent — existing user
# ---------------------------------------------------------------------------


@respx.mock
def test_login_existing_user_returns_token(client, db_session):
    from app.models.user import User

    # Pre-create the user
    user = User(openid=FAKE_OPENID)
    db_session.add(user)
    db_session.commit()

    respx.post(_CODE2SESSION_URL).mock(return_value=_mock_code2session_success())

    response = client.post("/auth/login", json={"code": FAKE_CODE})

    assert response.status_code == 200
    assert "token" in response.json()


@respx.mock
def test_login_does_not_duplicate_user(client, db_session):
    from app.models.user import User

    respx.post(_CODE2SESSION_URL).mock(
        side_effect=[
            _mock_code2session_success(),
            _mock_code2session_success(),
        ]
    )

    client.post("/auth/login", json={"code": FAKE_CODE})
    client.post("/auth/login", json={"code": FAKE_CODE})

    count = db_session.query(User).filter(User.openid == FAKE_OPENID).count()
    assert count == 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@respx.mock
def test_login_returns_502_when_douyin_api_fails(client):
    respx.post(_CODE2SESSION_URL).mock(return_value=httpx.Response(500))

    response = client.post("/auth/login", json={"code": FAKE_CODE})

    assert response.status_code == 502


@respx.mock
def test_login_returns_502_when_openid_missing(client):
    respx.post(_CODE2SESSION_URL).mock(
        return_value=httpx.Response(200, json={"data": {}, "err_no": 0})
    )

    response = client.post("/auth/login", json={"code": FAKE_CODE})

    assert response.status_code == 502
