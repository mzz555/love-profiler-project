-- =============================================================================
-- Migration: 给 base_segment_decode 表补 5 个字段注释
-- 日期: 2026-05-14
-- 背景:
--   base_segment_decode 原 SQL（20260514_add_dimension_meta_and_segment_decode.sql）
--   只对 code / score_range / is_healthy 3 列加了 COMMENT，遗漏：
--   id / dimension / label_cn / description / sort_order。本次补全。
-- =============================================================================

COMMENT ON COLUMN base_segment_decode.id          IS '自增主键';
COMMENT ON COLUMN base_segment_decode.dimension   IS '所属维度：D1 / D2 / D3。注意 D4/D5 不进入主分型，各有专门字典表（base_D4_type / base_D5_quadrant）';
COMMENT ON COLUMN base_segment_decode.label_cn    IS '段落中文展示标签，如「安全型依恋」「清晰边界」「健康冲突模式」，报告页和管理后台展示';
COMMENT ON COLUMN base_segment_decode.description IS '该段落的一句话核心特征说明，供前端二级说明文案与 AI prompt 动态注入';
COMMENT ON COLUMN base_segment_decode.sort_order  IS '同维度内展示排序：S→MS→MA→A / CL→BL / H→P，健康端在前';
