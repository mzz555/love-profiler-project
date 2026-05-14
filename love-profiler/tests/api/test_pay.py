"""
Tests for payment endpoints: /pay/create_order, /pay/callback, /pay/query.
"""

import json
import respx
import httpx
import pytest

from app.models.assessment import Assessment
from app.models.order import Order
from app.models.user import User


@pytest.fixture(autouse=True)
def _clear_pay_token(monkeypatch):
    """app.main load_dotenv 会把 .env 里的 DOUYIN_PAY_TOKEN 注入 os.environ；
    测试不带签名头，需要清空 token 让 /pay/callback 走"无签名校验"分支。"""
    monkeypatch.delenv("DOUYIN_PAY_TOKEN", raising=False)


def _make_user_and_token(db_session, openid="o_pay_test"):
    from app.middleware.auth import create_access_token

    user = User(openid=openid)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


def _make_assessment(db_session, user_id: int) -> Assessment:
    a = Assessment(user_id=user_id, session_id="sess-pay", signals="{}", status="complete")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# POST /pay/create_order
# ---------------------------------------------------------------------------


@respx.mock
def test_create_order_returns_out_trade_no(client, db_session):
    from app.api.pay import _CREATE_ORDER_URL

    user, headers = _make_user_and_token(db_session)
    assessment = _make_assessment(db_session, user.id)

    respx.post(_CREATE_ORDER_URL).mock(
        return_value=httpx.Response(200, json={"order": "mock_order_info"})
    )

    response = client.post(
        "/pay/create_order",
        json={"assessment_id": assessment.id},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "out_trade_no" in data
    assert data["out_trade_no"].startswith("LP")


@respx.mock
def test_create_order_persists_to_db(client, db_session):
    from app.api.pay import _CREATE_ORDER_URL

    user, headers = _make_user_and_token(db_session, "o_pay2")
    assessment = _make_assessment(db_session, user.id)

    respx.post(_CREATE_ORDER_URL).mock(
        return_value=httpx.Response(200, json={"order": "mock"})
    )

    response = client.post(
        "/pay/create_order",
        json={"assessment_id": assessment.id},
        headers=headers,
    )

    out_trade_no = response.json()["out_trade_no"]
    order = db_session.query(Order).filter(Order.out_trade_no == out_trade_no).first()
    assert order is not None
    assert order.status == "pending"
    assert order.amount == 990


@respx.mock
def test_create_order_returns_404_for_unknown_assessment(client, db_session):
    from app.api.pay import _CREATE_ORDER_URL

    _, headers = _make_user_and_token(db_session, "o_pay3")

    response = client.post(
        "/pay/create_order",
        json={"assessment_id": 99999},
        headers=headers,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /pay/callback
# ---------------------------------------------------------------------------


def test_callback_marks_order_as_paid(client, db_session):
    user, _ = _make_user_and_token(db_session, "o_cb1")
    assessment = _make_assessment(db_session, user.id)

    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-callback-001",
        amount=990,
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    payload = {"out_trade_no": "trade-callback-001", "status": "PAY_SUCCESS"}
    response = client.post("/pay/callback", content=json.dumps(payload))

    assert response.status_code == 200
    db_session.refresh(order)
    assert order.status == "paid"


def test_callback_ignores_non_success_status(client, db_session):
    user, _ = _make_user_and_token(db_session, "o_cb2")
    assessment = _make_assessment(db_session, user.id)

    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-callback-002",
        amount=990,
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    payload = {"out_trade_no": "trade-callback-002", "status": "PAY_FAIL"}
    client.post("/pay/callback", content=json.dumps(payload))

    db_session.refresh(order)
    assert order.status == "pending"


# ---------------------------------------------------------------------------
# POST /pay/query
# ---------------------------------------------------------------------------


def test_query_returns_order_status(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_q1")
    assessment = _make_assessment(db_session, user.id)

    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-query-001",
        amount=990,
        status="paid",
    )
    db_session.add(order)
    db_session.commit()

    response = client.post(
        "/pay/query",
        json={"out_trade_no": "trade-query-001"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_query_returns_404_for_unknown_order(client, db_session):
    _, headers = _make_user_and_token(db_session, "o_q2")

    response = client.post(
        "/pay/query",
        json={"out_trade_no": "nonexistent-trade"},
        headers=headers,
    )

    assert response.status_code == 404
