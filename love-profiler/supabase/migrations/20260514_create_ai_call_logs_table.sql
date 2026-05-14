-- =============================================================================
-- Migration: 建 ai_call_logs 表
-- 日期: 2026-05-14
-- 背景:
--   此表此前由 SQLAlchemy lifespan 自动 create_tables() 建立，
--   本 migration 补全建表 SQL 作为权威 schema 文档。
--   每行对应一次 LLM API 调用（success 与 error 都记录），用于 /admin/logs 监控。
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_call_logs (
    id                 SERIAL PRIMARY KEY,
    ts                 TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    agent              VARCHAR(50)  NOT NULL,
    session_id         VARCHAR(100),
    user_id            INTEGER,
    model              VARCHAR(100) NOT NULL,
    temperature        DOUBLE PRECISION NOT NULL,
    retry_index        INTEGER NOT NULL DEFAULT 0,
    status             VARCHAR(20) NOT NULL,
    error_message      TEXT,
    http_status_code   INTEGER,
    system_prompt_len  INTEGER NOT NULL DEFAULT 0,
    messages_json      TEXT,
    response_preview   TEXT,
    response_len       INTEGER NOT NULL DEFAULT 0,
    duration_ms        INTEGER NOT NULL,
    prompt_tokens      INTEGER NOT NULL DEFAULT 0,
    completion_tokens  INTEGER NOT NULL DEFAULT 0,
    total_tokens       INTEGER NOT NULL DEFAULT 0
);

COMMENT ON TABLE  ai_call_logs                   IS 'LLM API 调用全链路日志。每个 Agent 每轮调用都记录一行';
COMMENT ON COLUMN ai_call_logs.id                IS '自增主键';
COMMENT ON COLUMN ai_call_logs.ts                IS '调用发起时间戳（UTC），建索引用于按时间筛选';
COMMENT ON COLUMN ai_call_logs.agent             IS 'Agent 标识：agent_b 等（agent_a 是纯 Python 不入此表）';
COMMENT ON COLUMN ai_call_logs.session_id        IS '关联的测评 session_id，便于按 session 串起多次调用';
COMMENT ON COLUMN ai_call_logs.user_id           IS '关联用户 ID（用于按用户统计），可为 NULL';
COMMENT ON COLUMN ai_call_logs.model             IS 'LLM 模型名（如 doubao-pro-32k）';
COMMENT ON COLUMN ai_call_logs.temperature       IS '调用时的 temperature 参数';
COMMENT ON COLUMN ai_call_logs.retry_index       IS '本次调用是第几次重试（0 表示首次）';
COMMENT ON COLUMN ai_call_logs.status            IS '调用结果：success / error';
COMMENT ON COLUMN ai_call_logs.error_message     IS '错误时的异常信息（成功时 NULL）';
COMMENT ON COLUMN ai_call_logs.http_status_code  IS 'HTTP 响应状态码（如 200/429/500），错误诊断用';
COMMENT ON COLUMN ai_call_logs.system_prompt_len IS 'system_prompt 字符数（不存原文以避免行过大）';
COMMENT ON COLUMN ai_call_logs.messages_json     IS '完整 messages 数组 JSON（含 user/assistant 历史）';
COMMENT ON COLUMN ai_call_logs.response_preview  IS '响应内容前 2000 字符预览（完整内容太长不存）';
COMMENT ON COLUMN ai_call_logs.response_len      IS '响应内容总字符数';
COMMENT ON COLUMN ai_call_logs.duration_ms       IS 'API 调用耗时（毫秒）';
COMMENT ON COLUMN ai_call_logs.prompt_tokens     IS '消耗的 prompt token 数（豆包 usage.prompt_tokens）';
COMMENT ON COLUMN ai_call_logs.completion_tokens IS '消耗的 completion token 数';
COMMENT ON COLUMN ai_call_logs.total_tokens      IS 'prompt + completion 总 token 数';

CREATE INDEX IF NOT EXISTS idx_ai_call_logs_ts         ON ai_call_logs(ts);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_agent      ON ai_call_logs(agent);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_session_id ON ai_call_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_user_id    ON ai_call_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_status     ON ai_call_logs(status);
