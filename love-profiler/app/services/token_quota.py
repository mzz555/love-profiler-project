"""用户维度 daily token quota（Phase B.1）。

提供 3 个原子操作：
- add_usage：调用结束后累加（INSERT-OR-UPDATE 单条 SQL）
- get_today_total：查当日 total_tokens
- check_quota：超额抛 QuotaExceededError，应由上层转 HTTP 429

环境变量：
- USER_DAILY_TOKEN_QUOTA：单用户单日上限，默认 20000（约 5-10 份完整报告）
- DEV_MODE：true 时彻底 bypass（开发体验优先）

接入点：app/agents/report_writer.py + app/services/report_writer_runner.py + app/api/ws_result.py
"""

from __future__ import annotations

import logging
import os
from datetime import date as _date_cls

from sqlalchemy.orm import Session

from app.models.user_token_quota import UserTokenQuota

logger = logging.getLogger(__name__)

_DEFAULT_DAILY_LIMIT = 20_000


class QuotaExceededError(Exception):
    """单用户当日 token 用量已达上限。"""

    def __init__(self, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__(f"daily token quota exceeded: used={used}, limit={limit}")


def _dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() == "true"


def _limit() -> int:
    raw = os.environ.get("USER_DAILY_TOKEN_QUOTA", "")
    if not raw:
        return _DEFAULT_DAILY_LIMIT
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "[token_quota] 环境变量 USER_DAILY_TOKEN_QUOTA 非法值 %r，回退默认 %d",
            raw, _DEFAULT_DAILY_LIMIT,
        )
        return _DEFAULT_DAILY_LIMIT


def add_usage(
    db: Session,
    *,
    user_id: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """把本次调用消耗累加到当日记录。

    prompt_tokens + completion_tokens 同为 0 时直接返回，避免建空行。
    """
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return

    today = _date_cls.today()
    row = (
        db.query(UserTokenQuota)
        .filter_by(user_id=user_id, usage_date=today)
        .one_or_none()
    )
    total_delta = prompt_tokens + completion_tokens
    if row is None:
        row = UserTokenQuota(
            user_id=user_id,
            usage_date=today,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_delta,
        )
        db.add(row)
    else:
        row.prompt_tokens += prompt_tokens
        row.completion_tokens += completion_tokens
        row.total_tokens += total_delta
    db.commit()


def get_today_total(db: Session, *, user_id: int) -> int:
    """查询用户当日累计 total_tokens；无记录返回 0。"""
    today = _date_cls.today()
    row = (
        db.query(UserTokenQuota)
        .filter_by(user_id=user_id, usage_date=today)
        .one_or_none()
    )
    return row.total_tokens if row else 0


def check_quota(db: Session, *, user_id: int) -> None:
    """LLM 调用前预检：已用 ≥ 上限 → QuotaExceededError。

    DEV_MODE=true 时无条件通过；保证本地联调不受配额干扰。
    """
    if _dev_mode():
        return
    used = get_today_total(db, user_id=user_id)
    limit = _limit()
    if used >= limit:
        raise QuotaExceededError(used=used, limit=limit)
