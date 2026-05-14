-- =============================================================================
-- Migration: 建 assessments 表
-- 日期: 2026-05-14
-- 背景:
--   此表此前由 SQLAlchemy lifespan 自动 create_tables() 建立，
--   本 migration 补全建表 SQL 作为权威 schema 文档。
--   含若干对话模式（已废弃）遗留字段：signals / summary / mode / dimension_scores，
--   保留是为避免数据库迁移成本，但新代码不应再写入这些字段。
-- =============================================================================

CREATE TABLE IF NOT EXISTS assessments (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    session_id        VARCHAR(64) UNIQUE NOT NULL,
    signals           TEXT NOT NULL DEFAULT '{}',
    personality_type  VARCHAR(32),
    report_text       TEXT,
    summary           TEXT,
    status            VARCHAR(16) NOT NULL DEFAULT 'pending',
    mode              VARCHAR(16) NOT NULL DEFAULT 'chat',
    dimension_scores  TEXT,
    answers_json      TEXT,
    diagnosis_json    TEXT,
    report_json       TEXT,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

COMMENT ON TABLE  assessments                  IS '一次完整的恋爱人格测评记录。一个用户可有多条记录（历史回溯）';
COMMENT ON COLUMN assessments.id               IS '自增主键';
COMMENT ON COLUMN assessments.user_id          IS '关联 users.id，标识测评归属用户';
COMMENT ON COLUMN assessments.session_id       IS '测评会话唯一 ID（UUID），前端用它发起 WebSocket 与缓存';
COMMENT ON COLUMN assessments.signals          IS '【遗留】对话模式下 Agent1 提取的 5 项心理信号 JSON。quick-mode 新代码不写入，仅保留为兼容';
COMMENT ON COLUMN assessments.personality_type IS '16 类人格主类型 type_code（如 MA-CL-H），由 Agent A 计算并被 quiz.py 用 base_love_type 表校验后写入';
COMMENT ON COLUMN assessments.report_text      IS 'Agent B 输出的完整流式报告原文（含 --Section-- 标记）';
COMMENT ON COLUMN assessments.summary          IS '【遗留】对话模式时代的报告短摘要。新代码不写入';
COMMENT ON COLUMN assessments.status           IS '状态流转：pending → analyzed（Agent A 完成）→ generating（Agent B 开始流式）→ complete（Agent B 完成）';
COMMENT ON COLUMN assessments.mode             IS '【遗留】测评模式，旧值为 chat / quick。新代码不再使用，保留为字段兼容';
COMMENT ON COLUMN assessments.dimension_scores IS '【遗留】对话模式时代的维度分数 JSON。新代码用 diagnosis_json 取代';
COMMENT ON COLUMN assessments.answers_json     IS 'quick-mode 下 30 题的用户答案 JSON，由 /quiz/submit 写入';
COMMENT ON COLUMN assessments.diagnosis_json   IS 'Agent A 输出的结构化诊断 JSON（含 type_code / dimensions / highlights）';
COMMENT ON COLUMN assessments.report_json      IS 'Agent B 输出的结构化报告 JSON（含 raw_llm_output 字段）';
COMMENT ON COLUMN assessments.created_at       IS '记录创建时间（UTC）';

CREATE INDEX IF NOT EXISTS idx_assessments_user_id    ON assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_assessments_session_id ON assessments(session_id);
CREATE INDEX IF NOT EXISTS idx_assessments_status     ON assessments(status);
