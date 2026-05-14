-- =============================================================================
-- Migration: 建 users 表
-- 日期: 2026-05-14
-- 背景:
--   此表此前由 SQLAlchemy lifespan 自动 create_tables() 建立，
--   本 migration 补全建表 SQL 作为权威 schema 文档。
--   IF NOT EXISTS 保证 SQLAlchemy 已建好的环境下安全幂等。
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    openid     VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

COMMENT ON TABLE  users           IS '抖音小程序用户。每个 openid 对应一个登录用户';
COMMENT ON COLUMN users.id        IS '自增主键';
COMMENT ON COLUMN users.openid    IS '抖音侧 openid，作为用户唯一身份标识。来源于 tt.login() 返回 code 换取';
COMMENT ON COLUMN users.created_at IS '首次登录时间（UTC）';

CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid);
