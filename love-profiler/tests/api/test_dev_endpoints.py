"""Tests for app/api/dev_auth.py 与 app/api/dev_pay.py。

两个 endpoint 都只在 DEV_MODE=true 时注册路由（main.py 加载时一次性
决定），运行时 endpoint 内部又会再检查一次环境变量——所以要分别测：

1. 路由注册（main 加载时 DEV_MODE）：本地 .env 通常 DEV_MODE=true，
   测试集成器加载 main 时已注册，可直接 POST
2. 运行时分支：monkeypatch.setenv("DEV_MODE", "false") 后调用，
   endpoint 内的检查应抛 404
"""

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# /auth/dev-login
# ─────────────────────────────────────────────────────────────────────────────

def _dev_login_registered(client) -> bool:
    """通过预检 OPTIONS 判断路由是否注册；POST 不存在路由时 FastAPI 返回 405。"""
    resp = client.post("/auth/dev-login")
    return resp.status_code != 404 or "Not found" in resp.text


@pytest.fixture
def dev_routes_or_skip(client):
    """conftest 加载 main 时如果 DEV_MODE 未开，路由就没注册——本测试组跳过。"""
    if not _dev_login_registered(client):
        pytest.skip("dev 路由未在 main 启动时注册（DEV_MODE != true）")


def test_dev_login_creates_user_and_returns_token(
    client, db_session, monkeypatch, dev_routes_or_skip,
):
    monkeypatch.setenv("DEV_MODE", "true")

    # 确保没有已存在的 dev user，让 endpoint 走"创建"分支
    from app.models.user import User
    db_session.query(User).filter(User.openid == "dev_test_user_openid").delete()
    db_session.commit()

    resp = client.post("/auth/dev-login")
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["user_id"]
    assert "DEV MODE" in data["note"]


def test_dev_login_reuses_existing_user(
    client, db_session, monkeypatch, dev_routes_or_skip,
):
    """重复调用应复用同一 dev_test_user_openid 用户，不创建新行。"""
    monkeypatch.setenv("DEV_MODE", "true")

    # 第一次调用建立 user（可能复用已存在的）
    resp1 = client.post("/auth/dev-login")
    assert resp1.status_code == 200
    first_user_id = resp1.json()["user_id"]

    # 第二次必须命中同一 user
    resp2 = client.post("/auth/dev-login")
    assert resp2.status_code == 200
    assert resp2.json()["user_id"] == first_user_id

    # DB 里 dev_test_user_openid 只应有一行
    from app.models.user import User
    count = db_session.query(User).filter(User.openid == "dev_test_user_openid").count()
    assert count == 1


def test_dev_login_returns_404_when_dev_mode_off(
    client, monkeypatch, dev_routes_or_skip,
):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.post("/auth/dev-login")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /dev/pay-success
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def dev_pay_or_skip(client):
    """同理：路由未注册则跳过。"""
    resp = client.post("/dev/pay-success?out_trade_no=__probe__")
    # 路由没注册时 FastAPI 返回 404（detail: Not Found）
    if resp.status_code == 404 and "Not Found" in resp.text:
        pytest.skip("dev_pay 路由未在 main 启动时注册（DEV_MODE != true）")


def _make_pending_order(db_session, user_id: int = 1,
                        out_trade_no: str = "test-trade-001") -> int:
    from app.models.order import Order
    o = Order(
        user_id=user_id, assessment_id=1,
        out_trade_no=out_trade_no, amount=99, status="pending",
    )
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o.id


def test_dev_pay_marks_order_paid(client, db_session, monkeypatch, dev_pay_or_skip, auth_headers):
    monkeypatch.setenv("DEV_MODE", "true")
    order_id = _make_pending_order(db_session, out_trade_no="trade-pay-ok")

    resp = client.post("/dev/pay-success?out_trade_no=trade-pay-ok", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paid"
    assert data["out_trade_no"] == "trade-pay-ok"

    # 验证落库
    from app.models.order import Order
    db_session.expire_all()
    o = db_session.query(Order).filter_by(id=order_id).first()
    assert o.status == "paid"


def test_dev_pay_returns_404_when_order_missing(client, monkeypatch, dev_pay_or_skip, auth_headers):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.post("/dev/pay-success?out_trade_no=nonexistent-trade", headers=auth_headers)
    assert resp.status_code == 404


def test_dev_pay_returns_404_when_dev_mode_off(client, monkeypatch, dev_pay_or_skip, auth_headers):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.post("/dev/pay-success?out_trade_no=any", headers=auth_headers)
    assert resp.status_code == 404
