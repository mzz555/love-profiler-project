-- =============================================================================
-- Migration: 给 base_dimension_meta 表补 5 个字段注释
-- 日期: 2026-05-14
-- 背景:
--   base_dimension_meta 原 SQL（20260514_add_dimension_meta_and_segment_decode.sql）
--   只对 code / score_model / radar_label 3 列加了 COMMENT，遗漏：
--   name_cn / description / score_min / score_max / sort_order。本次补全。
-- =============================================================================

COMMENT ON COLUMN base_dimension_meta.name_cn     IS '维度中文名，如「依恋类型」「边界意识」，前端报告页标题展示用';
COMMENT ON COLUMN base_dimension_meta.description IS '维度测量内容一句话说明，作为前端二级说明文案，也供 AI prompt 动态注入';
COMMENT ON COLUMN base_dimension_meta.score_min   IS '量程下限：D1-D3=-12（强度型 6 题×-2）、D5 子面=-6（3 题×-2）、D4 归一化=0';
COMMENT ON COLUMN base_dimension_meta.score_max   IS '量程上限：D1-D3=+12（强度型 6 题×+2）、D5 子面=+6（3 题×+2）、D4 归一化=1';
COMMENT ON COLUMN base_dimension_meta.sort_order  IS '维度展示排序 1~5，对应 D1~D5 的自然顺序';
