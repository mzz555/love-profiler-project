"""user 维度 daily token quota 单元测试（Phase B.1）。

覆盖：
- add_usage 累加幂等
- get_today_total 正确聚合
- check_quota 在默认/超额/边界三种情况下的行为
- DEV_MODE bypass
"""

from datetime import date, timedelta

import pytest

from app.models.user_token_quota import UserTokenQuota
from app.services import token_quota
from app.services.token_quota import (
    QuotaExceededError,
    add_usage,
    check_quota,
    get_today_total,
)


def test_add_usage_creates_row_when_missing(db_session, user_id):
    add_usage(db_session, user_id=user_id, prompt_tokens=100, completion_tokens=200)

    rec = (
        db_session.query(UserTokenQuota)
        .filter_by(user_id=user_id)
        .one()
    )
    assert rec.prompt_tokens == 100
    assert rec.completion_tokens == 200
    assert rec.total_tokens == 300
    assert rec.usage_date == date.today()


def test_add_usage_accumulates_on_same_day(db_session, user_id):
    add_usage(db_session, user_id=user_id, prompt_tokens=100, completion_tokens=200)
    add_usage(db_session, user_id=user_id, prompt_tokens=50, completion_tokens=80)

    rec = (
        db_session.query(UserTokenQuota)
        .filter_by(user_id=user_id, usage_date=date.today())
        .one()
    )
    assert rec.prompt_tokens == 150
    assert rec.completion_tokens == 280
    assert rec.total_tokens == 430


def test_add_usage_zero_is_noop(db_session, user_id):
    """0 token 不应建空行。"""
    add_usage(db_session, user_id=user_id, prompt_tokens=0, completion_tokens=0)
    rec = (
        db_session.query(UserTokenQuota)
        .filter_by(user_id=user_id)
        .one_or_none()
    )
    assert rec is None


def test_get_today_total_returns_zero_when_no_row(db_session, user_id):
    assert get_today_total(db_session, user_id=user_id) == 0


def test_get_today_total_ignores_yesterday(db_session, user_id):
    # 手动插一条昨天的记录
    yesterday = date.today() - timedelta(days=1)
    db_session.add(UserTokenQuota(
        user_id=user_id, usage_date=yesterday,
        prompt_tokens=1000, completion_tokens=2000, total_tokens=3000,
    ))
    db_session.commit()

    add_usage(db_session, user_id=user_id, prompt_tokens=10, completion_tokens=20)
    assert get_today_total(db_session, user_id=user_id) == 30


def test_check_quota_passes_when_under_limit(db_session, user_id, monkeypatch):
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "1000")
    monkeypatch.setenv("DEV_MODE", "false")
    add_usage(db_session, user_id=user_id, prompt_tokens=300, completion_tokens=200)
    check_quota(db_session, user_id=user_id)


def test_check_quota_raises_when_at_or_over_limit(db_session, user_id, monkeypatch):
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "500")
    monkeypatch.setenv("DEV_MODE", "false")
    add_usage(db_session, user_id=user_id, prompt_tokens=300, completion_tokens=250)

    with pytest.raises(QuotaExceededError) as exc_info:
        check_quota(db_session, user_id=user_id)
    assert exc_info.value.used == 550
    assert exc_info.value.limit == 500


def test_check_quota_bypassed_in_dev_mode(db_session, user_id, monkeypatch):
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "10")
    monkeypatch.setenv("DEV_MODE", "true")
    add_usage(db_session, user_id=user_id, prompt_tokens=999, completion_tokens=999)
    # DEV_MODE 下任何用量都通过
    check_quota(db_session, user_id=user_id)


def test_check_quota_default_limit_is_generous(db_session, user_id, monkeypatch):
    """未设置环境变量时，默认 limit 应足以容纳一次正常报告（约 1300 tokens）。"""
    monkeypatch.delenv("USER_DAILY_TOKEN_QUOTA", raising=False)
    monkeypatch.setenv("DEV_MODE", "false")
    add_usage(db_session, user_id=user_id, prompt_tokens=800, completion_tokens=500)
    check_quota(db_session, user_id=user_id)  # 默认 ≥ 1300


def test_quota_exceeded_error_carries_used_and_limit():
    err = QuotaExceededError(used=600, limit=500)
    assert err.used == 600
    assert err.limit == 500
    assert "600" in str(err) and "500" in str(err)
