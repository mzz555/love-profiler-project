-- =============================================================================
-- Migration: 清洗 base_love_type.detail 字段中的治疗/疗愈类禁词
-- 日期: 2026-05-22
-- 背景:
--   docs/agent-b-system-prompt.md 第 73 行禁止 report writer 输出"治愈/疗愈/
--   修复自己/心理健康"等治疗类词汇。
--   16 行扫描后发现 [MS-BL-H] 柔软的修复师 的 detail 含"治愈彼此旧伤"，
--   作为"类型锚定句"被 build_user_message 注入 LLM 上下文，
--   prompt 又要求"开篇画像必须以锚定句为起点展开"，
--   导致 LLM 老实搬入 Opening 段（input poisoning output）。
--
--   修复策略：把"治愈彼此旧伤"改写为不踩禁词的等价诗意措辞。
--
-- 改动范围:
--   仅 [MS-BL-H] 一行；其余 15 行 detail/tagline 字段经正则扫描无禁词命中。
-- =============================================================================

UPDATE base_love_type
SET detail = '用柔软缝合裂缝，用爱意安放旧伤'
WHERE type_code = 'MS-BL-H';
