-- =============================================================================
-- Migration: 建 base_love_type 表
-- 日期: 2026-05-14
-- 背景:
--   此表是 16 类恋爱人格的权威字典，agent_a 算出 type_code 后由 quiz.py 在
--   此表查询 type_name / tagline / img_path 等展示字段。
--   此前由早期手动 SQL 创建，无 migration 文档；20260509 仅有 ALTER 加 tagline 列。
--   本 migration 补全建表 SQL（schema 通过 psql/inspector 从生产 DB 反向获取）。
-- =============================================================================

CREATE TABLE IF NOT EXISTS base_love_type (
    id          SERIAL       PRIMARY KEY,
    type_code   VARCHAR(255),
    type_name   VARCHAR(255),
    main_man    VARCHAR(255),
    main_woman  VARCHAR(255),
    remark      VARCHAR(255),
    detail      VARCHAR(255),
    img_path    VARCHAR(255),
    tagline     TEXT         NOT NULL DEFAULT ''
);

COMMENT ON TABLE  base_love_type            IS '16 类恋爱人格主类型字典。type_code 由 agent_a 的 D1×D2×D3 三轴组合决定（4×2×2=16）';
COMMENT ON COLUMN base_love_type.id         IS '自增主键';
COMMENT ON COLUMN base_love_type.type_code  IS '类型代码，三轴缩写：依恋(S/MS/MA/A) - 边界(CL/BL) - 冲突(H/P)。例: MA-CL-H';
COMMENT ON COLUMN base_love_type.type_name  IS '类型中文名，如「高敏感的清醒者」「靠岸的航行者」';
COMMENT ON COLUMN base_love_type.main_man   IS '男版主图片路径（指向 static/personalities/{type_code}_man.png）';
COMMENT ON COLUMN base_love_type.main_woman IS '女版主图片路径（指向 static/personalities/{type_code}_woman.png）';
COMMENT ON COLUMN base_love_type.remark     IS '简短备注/副标题，用于报告页二级展示';
COMMENT ON COLUMN base_love_type.detail     IS '类型详细描述（一句话核心定位）';
COMMENT ON COLUMN base_love_type.img_path   IS '附加人物图路径（指向 static/addtional/character_NN.png，注意 addtional 是历史拼写错误，保持）';
COMMENT ON COLUMN base_love_type.tagline    IS '类型标语，报告页 Title 段使用。例：「敏感是你的雷达，也是你的铠甲」';

CREATE INDEX IF NOT EXISTS idx_base_love_type_type_code ON base_love_type(type_code);
