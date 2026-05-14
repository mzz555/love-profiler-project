-- Migration: highlights 诊断高光参考表
-- 存储 12 种高光类型的完整定义：Agent A 触发条件 + Agent B 解读路径与报告语言种子
-- 单源真相：触发逻辑在 app/agents/agent_a.py，解读字典在此表，Agent B 系统提示从此表同步

CREATE TABLE IF NOT EXISTS highlights (
    code              TEXT    PRIMARY KEY,
    layer             INTEGER NOT NULL,
    involved_dims     TEXT    NOT NULL,
    severity          TEXT    NOT NULL CHECK (severity IN ('high', 'moderate', 'info')),
    is_positive       BOOLEAN NOT NULL DEFAULT false,
    name_cn           TEXT    NOT NULL,
    trigger_condition TEXT    NOT NULL,
    interp_path       TEXT    NOT NULL,
    report_seed       TEXT    NOT NULL,
    sort_order        INTEGER NOT NULL,
    version           TEXT    NOT NULL DEFAULT 'V1'
);

COMMENT ON TABLE  highlights                    IS '12 种诊断高光类型定义表，单源真相：触发逻辑、解读路径、报告语言种子均在此维护';
COMMENT ON COLUMN highlights.code              IS 'highlight 唯一标识，格式 add-{cv1|cv2|g}-{方向}，与 Agent A 输出的 highlights[].code 对应';
COMMENT ON COLUMN highlights.layer             IS '层级：1=维度内交叉验证(cv1)，2=维度间交叉验证(cv2)，3=全局复合诊断(g)';
COMMENT ON COLUMN highlights.involved_dims     IS '涉及的维度，单维如 D1，跨维如 D2D3，全局用 global';
COMMENT ON COLUMN highlights.severity          IS '严重程度：high=需锐度呈现，moderate=中度，info=提示级（正向高光常用）';
COMMENT ON COLUMN highlights.is_positive       IS '是否为正向高光；true 时报告以肯定语气呈现，不带负向解读';
COMMENT ON COLUMN highlights.name_cn           IS '中文显示名，用于管理后台和日志可读性';
COMMENT ON COLUMN highlights.trigger_condition IS 'Agent A 触发该 highlight 的精确条件，面向开发者，含题号与得分阈值';
COMMENT ON COLUMN highlights.interp_path       IS 'Agent B 理解层：解读路径，说明该模式的心理机制与解读逻辑';
COMMENT ON COLUMN highlights.report_seed       IS 'Agent B 写作起点：报告语言种子，直接指向用户可感知的行为描述';
COMMENT ON COLUMN highlights.sort_order        IS '排列顺序，与 Agent A 中 highlights 数组的追加顺序一致';
COMMENT ON COLUMN highlights.version           IS '数据版本号，迭代时更新，当前为 V1';

-- 后期手动添加的冗余 id 列（PK 实际为 code，此列不参与业务逻辑）：
-- 补建 + COMMENT，幂等可重复执行
ALTER TABLE highlights ADD COLUMN IF NOT EXISTS id INTEGER;
COMMENT ON COLUMN highlights.id IS '【冗余列】后期手动添加的自增 ID，可空。主键实际为 code（语义主键），此列不参与业务逻辑，仅作管理后台展示兼容';

-- ── 层级 1：维度内交叉验证（within-dimension）────────────────────────────────

-- [1] add-cv1-behavior-gap · D1 · 认知行为分裂 · moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv1-behavior-gap',
  1, 'D1', 'moderate', false, '认知行为分裂',
  'D1-Q04 得分与 D1-Q05 得分方向相反（一题≥+1，另一题≤-1）——"想象情境如何处理"与"真实压力下的行为"出现对称翻转',
  '用户在"应该怎么做"和"实际会怎么做"之间存在落差。脑子里有一套健康应对的答案，但真实压力来了，行为走了另一条路——不是撒谎，是应激状态下的真实分裂。',
  '「你脑子里有一套"我应该这样处理"的标准答案，但身体记住的是另一套。当他真的冷下来的时候，你不是先去坦白沟通，而是先打开他的朋友圈或步数。这不是矛盾，这只是说明真实的你比你以为的更敏感。」',
  1, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [2] add-cv1-pattern-blind · D2 · 模式觉察缺口 · high
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv1-pattern-blind',
  1, 'D2', 'high', false, '模式觉察缺口',
  'D2-Q01 得分≥+1（单次越界事件能响应）且 D2-Q05 得分≤-1（面对持续性贬低选择忍耐）',
  '用户对"一次越界事件"有清晰识别和响应能力，但越界变成持续模式后开始失语。能区分"事件"，区分不了"模式"——不是不知道难受，是不知道这种连续性的难受值得说。',
  '「你能在他翻你手机那一刻直接告诉他"这让我不舒服"，但当他每周都用刺人的方式开你玩笑时，你的回应反而变成了一种沉默的等待。你不是不知道难受，你只是把"每天的"难受归类成了"一段关系本来就有的损耗"。」',
  2, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [3] add-cv1-pressure-collapse · D3 · 压力表达崩塌 · moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv1-pressure-collapse',
  1, 'D3', 'moderate', false, '压力表达崩塌',
  'D3-Q01 得分≥+1（小摩擦能软启动表达）且 D3-Q05 得分＜0（重大分歧场景下表达崩塌）',
  '用户在日常小摩擦中有良好的表达能力，但在重大分歧下被压力击穿，滑入指责或沉默。这是高压下的应激退行，不是"不会表达"——是情绪调节带宽问题。',
  '「他不收拾房间、答应陪你却开始打游戏——这种小事你能说得很漂亮："刚才那样让我有点被冷落"。但当你们在更大的事情上意见相左——城市、未来、什么时候结婚——你就回到了"你这个人就是自私"。不是你不会表达，是压力把你拽回了更熟的反应。」',
  3, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- ── 层级 2：维度间交叉验证（cross-dimension）─────────────────────────────────

