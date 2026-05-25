"""Tests for app/api/unlock.py.

覆盖 unlock_via_ad endpoint 与 _verify_ad_token：
- endpoint: 成功首次解锁 / 幂等重复解锁 / 404 不存在 / ad_token 校验失败
- _verify_ad_token: 无 secret 直放 / 有 secret 时占位实现行为
"""

import hashlib
import hmac
import json

import pytest

from app.api.unlock import _verify_ad_token


def _auth_token(user_id: int) -> str:
    """跟 test_ws_result.py 保持一致：直接基于 user_id 造 token，
    避免 conftest 里 auth_headers (o_test_user) 与 user_id (o_test_user_id)
    fixture 创建两个不同用户造成的 ID 错位。"""
    from app.middleware.auth import create_access_token
    return create_access_token(user_id)


def _headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {_auth_token(user_id)}"}


# ─────────────────────────────────────────────────────────────────────────────
# _verify_ad_token 单测
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_ad_token_dev_mode_passes(monkeypatch):
    """DEV_MODE=true 时无论密钥和签名如何都放行。"""
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.delenv("DOUYIN_AD_SECRET", raising=False)
    assert _verify_ad_token("any-token", "") is True


def test_verify_ad_token_no_secret_rejects_in_prod(monkeypatch):
    """生产环境（非 DEV_MODE）缺密钥 → fail-closed 拒绝。"""
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.delenv("DOUYIN_AD_SECRET", raising=False)
    assert _verify_ad_token("any-token", "any-sig") is False


def test_verify_ad_token_empty_signature_rejects(monkeypatch):
    """有密钥但签名为空 → 拒绝。"""
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("DOUYIN_AD_SECRET", "test-secret")
    assert _verify_ad_token("token", "") is False


def test_verify_ad_token_wrong_signature_rejects(monkeypatch):
    """有密钥、签名不匹配 → 拒绝。"""
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("DOUYIN_AD_SECRET", "test-secret")
    assert _verify_ad_token("token", "wrong-sig") is False


def test_verify_ad_token_correct_signature_passes(monkeypatch):
    """有密钥、签名正确 → 通过。"""
    secret = "test-secret"
    token = "my-trans-id"
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("DOUYIN_AD_SECRET", secret)
    correct_sig = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
    assert _verify_ad_token(token, correct_sig) is True


# ─────────────────────────────────────────────────────────────────────────────
# unlock_via_ad endpoint
# ─────────────────────────────────────────────────────────────────────────────

def _make_assessment(db_session, user_id: int, *, session_id: str = "unlock-test",
                    status: str = "analyzed"):
    from app.models.assessment import Assessment
    a = Assessment(
        user_id=user_id,
        session_id=session_id,
        status=status,
        answers_json="[]",
        diagnosis_json="{}",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_unlock_creates_paid_order_first_time(client, db_session, user_id):
    a = _make_assessment(db_session, user_id)
    resp = client.post(
        "/unlock/ad",
        json={"assessment_id": a.id, "ad_token": "tok"},
        headers=_headers(user_id),
    )
    assert resp.status_code == 200
    assert resp.json()["unlocked"] is True

    # 验证落库：零金额 + status=paid + out_trade_no 形如 AD-{user}-{assess}
    from app.models.order import Order
    orders = db_session.query(Order).filter_by(assessment_id=a.id).all()
    assert len(orders) == 1
    o = orders[0]
    assert o.amount == 0
    assert o.status == "paid"
    assert o.out_trade_no == f"AD-{user_id}-{a.id}"


def test_unlock_is_idempotent_when_order_exists(client, db_session, user_id):
    """已有 order（无论 paid 还是 pending）应直接返回 unlocked=True，不重复建单。"""
    a = _make_assessment(db_session, user_id)
    # 预先建一个 order
    from app.models.order import Order
    pre = Order(
        user_id=user_id, assessment_id=a.id,
        out_trade_no="PRE-EXISTING", amount=1, status="paid",
    )
    db_session.add(pre)
    db_session.commit()

    resp = client.post(
        "/unlock/ad",
        json={"assessment_id": a.id, "ad_token": "tok"},
        headers=_headers(user_id),
    )
    assert resp.status_code == 200
    assert resp.json()["unlocked"] is True

    # 不应有新增 order，仍只有 1 条
    orders = db_session.query(Order).filter_by(assessment_id=a.id).all()
    assert len(orders) == 1
    assert orders[0].out_trade_no == "PRE-EXISTING"


def test_unlock_returns_404_when_assessment_not_found(client, user_id):
    resp = client.post(
        "/unlock/ad",
        json={"assessment_id": 999999, "ad_token": "tok"},
        headers=_headers(user_id),
    )
    assert resp.status_code == 404


def test_unlock_returns_400_when_ad_token_verification_fails(
    client, db_session, user_id, monkeypatch,
):
    """配置了 DOUYIN_AD_SECRET 且非 DEV_MODE 时，错误签名被拒绝。"""
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("DOUYIN_AD_SECRET", "prod-secret")
    a = _make_assessment(db_session, user_id)

    resp = client.post(
        "/unlock/ad",
        json={"assessment_id": a.id, "ad_token": "anything", "signature": "wrong"},
        headers=_headers(user_id),
    )
    assert resp.status_code == 400

    # 失败时不应建单
    from app.models.order import Order
    assert db_session.query(Order).filter_by(assessment_id=a.id).count() == 0


def test_unlock_does_not_leak_other_users_assessment(client, db_session, user_id):
    """用户 A 不能解锁用户 B 的 assessment。"""
    from app.models.user import User
    other = User(openid="o_other_user")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    a_other = _make_assessment(db_session, other.id, session_id="other-sess")
    # 用 user_id（默认登陆用户）去解锁 other 的 assessment
    resp = client.post(
        "/unlock/ad",
        json={"assessment_id": a_other.id, "ad_token": "tok"},
        headers=_headers(user_id),
    )
    assert resp.status_code == 404
