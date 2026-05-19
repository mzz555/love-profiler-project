-- Migration: 新建 user_token_quota 表（B.1 user 维度 daily token quota）
-- 日期: 2026-05-15
-- 背景:
--   现有限流仅按 IP（slowapi），无法防止单用户多设备/多 IP 刷量；
--   也无法基于 LLM token 真实消耗做成本控制。
--   本表按 (user_id, usage_date) 累加 prompt / completion / total 三个计数，
--   服务层 add_usage 走 INSERT-OR-UPDATE（PG 的 ON CONFLICT），
--   预检调用 SUM 当日 total_tokens 与 USER_DAILY_TOKEN_QUOTA 比较。

CREATE TABLE IF NOT EXISTS user_token_quota (
    user_id            INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date         DATE        NOT NULL,
    prompt_tokens      BIGINT      NOT NULL DEFAULT 0,
    completion_tokens  BIGINT      NOT NULL DEFAULT 0,
    total_tokens       BIGINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS user_token_quota_usage_date_idx
    ON user_token_quota (usage_date);

COMMENT ON TABLE  user_token_quota                    IS '单用户单日 LLM token 用量聚合；驱动 daily quota 校验与成本归因';
COMMENT ON COLUMN user_token_quota.user_id            IS '关联 users.id，用户删除时级联删除';
COMMENT ON COLUMN user_token_quota.usage_date         IS '用量统计日（服务器时区）；与 user_id 组成复合主键';
COMMENT ON COLUMN user_token_quota.prompt_tokens      IS '当日累计 prompt token 数（来自 LLM 响应 usage.prompt_tokens）';
COMMENT ON COLUMN user_token_quota.completion_tokens  IS '当日累计 completion token 数';
COMMENT ON COLUMN user_token_quota.total_tokens       IS '当日 prompt + completion 累计，用于配额比较，避免每次重算';
