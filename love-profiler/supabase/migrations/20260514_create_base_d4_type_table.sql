-- =============================================================================
-- Migration: 建 base_D4_type 表
-- 日期: 2026-05-14
-- 背景:
--   此表是 D4 维度（爱的语言/情感需求）5 种类型的字典：T1 言语肯定 / T2 精心时刻
--   / T3 用心小惊喜 / T4 服务行动 / T5 身体接触。
--   此前由早期手动 SQL 创建，无 migration 文档。
--   本 migration 补全建表 SQL（schema 通过 psql/inspector 从生产 DB 反向获取）。
--   注意：表名含大写 D，PostgreSQL 必须用双引号 "base_D4_type" 引用。
-- =============================================================================

CREATE TABLE IF NOT EXISTS "base_D4_type" (
    id                     SERIAL       PRIMARY KEY,
    love_languages_code    VARCHAR(255),
    love_languages_name    VARCHAR(255),
    love_languages_detail  VARCHAR(255)
);

COMMENT ON TABLE  "base_D4_type"                       IS 'D4 维度（爱的语言）5 类字典。Agent A 归一化后取 top2 作为用户的情感需求画像';
COMMENT ON COLUMN "base_D4_type".id                    IS '自增主键';
COMMENT ON COLUMN "base_D4_type".love_languages_code   IS '爱的语言代码：T1（言语肯定）/ T2（精心时刻）/ T3（用心小惊喜）/ T4（服务行动）/ T5（身体接触）';
COMMENT ON COLUMN "base_D4_type".love_languages_name   IS '爱的语言中文名，前端报告页展示用';
COMMENT ON COLUMN "base_D4_type".love_languages_detail IS '该类爱的语言的详细解读文案，AI 报告与前端均可引用';
