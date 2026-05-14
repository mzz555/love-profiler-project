-- Migration: D5 表达风格 9 宫格写作方向参考表
-- agent_a 输出 dimensions.D5.quadrant（9 种），enrich 阶段查表得 guide 写入 diagnosis.D5_guide
-- 替代原 agent_b._D5_QUADRANT_GUIDES 字典；顺手修了 key 与 agent_a 输出不匹配的 bug
-- （旧字典 key 用 style，但 agent_a 实际只产 8 种 style，且命名不与 9 宫格 quadrant 对齐）

CREATE TABLE IF NOT EXISTS "base_D5_quadrant" (
    quadrant     TEXT PRIMARY KEY,
    style_name   TEXT NOT NULL,
    description  TEXT NOT NULL,
    guide        TEXT NOT NULL,
    sort_order   INTEGER NOT NULL,
    version      TEXT NOT NULL DEFAULT 'V1'
);

COMMENT ON TABLE  "base_D5_quadrant"             IS 'D5 表达风格 9 宫格 → 报告写作方向；agent_a 算出 quadrant，enrich 阶段查此表注入 D5_guide';
COMMENT ON COLUMN "base_D5_quadrant".quadrant    IS '直接性×分享欲象限，与 agent_a._d5_quadrant 输出的 quadrant 字段一致（如 "高直接×高分享"）';
COMMENT ON COLUMN "base_D5_quadrant".style_name  IS '风格名（参考用，agent_a 当前可能输出该名或带"偏中"后缀）';
COMMENT ON COLUMN "base_D5_quadrant".description IS '该象限的打分算法说明（s1=D5-Q01+Q02+Q03 直接性、s2=D5-Q04+Q05+Q06 分享欲，阈值 >3 / -3~3 / <-3）；面向开发与运营，不进 LLM 提示';
COMMENT ON COLUMN "base_D5_quadrant".guide       IS 'Agent B 写 D5 段的写作方向参考；含风格描述 + 一段写法示范';

INSERT INTO "base_D5_quadrant" (quadrant, style_name, description, guide, sort_order) VALUES
('高直接×高分享', '直爽热情型',
 's1>3 且 s2>3（直接性强 + 分享欲强）',
 '直接说、主动发、不怕占对方时间；关系里的信息密度高。写法示范：「你是那种有话就直说，也不怕多说的人。信息流动快，对方能清楚感受到你的想法和情绪。」', 1),
('高直接×中分享', '高直中分享型',
 's1>3 且 -3≤s2≤3（直接性强 + 分享欲中等）',
 '整体表达顺畅，分享有选择性。写法示范：「你表达得清楚，但不是什么都说。选择性地分享，而不是什么都往外倒。」', 2),
('高直接×低分享', '清爽利落型',
 's1>3 且 s2<-3（直接性强 + 分享欲弱）',
 '说了就算，话不多，但每句都清楚。写法示范：「你的表达很干脆。不需要太多铺垫，想说什么就说，一句顶一句。」', 3),
('中直接×高分享', '中直高分享型',
 '-3≤s1≤3 且 s2>3（直接性中等 + 分享欲强）',
 '话多但有时候不直接说要什么，靠对方感受。写法示范：「你话很多，但有时候不是直接说，而是期待他从细节里感受你的意思。」', 4),
('中直接×中分享', '默认型',
 '-3≤s1≤3 且 -3≤s2≤3（直接性中等 + 分享欲中等）',
 '不会让对方读不懂，也不会让对方读太透；表达平衡居中。写法示范：「你的表达不会让人困惑，也没有特别暴露。平衡的那种，对方能听懂，也不会被你的情绪淹没。」', 5),
('中直接×低分享', '中直低分享型',
 '-3≤s1≤3 且 s2<-3（直接性中等 + 分享欲弱）',
 '话少但清楚，想被主动问。写法示范：「你不会主动铺开讲，但被问起来能清楚说明白。话少，但不含混。」', 6),
('高含蓄×高分享', '碎碎念含蓄型',
 's1<-3 且 s2>3（直接性弱 + 分享欲强）',
 '说了很多但说不到点上，期待对方领会。写法示范：「你的分享有很多碎片——想表达的东西很多，但有时候不是直接说，靠对方去领会。」', 7),
('高含蓄×中分享', '低直中分享型',
 's1<-3 且 -3≤s2≤3（直接性弱 + 分享欲中等）',
 '有分享意愿但表达含蓄，需要对方耐心。写法示范：「你有想分享的东西，但表达方式比较含蓄。对方需要一点耐心才能听懂你没说出口的部分。」', 8),
('高含蓄×低分享', '安静含蓄型',
 's1<-3 且 s2<-3（直接性弱 + 分享欲弱）',
 '很少主动，话也含蓄，相处需要时间。写法示范：「你在表达上很保留。不会主动占用对方的时间，话也说得含蓄。这种相处需要时间才能熟悉。」', 9)
ON CONFLICT (quadrant) DO NOTHING;
