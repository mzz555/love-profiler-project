-- =============================================================================
-- Migration: 给 base_D5_quadrant 表补 sort_order / version 字段注释
-- 日期: 2026-05-14
-- 背景:
--   base_D5_quadrant 原 SQL（20260509_create_base_d5_quadrant_table.sql）
--   已给 quadrant / style_name / description / guide 4 列加了 COMMENT，
--   但 sort_order / version 2 列遗漏。本次补全。
--   表名含大写 D，COMMENT 命令必须用双引号引用。
-- =============================================================================

COMMENT ON COLUMN "base_D5_quadrant".sort_order IS '展示排序 1~9，对应 9 宫格（高直接×高分享 → 高含蓄×低分享）的自然顺序';
COMMENT ON COLUMN "base_D5_quadrant".version    IS '数据版本号，当前 V1。迭代写作方向时升级版本';
