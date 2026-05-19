-- Migration: 给 assessments 表增加 partial_sections JSONB 字段
-- 日期: 2026-05-15
-- 背景:
--   Agent B 流式写到中段崩溃时，前面已生成的 section（Title/Opening/Attachment/...）
--   会全部丢失，用户需要从头等。本字段持久化每个 section_end 的文本，
--   下次重连 WS 时 replay 给前端 + 提示 LLM 从下一段接续生成。
--   完成（status=complete）后清空，避免占空间。

ALTER TABLE assessments
    ADD COLUMN IF NOT EXISTS partial_sections JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN assessments.partial_sections
    IS 'Section 级断点续传：键=section 名（Title/Opening/Attachment/Boundary/Conflict/Language/Style/Highlight/Suggestion），值=该段已落库文本。每个 section_end 增量写；status=complete 后清空';
