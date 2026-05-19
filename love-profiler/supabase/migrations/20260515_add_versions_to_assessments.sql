-- Migration: 给 assessments 表增加 prompt_version / report_version 列
-- 日期: 2026-05-15
-- 背景:
--   Agent B 的 system prompt 会不定期迭代（措辞/约束/篇幅等），
--   报告结构（Section 顺序/数量）也可能不兼容升级。
--   为了支持批量回溯/统计/A-B test，需要把这两类版本号落库。
--   - prompt_version 由 agent_b 启动时从 docs/agent-b-system-prompt.md 头部解析
--   - report_version 是当前 Section schema 的版本号，结构破坏性变化时升级

ALTER TABLE assessments
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS report_version SMALLINT DEFAULT 1;

COMMENT ON COLUMN assessments.prompt_version
    IS 'Agent B system prompt 版本号；启动时从 docs/agent-b-system-prompt.md 头部 <!-- version: x.y --> 注解解析';
COMMENT ON COLUMN assessments.report_version
    IS '报告 Section schema 版本号；结构不兼容变化（section 拆分/重命名/顺序变）时手动升级';