-- [4] add-cv2-aggr-passive · D2D3 · 攻守错位 · high
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv2-aggr-passive',
  2, 'D2D3', 'high', false, '攻守错位',
  'D2-Q01 得分=-2（真实边界越界选择沉默，怕引发矛盾）且 D3-Q01 得分=-2（小摩擦选择压抑直至积累爆发）——对低风险小事有情绪出口，对高风险真实侵害反而失声',
  '对越界行为没有响应（边界模糊）+ 对日常小摩擦直接攻击——真正的问题说不出口，压力积累后在小事上爆发。外显强硬，内里无力。只敢对低风险目标使用攻击，底层是不安全感。',
  '「你以为自己的脾气来得很快——他没及时回消息，你立刻就能开口指责。但仔细看，你真的会发火的事都不是大事。当他做了那些更应该被指出来的事，你反而沉默了。攻击的不是底气，只是它的代价更低。」',
  4, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [5] add-cv2-anxious-disguise · D1D5 · 焦虑式回避伪装 · moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv2-anxious-disguise',
  2, 'D1D5', 'moderate', false, '焦虑式回避伪装',
  'D1-Q02 得分=-2（三天无联系极度焦虑、想联系又怕打扰）且 D5-Q05 得分=-2（几乎不主动分享日常，觉得各自生活应分开）',
  '对方不主动联系时内心焦虑，但自己也不主动分享——用"我们各忙各的"掩盖"我其实很在乎"。被迫的傲娇，不是真的不想说话，是怕主动显得自己更需要、更掉价、更容易被伤害。',
  '「下班后你们的对话框里只有"到了吗""睡了""晚安"。你嘴上跟朋友说"我们就是这样的相处模式"，但你下午五点没收到他消息时，真实状态是反复点亮屏幕。你不是不想说话，你只是不想做先开口的那一个。」',
  5, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [6] add-cv2-self-dissolve · D2D5 · 自我溶解风险 · high
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-cv2-self-dissolve',
  2, 'D2D5', 'high', false, '自我溶解风险',
  'D2-Q02 得分≤-1（恋爱后自我让步严重）且 D5-Q01/Q02/Q03 中至少 2 题得分≤-1（表达直接性整体偏低）',
  '自我维持能力低 + 日常表达含蓄——两者叠加，容易在关系中被慢慢吞噬。最危险的是过程中没有明确"这一刻应该停下"的信号。收尾建议段应优先给出"先练习日常小事直接表达"的起点。',
  '「你的朋友最近都说很少看到你了。你的生活半径以肉眼可见的速度，从一个城市缩到了你们两个人的小屋。当心里有不舒服的事，你也只是把笔记顺手转发给他，期待他懂。这两件事单独看都还行，合在一起就是另一件事——你正在被慢慢溶进他里面，而你自己还没意识到。」',
  6, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- ── 层级 3：全局复合诊断（global）───────────────────────────────────────────

