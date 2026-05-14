-- =============================================================================
-- Migration: 给 questions 表 19 个字段补全 COMMENT
-- 日期: 2026-05-14
-- 背景:
--   questions 表的原始建表 SQL（20260430_create_questions_table.sql）只有
--   表结构和 INSERT，没有 COMMENT ON COLUMN。本次补全字段注释，作为题库
--   语义的权威说明。COMMENT 重复执行幂等，对已有数据无影响。
-- =============================================================================

COMMENT ON TABLE  questions               IS '30 题题库。一行=一道题；30 题分布在 5 个维度（D1-D5），每维 6 题。题库版本由 version 字段管理';

COMMENT ON COLUMN questions.question_id   IS '题目唯一 ID，格式 {维度代码}-Q{两位序号}，如 D1-Q01 ~ D5-Q06';
COMMENT ON COLUMN questions.dimension     IS '维度中文名：依恋 / 边界 / 冲突 / 情感 / 风格，对应 D1~D5';
COMMENT ON COLUMN questions.signal_code   IS '维度内细化信号代码：S1-S5（5 个心理信号），D4-Q01 用 ALL（基线五语均测）';
COMMENT ON COLUMN questions.signal_name   IS '信号中文名，如「不确定性解读」「越界识别」「追逃模式」等；面向开发者';
COMMENT ON COLUMN questions.question_type IS '题型：强度型 / 爱的语言型 / 双子面型，决定 Agent A 的打分逻辑';
COMMENT ON COLUMN questions.stem          IS '题干文本，前端原样展示';
COMMENT ON COLUMN questions.option_a      IS '选项 A 文本';
COMMENT ON COLUMN questions.option_b      IS '选项 B 文本';
COMMENT ON COLUMN questions.option_c      IS '选项 C 文本';
COMMENT ON COLUMN questions.option_d      IS '选项 D 文本';
COMMENT ON COLUMN questions.option_e      IS '选项 E 文本，仅 D4-Q01 使用（五语均测），其他题为 NULL';
COMMENT ON COLUMN questions.score_a       IS '选项 A 的分值字符串。强度型用 +2/+1/-1/-2，爱的语言型用 T1+2 / T3+2 等指向爱语类型';
COMMENT ON COLUMN questions.score_b       IS '选项 B 的分值字符串，含义同 score_a';
COMMENT ON COLUMN questions.score_c       IS '选项 C 的分值字符串。注意 D3-Q06 的 C 含 score_meta={"pursue_avoid":"pursue"} 追型标记';
COMMENT ON COLUMN questions.score_d       IS '选项 D 的分值字符串。注意 D3-Q06 的 D 含 score_meta={"pursue_avoid":"avoid"} 逃型标记';
COMMENT ON COLUMN questions.score_e       IS '选项 E 的分值字符串，仅 D4-Q01 使用';
COMMENT ON COLUMN questions.sort_order    IS '题目展示顺序 1~30，前端按此顺序播放';
COMMENT ON COLUMN questions.version       IS '题库版本号，当前 V2。修订题目时升级版本，answer_package_builder 会带上 question_set_version';
COMMENT ON COLUMN questions.notes         IS '题目设计意图说明，仅供开发/运营查阅，不向用户/AI 暴露';
