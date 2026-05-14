-- =============================================================================
-- Migration: 新增维度元信息表 + D1/D2/D3 段落解码表
-- 日期: 2026-05-14
-- 背景:
--   base_D4_type 和 base_D5_quadrant 已有对应解释表，但 D1/D2/D3 的
--   段落代码（S/MS/MA/A/CL/BL/H/P）含义只存在于 prompt 文本中。
--   本 migration 补全这两块缺口，使全部五维度均有数据库层面的元数据，
--   前端可直接 JOIN 渲染，AI prompt 也可动态注入，无需硬编码。
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 表1: base_dimension_meta
-- 存储 D1~D5 五个维度的基本信息
-- 用途:
--   - 前端雷达图轴名 (radar_label)
--   - 报告页维度标题和说明
--   - 提供各维度的计分模型和量程供前端/AI参考
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS base_dimension_meta (
    code         VARCHAR(5)  PRIMARY KEY,   -- 维度代码，如 D1 / D2 / D3 / D4 / D5
    name_cn      VARCHAR(20) NOT NULL,       -- 维度中文名，如"依恋类型"
    description  TEXT,                      -- 测量内容一句话说明
    score_model  VARCHAR(20) NOT NULL,       -- 计分模型: intensity / preference / dual_axis
    score_min    SMALLINT,                   -- 量程下限（D1-D3: -12，D5子面: -6，D4: 0）
    score_max    SMALLINT,                   -- 量程上限（D1-D3: +12，D5子面: +6，D4归一化: 1）
    radar_label  VARCHAR(15) NOT NULL,       -- 雷达图轴名（简短，如"依恋"）
    sort_order   SMALLINT    NOT NULL DEFAULT 0  -- 显示排序（1~5 对应 D1~D5）
);

COMMENT ON TABLE  base_dimension_meta           IS '五维度元信息，供前端展示和 AI 动态注入上下文';
COMMENT ON COLUMN base_dimension_meta.code        IS '维度代码 D1-D5';
COMMENT ON COLUMN base_dimension_meta.score_model IS 'intensity=强度型累加(-12~+12); preference=类型偏好归一化(0~1); dual_axis=双子面各自-6~+6';
COMMENT ON COLUMN base_dimension_meta.radar_label IS '雷达图轴标签，字数尽量≤4字';

INSERT INTO base_dimension_meta (code, name_cn, description, score_model, score_min, score_max, radar_label, sort_order) VALUES
-- D1: 6道题，强度型，量程 -12~+12
('D1', '依恋类型',   '遭遇关系不确定性时（对方沉默/出现第三方）依恋系统的激活模式',     'intensity',  -12,  12, '依恋',     1),
-- D2: 6道题，强度型，量程 -12~+12
('D2', '边界意识',   '关系中保持独立自我、识别并响应越界行为的能力',                   'intensity',  -12,  12, '边界',     2),
-- D3: 6道题，强度型，量程 -12~+12；另有追逃亚型标记
('D3', '冲突处理',   '关系摩擦出现时的表达方式与修复主动性（Gottman 研究最强预测变量）', 'intensity',  -12,  12, '冲突',     3),
-- D4: 6道题，类型偏好型，原始分归一化到 0~1 后取 top2
('D4', '情感需求',   '最能感知"被爱"的方式——五种爱的语言的相对偏好排序',              'preference',   0,   1, '爱语',     4),
-- D5: 6道题，双子面（S1直接性 / S2分享欲），各子面量程 -6~+6
('D5', '亲密风格',   '直接性（说话/需求表达）与分享欲（信息主动流动）两个独立子面',     'dual_axis',   -6,   6, '风格',     5)
ON CONFLICT (code) DO NOTHING;


