"""Phase D.1 admin 指标聚合服务单元测试。"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.ai_call_log import AiCallLog
from app.models.assessment import Assessment
from app.models.order import Order
from app.models.report_quality_audit import ReportQualityAudit
from app.models.user import User
from app.models.user_token_quota import UserTokenQuota
from app.services.admin_metrics import (
    _percentile,
    compute_assessment_funnel,
    compute_business_metrics,
    compute_daily_orders,
    compute_daily_users,
    compute_duration_percentiles,
    compute_hourly_trend,
    compute_llm_metrics,
    compute_personality_distribution,
    compute_quality_score_distribution,
    compute_status_breakdown,
    compute_top_users_by_tokens,
)


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------

def test_percentile_empty():
    assert _percentile([], 0.5) == 0


def test_percentile_single_value():
    assert _percentile([42], 0.95) == 42


def test_percentile_p50_of_odd():
    assert _percentile([10, 20, 30], 0.5) == 20


def test_percentile_p50_of_even_uses_interpolation():
    assert _percentile([10, 20, 30, 40], 0.5) == 25


def test_percentile_p95():
    data = sorted(range(1, 101))
    p95 = _percentile(data, 0.95)
    assert 95 <= p95 <= 96


# ---------------------------------------------------------------------------
# compute_duration_percentiles
# ---------------------------------------------------------------------------

def _add_log(db, *, duration_ms: int, status: str = "success",
             ts: datetime | None = None, agent: str = "agent_b",
             total_tokens: int = 0, user_id: int | None = None):
    if ts is None:
        ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    log = AiCallLog(
        ts=ts, agent=agent, status=status, model="doubao-test",
        temperature=0.6, retry_index=0, duration_ms=duration_ms,
        prompt_tokens=0, completion_tokens=0, total_tokens=total_tokens,
        system_prompt_len=0, response_len=0,
        user_id=user_id,
    )
    db.add(log)
    db.commit()
    return log


def test_duration_percentiles_empty_returns_zeros(db_session):
    out = compute_duration_percentiles(db_session)
    assert out == {"count": 0, "p50": 0, "p95": 0, "p99": 0, "avg": 0, "max": 0}


def test_duration_percentiles_ignores_errors(db_session):
    """error 状态的调用不计入分位数。"""
    for d in (100, 200, 300):
        _add_log(db_session, duration_ms=d, status="success")
    _add_log(db_session, duration_ms=99999, status="error")

    out = compute_duration_percentiles(db_session)
    assert out["count"] == 3
    assert out["max"] == 300


def test_duration_percentiles_window_filter(db_session):
    """超过 window 的旧记录不计。"""
    _add_log(db_session, duration_ms=500, ts=datetime.now(timezone.utc) - timedelta(hours=48))
    _add_log(db_session, duration_ms=100, ts=datetime.now(timezone.utc) - timedelta(hours=2))
    out = compute_duration_percentiles(db_session, hours=24)
    assert out["count"] == 1
    assert out["max"] == 100


# ---------------------------------------------------------------------------
# compute_hourly_trend
# ---------------------------------------------------------------------------

def test_hourly_trend_returns_window_buckets_even_when_empty(db_session):
    buckets = compute_hourly_trend(db_session, hours=6)
    assert len(buckets) == 6
    assert all(b["total"] == 0 for b in buckets)


def test_hourly_trend_aggregates_into_correct_bucket(db_session):
    """now 已 floor 到整点；落 +15min 进入 now 桶，落 -65min 进入 (now-1h) 桶。"""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _add_log(db_session, duration_ms=100, ts=now + timedelta(minutes=15), total_tokens=50)
    _add_log(db_session, duration_ms=200, ts=now + timedelta(minutes=25), total_tokens=80)
    _add_log(db_session, duration_ms=300, ts=now - timedelta(hours=1, minutes=5),
             status="error", total_tokens=0)

    buckets = compute_hourly_trend(db_session, hours=4)
    by_hour = {b["hour"]: b for b in buckets}

    current = by_hour[now.isoformat()]
    assert current["total"] == 2
    assert current["success"] == 2
    assert current["total_tokens"] == 130

    err_bucket = by_hour[(now - timedelta(hours=2)).isoformat()]
    assert err_bucket["total"] == 1
    assert err_bucket["error"] == 1


# ---------------------------------------------------------------------------
# compute_top_users_by_tokens
# ---------------------------------------------------------------------------

def _add_user(db, *, openid: str = "o_test"):
    u = User(openid=openid)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_top_users_empty_returns_empty_list(db_session):
    assert compute_top_users_by_tokens(db_session) == []


def test_top_users_orders_by_total_tokens_desc(db_session):
    u1 = _add_user(db_session, openid="o_user_one")
    u2 = _add_user(db_session, openid="o_user_two")
    u3 = _add_user(db_session, openid="o_user_three")
    today = date.today()
    db_session.add_all([
        UserTokenQuota(user_id=u1.id, usage_date=today, prompt_tokens=100, completion_tokens=200, total_tokens=300),
        UserTokenQuota(user_id=u2.id, usage_date=today, prompt_tokens=1000, completion_tokens=2000, total_tokens=3000),
        UserTokenQuota(user_id=u3.id, usage_date=today, prompt_tokens=50, completion_tokens=50, total_tokens=100),
    ])
    db_session.commit()

    out = compute_top_users_by_tokens(db_session)
    assert [r["user_id"] for r in out] == [u2.id, u1.id, u3.id]
    assert out[0]["total_tokens"] == 3000


def test_top_users_masks_long_openid(db_session):
    long_openid = "o_" + "x" * 40
    u = _add_user(db_session, openid=long_openid)
    db_session.add(UserTokenQuota(
        user_id=u.id, usage_date=date.today(),
        prompt_tokens=10, completion_tokens=10, total_tokens=20,
    ))
    db_session.commit()

    out = compute_top_users_by_tokens(db_session)
    assert out[0]["openid_masked"].endswith("…")
    assert len(out[0]["openid_masked"]) <= 13


def test_top_users_only_counts_today(db_session):
    u = _add_user(db_session, openid="o_yesterday")
    yesterday = date.today() - timedelta(days=1)
    db_session.add(UserTokenQuota(
        user_id=u.id, usage_date=yesterday,
        prompt_tokens=999, completion_tokens=999, total_tokens=1998,
    ))
    db_session.commit()

    assert compute_top_users_by_tokens(db_session) == []


def test_top_users_respects_limit(db_session):
    for i in range(5):
        u = _add_user(db_session, openid=f"o_u{i}")
        db_session.add(UserTokenQuota(
            user_id=u.id, usage_date=date.today(),
            prompt_tokens=0, completion_tokens=0, total_tokens=i * 10,
        ))
    db_session.commit()
    out = compute_top_users_by_tokens(db_session, limit=2)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# compute_status_breakdown
# ---------------------------------------------------------------------------

def test_status_breakdown_groups_by_agent_and_calculates_error_rate(db_session):
    _add_log(db_session, duration_ms=10, agent="agent_b", status="success")
    _add_log(db_session, duration_ms=10, agent="agent_b", status="success")
    _add_log(db_session, duration_ms=10, agent="agent_b", status="error")
    _add_log(db_session, duration_ms=10, agent="agent_a", status="success")

    out = compute_status_breakdown(db_session)
    by_agent = {r["agent"]: r for r in out["agents"]}
    assert by_agent["agent_b"]["total"] == 3
    assert by_agent["agent_b"]["success"] == 2
    assert by_agent["agent_b"]["error"] == 1
    assert by_agent["agent_b"]["error_rate"] == round(1 / 3, 4)
    assert by_agent["agent_a"]["error_rate"] == 0.0


# ---------------------------------------------------------------------------
# compute_llm_metrics (aggregate)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Business metrics (Phase D.3 dashboard)
# ---------------------------------------------------------------------------

def _add_assessment(db, *, user_id: int, status: str = "complete",
                    personality_type: str | None = "S-CL-H",
                    session_id: str | None = None,
                    created_at: datetime | None = None):
    sid = session_id or f"sess_{user_id}_{status}_{datetime.now(timezone.utc).timestamp()}"
    a = Assessment(
        user_id=user_id, session_id=sid, status=status,
        personality_type=personality_type, mode="chat",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _add_order(db, *, user_id: int, assessment_id: int, status: str = "paid",
               amount: int = 990, out_trade_no: str | None = None,
               created_at: datetime | None = None):
    tn = out_trade_no or f"trade_{user_id}_{assessment_id}_{status}_{datetime.now(timezone.utc).timestamp()}"
    o = Order(
        user_id=user_id, assessment_id=assessment_id, out_trade_no=tn,
        amount=amount, status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


# --- compute_daily_users ---

def test_daily_users_returns_correct_window_size(db_session):
    out = compute_daily_users(db_session, days=7)
    assert len(out) == 7
    # 升序日期
    dates = [r["date"] for r in out]
    assert dates == sorted(dates)


def test_daily_users_buckets_into_correct_date(db_session):
    u = _add_user(db_session, openid="o_today_user")
    _add_assessment(db_session, user_id=u.id, status="complete")
    _add_assessment(db_session, user_id=u.id, status="pending")  # 不计完成

    out = compute_daily_users(db_session, days=3)
    today_bucket = out[-1]  # 升序最后一桶是今天
    assert today_bucket["new_users"] >= 1
    assert today_bucket["completed_assessments"] == 1


# --- compute_personality_distribution ---

def test_personality_distribution_groups_and_sorts(db_session):
    u = _add_user(db_session, openid="o_pers_dist")
    _add_assessment(db_session, user_id=u.id, status="complete", personality_type="S-CL-H")
    _add_assessment(db_session, user_id=u.id, status="complete", personality_type="S-CL-H")
    _add_assessment(db_session, user_id=u.id, status="complete", personality_type="MA-BL-P")
    _add_assessment(db_session, user_id=u.id, status="pending",  personality_type="A-CL-H")  # 不计入

    out = compute_personality_distribution(db_session, days=30)
    by_code = {r["type_code"]: r for r in out}
    assert by_code["S-CL-H"]["count"] == 2
    assert by_code["MA-BL-P"]["count"] == 1
    assert "A-CL-H" not in by_code
    # 降序
    counts = [r["count"] for r in out]
    assert counts == sorted(counts, reverse=True)
    # d1_group 从 type_code 首段抽取
    assert by_code["S-CL-H"]["d1_group"] == "S"
    assert by_code["MA-BL-P"]["d1_group"] == "MA"


def test_personality_distribution_empty_returns_empty_list(db_session):
    assert compute_personality_distribution(db_session, days=30) == []


# --- compute_assessment_funnel ---

def test_funnel_counts_each_status_independently(db_session):
    u = _add_user(db_session, openid="o_funnel")
    _add_assessment(db_session, user_id=u.id, status="pending")
    _add_assessment(db_session, user_id=u.id, status="generating")
    _add_assessment(db_session, user_id=u.id, status="analyzed")
    _add_assessment(db_session, user_id=u.id, status="complete")
    _add_assessment(db_session, user_id=u.id, status="complete")

    out = compute_assessment_funnel(db_session, days=30)
    assert out["stages"] == {"pending": 1, "generating": 1, "analyzed": 1, "complete": 2}
    assert out["total"] == 5


def test_funnel_empty_returns_zero_stages(db_session):
    out = compute_assessment_funnel(db_session, days=7)
    assert out["stages"] == {"pending": 0, "generating": 0, "analyzed": 0, "complete": 0}
    assert out["total"] == 0


# --- compute_daily_orders ---

def test_daily_orders_returns_window_size(db_session):
    out = compute_daily_orders(db_session, days=7)
    assert len(out) == 7
    for r in out:
        assert {"date", "paid", "failed", "pending", "revenue_yuan"} <= set(r.keys())


def test_daily_orders_revenue_only_from_paid(db_session):
    u = _add_user(db_session, openid="o_orders_rev")
    a = _add_assessment(db_session, user_id=u.id, status="complete")
    _add_order(db_session, user_id=u.id, assessment_id=a.id, status="paid",   amount=990)
    _add_order(db_session, user_id=u.id, assessment_id=a.id, status="paid",   amount=1990)
    _add_order(db_session, user_id=u.id, assessment_id=a.id, status="failed", amount=990)
    _add_order(db_session, user_id=u.id, assessment_id=a.id, status="pending", amount=990)

    out = compute_daily_orders(db_session, days=3)
    today = out[-1]
    assert today["paid"] == 2
    assert today["failed"] == 1
    assert today["pending"] == 1
    # 990 + 1990 = 2980 分 = 29.80 元
    assert today["revenue_yuan"] == 29.80


# --- compute_quality_score_distribution ---

def test_quality_score_distribution_buckets_by_threshold(db_session):
    u = _add_user(db_session, openid="o_quality")
    a = _add_assessment(db_session, user_id=u.id, status="complete")
    for score in (9, 8, 7, 6, 5, 3):
        db_session.add(ReportQualityAudit(
            assessment_id=a.id, judge_model="doubao-test",
            coherence_score=score, readability_score=score, factual_score=score,
            overall_score=score, duration_ms=10,
        ))
    db_session.commit()

    out = compute_quality_score_distribution(db_session, days=30)
    assert out["total"] == 6
    assert out["buckets"] == {"excellent": 2, "good": 2, "poor": 2}
    # 平均 (9+8+7+6+5+3)/6 = 6.33
    assert out["avg_score"] == 6.33


def test_quality_score_distribution_empty(db_session):
    out = compute_quality_score_distribution(db_session, days=30)
    assert out == {"window_days": 30, "buckets": {"excellent": 0, "good": 0, "poor": 0},
                   "total": 0, "avg_score": 0.0}


# --- compute_business_metrics (aggregate) ---

def test_compute_business_metrics_returns_all_sections(db_session):
    out = compute_business_metrics(db_session, days=7)
    assert out["window_days"] == 7
    assert "daily_users" in out
    assert "personality_distribution" in out
    assert "funnel" in out
    assert "daily_orders" in out
    assert len(out["daily_users"]) == 7
    assert len(out["daily_orders"]) == 7


# ---------------------------------------------------------------------------
# compute_llm_metrics (aggregate)
# ---------------------------------------------------------------------------

def test_compute_llm_metrics_returns_all_sections(db_session):
    u = _add_user(db_session, openid="o_metrics_user")
    _add_log(db_session, duration_ms=120, status="success", total_tokens=300, agent="agent_b")
    db_session.add(UserTokenQuota(
        user_id=u.id, usage_date=date.today(),
        prompt_tokens=200, completion_tokens=100, total_tokens=300,
    ))
    db_session.commit()

    out = compute_llm_metrics(db_session, hours=24, top_n=5)
    assert out["window_hours"] == 24
    assert "duration" in out
    assert out["duration"]["count"] == 1
    assert len(out["hourly_trend"]) == 24
    assert any(b["total"] >= 1 for b in out["hourly_trend"])
    assert any(r["user_id"] == u.id for r in out["top_users"])
    assert any(r["agent"] == "agent_b" for r in out["by_agent"])
