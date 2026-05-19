"""Admin 监控指标聚合（Phase D.1）。

提供 LLM 调用相关的统计：P50/P95 延迟、24h 调用趋势、token 消耗 top user。
所有计算都在 Python 端做，避免依赖 PostgreSQL 专有的 percentile_cont
（测试用的 SQLite 不支持）。
"""

from __future__ import annotations

import statistics
from datetime import date as _date_cls, datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.ai_call_log import AiCallLog
from app.models.user import User
from app.models.user_token_quota import UserTokenQuota


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def compute_duration_percentiles(db: Session, *, hours: int = 24) -> dict:
    """计算最近 N 小时 success 调用的 duration_ms P50 / P95 / P99 / 平均。"""
    since = _utc_now() - timedelta(hours=hours)
    rows = (
        db.query(AiCallLog.duration_ms)
        .filter(AiCallLog.ts >= since)
        .filter(AiCallLog.status == "success")
        .all()
    )
    durations = [r[0] for r in rows if r[0] is not None]
    if not durations:
        return {"count": 0, "p50": 0, "p95": 0, "p99": 0, "avg": 0, "max": 0}
    durations.sort()
    return {
        "count": len(durations),
        "p50":   _percentile(durations, 0.50),
        "p95":   _percentile(durations, 0.95),
        "p99":   _percentile(durations, 0.99),
        "avg":   round(statistics.mean(durations), 1),
        "max":   durations[-1],
    }


def _percentile(sorted_values: list[int], q: float) -> int:
    """已排序数组的近似分位数（线性插值），返回 int。"""
    if not sorted_values:
        return 0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return int(round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac))


def compute_hourly_trend(db: Session, *, hours: int = 24) -> list[dict]:
    """按小时分桶返回最近 N 小时的调用量与 token 消耗。

    返回升序（早 → 晚），每个桶含：
      hour: ISO8601 UTC 时间（hour 边界，分秒 = 0）
      total / success / error / total_tokens
    缺失的小时也补零桶。
    """
    now = _utc_now().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours - 1)

    rows = (
        db.query(AiCallLog.ts, AiCallLog.status, AiCallLog.total_tokens)
        .filter(AiCallLog.ts >= start)
        .all()
    )

    # 用 ISO 字符串作 key，避免 datetime 跨 tz-aware/naive 比较失配
    buckets: dict[str, dict] = {}
    ordered_keys: list[str] = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        key = ts.isoformat()
        buckets[key] = {
            "hour":          key,
            "total":         0,
            "success":       0,
            "error":         0,
            "total_tokens":  0,
        }
        ordered_keys.append(key)

    for ts, status, total_tokens in rows:
        if ts is None:
            continue
        # SQLite 默认存 naive datetime，读回时无 tzinfo；统一加 UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour_key = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        bucket = buckets.get(hour_key)
        if bucket is None:
            continue
        bucket["total"] += 1
        if status == "success":
            bucket["success"] += 1
        else:
            bucket["error"] += 1
        bucket["total_tokens"] += total_tokens or 0

    return [buckets[k] for k in ordered_keys]


def compute_top_users_by_tokens(db: Session, *, limit: int = 10) -> list[dict]:
    """按当日 token 消耗降序返回 top N 用户。

    join users 取 openid（前 12 位脱敏）以便管理员快速识别；
    user_token_quota 行未必存在用户，跳过孤行。
    """
    today = _date_cls.today()
    rows = (
        db.query(
            UserTokenQuota.user_id,
            UserTokenQuota.prompt_tokens,
            UserTokenQuota.completion_tokens,
            UserTokenQuota.total_tokens,
            User.openid,
        )
        .join(User, User.id == UserTokenQuota.user_id)
        .filter(UserTokenQuota.usage_date == today)
        .order_by(UserTokenQuota.total_tokens.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "user_id":           uid,
            "openid_masked":     (oid[:12] + "…") if oid and len(oid) > 12 else (oid or ""),
            "prompt_tokens":     pt,
            "completion_tokens": ct,
            "total_tokens":      tt,
        }
        for (uid, pt, ct, tt, oid) in rows
    ]


def compute_status_breakdown(db: Session, *, hours: int = 24) -> dict:
    """按 agent + status 维度统计调用次数与错误率。"""
    since = _utc_now() - timedelta(hours=hours)
    rows = (
        db.query(
            AiCallLog.agent,
            func.count(AiCallLog.id),
            func.sum(case((AiCallLog.status == "success", 1), else_=0)),
        )
        .filter(AiCallLog.ts >= since)
        .group_by(AiCallLog.agent)
        .all()
    )
    out = []
    for agent, total, success in rows:
        total_i = total or 0
        success_i = success or 0
        error_i = total_i - success_i
        error_rate = round(error_i / total_i, 4) if total_i else 0.0
        out.append({
            "agent":      agent,
            "total":      total_i,
            "success":    success_i,
            "error":      error_i,
            "error_rate": error_rate,
        })
    out.sort(key=lambda r: r["total"], reverse=True)
    return {"agents": out}


def compute_llm_metrics(db: Session, *, hours: int = 24, top_n: int = 10) -> dict:
    """聚合所有 LLM 监控指标，供 /admin/api/metrics/llm 一次返回。"""
    return {
        "window_hours":  hours,
        "duration":      compute_duration_percentiles(db, hours=hours),
        "hourly_trend":  compute_hourly_trend(db, hours=hours),
        "top_users":     compute_top_users_by_tokens(db, limit=top_n),
        "by_agent":      compute_status_breakdown(db, hours=hours)["agents"],
    }