-- -----------------------------------------------------------------------------
-- 表2: base_segment_decode
-- 存储 D1/D2/D3 的 type_code 段落代码的解码规则
-- 说明:
--   type_code 格式: <D1段>-<D2段>-<D3段>，如 MS-CL-P
--   D4/D5 不进入主分型（避免膨胀到 1440 类），其解码已由
--   base_D4_type 和 base_D5_quadrant 覆盖，本表只处理 D1-D3
-- 用途:
--   - 前端报告页动态渲染 "你的代码含义" 解读
--   - 双人配对报告逐段对比兼容度（未来功能预留）
--   - Agent prompt 动态注入维度描述
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS base_segment_decode (
    id          SERIAL      PRIMARY KEY,
    dimension   VARCHAR(5)  NOT NULL,  -- 所属维度: D1 / D2 / D3
    code        VARCHAR(5)  NOT NULL,  -- 段落代码: S / MS / MA / A / CL / BL / H / P
    label_cn    VARCHAR(25) NOT NULL,  -- 展示标签，如"安全型依恋"
    description TEXT,                 -- 一句话核心特征说明
    score_range VARCHAR(30),          -- 对应的原始分区间，如"≥6分"（参考用，实际分型由 Agent A 执行）
    is_healthy  BOOLEAN     NOT NULL DEFAULT TRUE,  -- 是否为健康端（用于前端配色和图标区分）
    sort_order  SMALLINT    NOT NULL DEFAULT 0,
    UNIQUE (dimension, code)          -- 同维度内代码唯一
);

COMMENT ON TABLE  base_segment_decode             IS 'D1/D2/D3 type_code 段落代码解码表；D4/D5 另有专表';
COMMENT ON COLUMN base_segment_decode.code        IS '段落代码，与 base_love_type.type_code 中对应位置一致';
COMMENT ON COLUMN base_segment_decode.score_range IS '参考区间，仅作展示；实际分型由 Agent A 按得分就近归类';
COMMENT ON COLUMN base_segment_decode.is_healthy  IS 'true=健康/积极端；false=问题/消极端；供前端差异化配色';

INSERT INTO base_segment_decode (dimension, code, label_cn, description, score_range, is_healthy, sort_order) VALUES

-- -------------------------
-- D1 依恋类型（4档）
-- 评分映射（强度型，-12~+12）:
--   ≥6       → S  安全型
--   3~5      → MS 中度安全
--   -5~-3    → MA 中度焦虑（混合型 -2~2 由 Agent A 就近归入 MS 或 MA）
--   ≤-6      → A  焦虑型
-- -------------------------
('D1', 'S',  '安全型依恋',
    '在关系不确定时能保持内心稳定，信任基底强，不需要持续确认',
    '≥6分',     TRUE,  1),
('D1', 'MS', '中度安全型依恋',
    '整体稳定，偶有情绪波动但具备自我调节能力，依恋需求适中',
    '3~5分',    TRUE,  2),
('D1', 'MA', '中度焦虑型依恋',
    '对关系信号较为敏感，有时需要额外的确认感，激活后能逐渐平复',
    '-5~-3分',  FALSE, 3),
('D1', 'A',  '焦虑型依恋',
    '对分离或不确定性有强烈焦虑反应，激活后难以快速平复，需要大量确认',
    '≤-6分',    FALSE, 4),

-- -------------------------
-- D2 边界意识（2档）
-- 评分映射（强度型，-12~+12）:
--   ≥3       → CL 清晰边界（含混合偏正方向）
--   <-3      → BL 模糊边界（含混合偏负方向）
--   混合段（-3~3）由 Agent A 就近归类
-- -------------------------
('D2', 'CL', '清晰边界',
    '能识别越界行为并作出健康响应，在亲密关系中维持独立自我',
    '≥3分',     TRUE,  1),
('D2', 'BL', '模糊边界',
    '自我与关系的边界不清晰，容易被对方需求吞没，或自我消融于关系中',
    '<-3分',    FALSE, 2),

-- -------------------------
-- D3 冲突处理（2档）
-- 评分映射（强度型，-12~+12）:
--   ≥3       → H  健康冲突模式
--   <-3      → P  问题冲突模式
--   混合段由 Agent A 就近归类
-- 注意: D3 另有"追逃亚型"（pursue_avoid_role），存于 diagnosis_json，
--       不体现在 type_code 但在报告中单独解读
-- -------------------------
('D3', 'H',  '健康冲突模式',
    '能建设性地表达不满，具备主动修复裂缝的意愿和能力，冲突后关系可修复',
    '≥3分',     TRUE,  1),
('D3', 'P',  '问题冲突模式',
    '在冲突中容易回避、攻击或情绪失控，摩擦后裂缝难以自然修复',
    '<-3分',    FALSE, 2)

ON CONFLICT (dimension, code) DO NOTHING;
