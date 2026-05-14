-- =============================================================================
-- Migration: 建 orders 表
-- 日期: 2026-05-14
-- 背景:
--   此表此前由 SQLAlchemy lifespan 自动 create_tables() 建立，
--   本 migration 补全建表 SQL 作为权威 schema 文档。
-- =============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    out_trade_no  VARCHAR(64) UNIQUE NOT NULL,
    amount        INTEGER NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

COMMENT ON TABLE  orders               IS '支付订单。每解锁一次报告（付费路径）产生一条订单记录';
COMMENT ON COLUMN orders.id            IS '自增主键';
COMMENT ON COLUMN orders.user_id       IS '关联 users.id，标识下单用户';
COMMENT ON COLUMN orders.assessment_id IS '关联 assessments.id，标识要解锁的测评';
COMMENT ON COLUMN orders.out_trade_no  IS '商户订单号（幂等键），格式 LP + 14 位 hex；由本服务生成、字节跳动支付系统使用';
COMMENT ON COLUMN orders.amount        IS '金额（单位：分）。¥9.9 = 990。广告解锁路径金额为 0';
COMMENT ON COLUMN orders.status        IS '订单状态：pending（创建未支付）/ paid（支付成功）/ failed（支付失败）';
COMMENT ON COLUMN orders.created_at    IS '订单创建时间（UTC）';

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