-- [7] add-g-self-blame · global · 跨情境自我攻击 · high
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-self-blame',
  3, 'global', 'high', false, '跨情境自我攻击',
  'D1-Q01 选 D + D2-Q05 选 D + D3-Q03 选 D 中至少 2 项成立——在依恋、边界、冲突三个不同情境中均以自我归因作为第一反应',
  '用户在多个不同情境（收不到回复、被持续贬低、刚吵完架）里，第一反应都是"是不是我哪里做错了"。这不是"反思"，是稳定的自我攻击操作系统。看似觉察，实则把伤害你的事内化为你的过错，让对方责任消失。',
  '「他没回消息，你想"是我刚才说错了什么"；他在朋友面前拿你开玩笑，你想"是不是我太敏感"；你们刚吵完架，你想"我是不是哪里不够好"。三件完全不同的事，你的第一反应都是同一个——把矛头指向自己。这不是你比别人更会反省，这是一个习惯，而且它不为你服务。」',
  7, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [8] add-g-pa-pursuer · D3 · 追逃循环（追方）· moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-pa-pursuer',
  3, 'D3', 'moderate', false, '追逃循环（追方）',
  'D3-Q06 选 C（score_meta.pursue_avoid = "pursue"）——在历史冲突中主要扮演"追"的角色',
  '在追逃循环中扮演"追"的角色。停不下来，是因为停下来意味着直面"对方可能就是不在乎"的可能性。追的不是答案，是即时的安全感。',
  '「他越冷你越追，这个动作你重复过不止一次。你以为你在解决问题——"非要逼出一个回应"——但你逼出来的回应从来没让你真正放松过。因为你追的不是答案，是这一刻不要再悬着。停下来很难，因为停下来意味着你要面对一个更难的问题：他可能本来就没那么想回。」',
  8, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [9] add-g-pa-avoider · D3 · 追逃循环（逃方）· moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-pa-avoider',
  3, 'D3', 'moderate', false, '追逃循环（逃方）',
  'D3-Q06 选 D（score_meta.pursue_avoid = "avoid"）——在历史冲突中主要扮演"逃"的角色',
  '在追逃循环中扮演"逃"的角色。感受到压力时第一反应是关闭、拉开距离。逃的一方不是冷漠，是过载——关闭沟通是把所有进来的东西先拦在外面。',
  '「你不是冷漠的人。你只是当对方声音再大一点、再凑近一点的时候，系统就过载了。沉默、出门、打游戏到睡前——这不是惩罚她，这是你给自己买时间。但你没看到的是，你买的时间是用她那一晚的崩溃换的。你回来时关系不是回到原点，是又少了一截。」',
  9, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [10] add-g-pa-aware · D3 · 追逃觉察突破者 · info ✦positive
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-pa-aware',
  3, 'D3', 'info', true, '追逃觉察突破者',
  'D3-Q06 选 A（pursue_avoid_role = "aware_breaker"）——能主动觉察追逃循环并推动双方跳出',
  '用户能觉察到追逃动态并主动打破它，是冲突处理中的正向标志，值得作为优势明确点出。识别意味着用户已经在元认知层把"我在追/在逃"和"我"分开了——动作还可能发生，但有一个观察者在场。',
  '「在大多数关系里，追的人不知道自己在追，逃的人不觉得自己在逃。你不一样——你能看到这个循环正在发生，然后选择不再走完。这种识别不是心理学知识，是你在过去某段关系里掉进去过、爬出来过、记下来了。它的稀缺度比你想象的高。」',
  10, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [11] add-g-stable · global · 稳定型人格信号 · info ✦positive
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-stable',
  3, 'global', 'info', true, '稳定型人格信号',
  'D1/D2/D3/D5 共 24 题中得分≥+1 的题目占比≥60%——整体呈现稳定的健康反应模式',
  '用户在多维度展现稳定的健康反应模式。稳定本身就是特点，且被严重低估——伴侣不需要花精力解码你今天的状态，可以把精力放在更重要的事上。需让稳定型用户感到自己被看见，而不是觉得报告"没我什么事"。',
  '「你测完可能会觉得"好像没看到什么戏剧性的东西"，但请慢一秒——稳定不是没特点，稳定本身就是。当大多数人的关系是一场反复的解码——他今天为什么这样、我今天该怎么回——和你在一起的人不用做这件事。你给他的不是激情，是节省下来的认知带宽。这件事的价值，他可能要过几段关系才会真正知道。」',
  11, 'V1'
) ON CONFLICT (code) DO NOTHING;

-- [12] add-g-love-blind · D4 · 爱语自我盲区 · moderate
INSERT INTO highlights (code, layer, involved_dims, severity, is_positive, name_cn, trigger_condition, interp_path, report_seed, sort_order, version)
VALUES (
  'add-g-love-blind',
  3, 'D4', 'moderate', false, '爱语自我盲区',
  'D4-Q01 主动选择（declared）与 D4 场景题归一化后 top1 不一致（aligned = false）',
  '用户主观认为自己最被某种爱的语言打动，但具体场景题选出来的偏好是另一种。对自己需求有一层"应该的"叙事，但身体诚实地选择了另一种。这是测评能给的、用户不靠测评得不到的东西，单独给段落。',
  '「你以为自己最被[declared对应语言]打动，但具体场景题里你的选择诚实得多——你真正放下心来的，是[normalized_top1对应语言]的时刻。被夸是头脑里的浪漫，被照顾是身体里的踏实。这两种你都需要，但你之前可能误读了自己的优先级。」',
  12, 'V1'
) ON CONFLICT (code) DO NOTHING;
