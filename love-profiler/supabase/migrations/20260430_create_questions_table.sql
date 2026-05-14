CREATE TABLE IF NOT EXISTS questions (
    question_id   TEXT PRIMARY KEY,
    dimension     TEXT NOT NULL,
    signal_code   TEXT NOT NULL,
    signal_name   TEXT NOT NULL,
    question_type TEXT NOT NULL,
    stem          TEXT NOT NULL,
    option_a      TEXT,
    option_b      TEXT,
    option_c      TEXT,
    option_d      TEXT,
    option_e      TEXT,
    score_a       TEXT,
    score_b       TEXT,
    score_c       TEXT,
    score_d       TEXT,
    score_e       TEXT,
    sort_order    INTEGER NOT NULL,
    version       TEXT DEFAULT 'V2',
    notes         TEXT
);

-- D1 依恋行为 (6题)
INSERT INTO questions VALUES
('D1-Q01','依恋','S1','不确定性解读','强度型',
 '你正在等对方回消息，发现他「正在输入…」后突然消失，消息迟迟不来，你的第一反应是？',
 '没什么，他可能临时有事，等等就好',
 '有点好奇他在忙什么，但不会追问',
 '有点担心，忍不住回看聊天记录找原因',
 '开始焦虑，觉得是不是自己说错了什么',
 NULL,
 '+2','+1','-1','-2',NULL,
 1,'V2','S1 测对方「无回应」时的默认解读方向')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D1-Q02','依恋','S2','距离容忍度','强度型',
 '你们已经三天没怎么联系，对方偶尔发来一个表情，你感觉怎么样？',
 '感觉很好，各自有各自的节奏',
 '有点思念，但能接受这种状态',
 '有些不安，担心感情在降温',
 '非常焦虑，想主动联系但又怕打扰',
 NULL,
 '+2','+1','-1','-2',NULL,
 2,'V2','S2 测能忍受多久没有联系而不触发焦虑')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D1-Q03','依恋','S3','第三者敏感度','强度型',
 '你刷到对方朋友圈，发现有个陌生异性频繁点赞评论，你的反应是？',
 '不在意，对方有自己的社交圈很正常',
 '留意了一下，但没放在心上',
 '有点不舒服，开始查这个人的主页',
 '很不安，忍不住问对方那是谁',
 NULL,
 '+2','+1','-1','-2',NULL,
 3,'V2','S3 测对潜在竞争者的情绪反应强度')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D1-Q04','依恋','S4','激活后表达','强度型',
 '对方最近突然变得冷淡，消息回复变少，你通常会怎么做？',
 '直接和他说：我最近感觉你有点疏远我，我们谈谈吧',
 '找个轻松的话题试探，看他反应',
 '等他主动，自己默默担心',
 '表现出更多关心或主动联系，但心里越来越焦虑',
 NULL,
 '+2','+1','-1','-2',NULL,
 4,'V2','S4 核心题：依恋系统激活后的行为输出')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D1-Q05','依恋','S4','激活后表达','强度型',
 '和对方约好的计划，他临时取消了，你通常的处理方式是？',
 '直接表达失望：这次我很失望，以后麻烦提前说',
 '表示理解，内心有些不开心但没说',
 '嘴上说没事，但心里一直记着这件事',
 '开始担心他是不是不想见自己了，反复找理由解释',
 NULL,
 '+2','+1','-1','-2',NULL,
 5,'V2','S4 验证题：换情境复测，对抗社会期望污染')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D1-Q06','依恋','S5','安全感来源','强度型',
 '在一段关系里，什么样的相处方式最让你有「被坚定选择」的踏实感？',
 '他主动分享生活细节，让我觉得被纳入他的世界',
 '我们彼此保有空间，但关键时刻都在',
 '他对我很好，但我总担心这种好会突然消失',
 '只有他主动找我、安抚我，我才能暂时安心',
 NULL,
 '+2','+1','-1','-2',NULL,
 6,'V2','S5 测安全感的来源机制')
ON CONFLICT (question_id) DO NOTHING;

-- D2 边界意识 (6题)
INSERT INTO questions VALUES
('D2-Q01','边界','S1','越界识别','强度型',
 '你不在时，对方坦白偷看了你的手机，你的反应是？',
 '直接表达：这不可以，请你解释一下，以后不能这样',
 '有些不舒服，问他为什么这样做',
 '心里不开心，但觉得在关系里这很正常，没有说',
 '心里难受但不敢说，担心提了会闹矛盾',
 NULL,
 '+2','+1','-1','-2',NULL,
 7,'V2','S1 核心题：对单次越界能否清晰响应')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D2-Q02','边界','S2','自我维持','强度型',
 '恋爱后，你的个人时间、朋友圈、兴趣爱好的状态是？',
 '完全保持，恋爱是我生活的一部分，不是全部',
 '有些调整，但核心还在',
 '大部分让步了，总觉得对方比自己重要',
 '几乎全让步了，生活重心完全转移到关系上',
 NULL,
 '+2','+1','-1','-2',NULL,
 8,'V2','S2 测恋爱后自我身份的保存程度')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D2-Q03','边界','S3','异性相处共识','强度型',
 '对于伴侣与异性朋友的相处方式，你们的态度是？',
 '信任为基础，不需要额外的报备或限制',
 '大多信任，偶尔确认一下',
 '需要明确规则，否则会有点不安',
 '希望知道所有细节，否则会持续焦虑',
 NULL,
 '+2','+1','-1','-2',NULL,
 9,'V2','S3 测对伴侣异性社交的边界设定')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D2-Q04','边界','S4','付出对等','强度型',
 '在关系里，你们的情感付出和日常照顾是否相对平衡？',
 '基本平衡，有时我多有时他多，但整体我们都会提出来',
 '有些不均衡，但偶尔会提出来',
 '明显不均衡，我付出更多，但觉得这是正常的',
 '我几乎全部承担，但说了会被说太计较',
 NULL,
 '+2','+1','-1','-2',NULL,
 10,'V2','S4 测付出失衡时的觉察与表达意愿')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D2-Q05','边界','S1','越界识别','强度型',
 '对方在争吵中翻旧账、持续贬低你，你通常的反应是？',
 '当场说清楚：这种方式我不接受，我们就事论事',
 '表示不喜欢，但说得不够明确',
 '选择沉默，等他消气后再说',
 '接受了，心里认为也许是自己的问题',
 NULL,
 '+2','+1','-1','-2',NULL,
 11,'V2','S1 验证题：对持续性伤害能否响应')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D2-Q06','边界','S5','隐私空间','强度型',
 '你认为健康的恋爱关系应该是？',
 '两个人都有独立的私人空间，不强制透明',
 '基本信任透明，但保留小部分个人空间',
 '应该尽量开放，保密会让对方不安心',
 '情侣就应该完全透明，有秘密就是不信任',
 NULL,
 '+2','+1','-1','-2',NULL,
 12,'V2','S5 测对隐私与透明度的基本信念')
ON CONFLICT (question_id) DO NOTHING;

-- D3 冲突处理 (6题)
INSERT INTO questions VALUES
('D3-Q01','冲突','S1','表达方式','强度型',
 '对方做了让你不舒服的小事，你通常会怎么开口？',
 '直接说清楚：刚才那件事，我感觉……是因为……',
 '找个时机说，但措辞比较迂回',
 '用冷淡或沉默暗示，希望对方自己发现',
 '忍着不说，等积累到一定程度再爆发',
 NULL,
 '+2','+1','-1','-2',NULL,
 13,'V2','S1 核心题：小摩擦时的表达风格')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D3-Q02','冲突','S2','修复主动性','强度型',
 '你们冷战了，双方都没有主动，通常会怎么发展？',
 '我会主动打破，觉得冷战比解决问题更浪费时间',
 '我会找机会试探，但不一定是第一个开口',
 '等对方先主动，我很难迈出第一步',
 '会一直僵着，直到外部事件迫使我们开口',
 NULL,
 '+2','+1','-1','-2',NULL,
 14,'V2','S2 测冷战后的主动修复意愿')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D3-Q03','冲突','S3','责任归因','强度型',
 '争吵冷静下来后，你通常怎么看这次冲突的根源？',
 '双方都有责任，我主动想想自己能改进什么',
 '觉得大部分是他的问题，但我也有一点',
 '主要是他的问题，但为了和好我可能先低头',
 '完全是他的问题，但我说了也没用，算了',
 NULL,
 '+2','+1','-1','-2',NULL,
 15,'V2','S3 测冲突后的责任归因模式')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D3-Q04','冲突','S4','情绪淹没管理','强度型',
 '你感到情绪快要失控时，你怎么处理？',
 '主动说：我现在状态不好，需要冷静一下，稍后再谈',
 '尽量控制，但有时会带出来',
 '通常会直接爆发，事后后悔',
 '压下去，用沉默回避，但情绪一直都在',
 NULL,
 '+2','+1','-1','-2',NULL,
 16,'V2','S4 测情绪淹没阈值下的自我调节能力')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D3-Q05','冲突','S1','表达方式','强度型',
 '你们在关于未来的重大问题上出现了分歧，你怎么处理？',
 '认真说清楚各自的立场和需求，找到共同点',
 '表达了自己的看法，但说得不够完整',
 '表面顺着对方，心里保留意见',
 '回避这个话题，不想为此引发矛盾',
 NULL,
 '+2','+1','-1','-2',NULL,
 17,'V2','S1 验证题：高压场景（未来分歧）下的表达韧性')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D3-Q06','冲突','S5','追逃模式','强度型',
 '回顾你经历过的摩擦或争吵，你在其中更多扮演的是？',
 '会主动觉察我们的模式，推动双方跳出追/逃循环',
 '没有固定模式，情况不同角色也不同',
 '主要是「追」的那方：想解决、想连接、想被回应',
 '主要是「逃」的那方：需要空间、回避冲突、用沉默应对',
 NULL,
 '+2','+1','-2','-2',NULL,
 18,'V2','S5 特殊题：C/D同分-2但须标记pursue_avoid亚型')
ON CONFLICT (question_id) DO NOTHING;

-- D4 情感需求 (6题) ── 爱的语言型
INSERT INTO questions VALUES
('D4-Q01','情感','ALL','五语均测','爱的语言型',
 '在某个疲惫的夜晚，你最希望伴侣能做什么让你感到被爱？',
 '主动说：你今天辛苦了，我很感激你一直这样',
 '坐下来陪着你，什么也不用做，就是在你身边',
 '在你桌上放一个你最近想要的小东西',
 '悄悄把家务都做完，让你不用操心任何事',
 '从背后抱着你，或者帮你按摩肩膀',
 'T1+2','T2+2','T3+2','T4+2','T5+2',
 19,'V2','全五语开放选：基线偏好探测')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D4-Q02','情感','T1/T4','言语/服务','爱的语言型',
 '关系稳定下来后，什么样的日常最让你觉得「我们感情很好」？',
 '他经常夸我、肯定我做的事',
 '他主动帮我处理我头疼的事情（修东西/陪我去医院等）',
 '每隔一段时间会一起认真规划一次约会',
 '他随口的一个小拥抱或者牵手',
 NULL,
 'T1+2','T4+2','T2+1','T5+1',NULL,
 20,'V2','T1/T4对照；C=T2+1 D=T5+1 副得分')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D4-Q03','情感','T2/T5','精心/接触','爱的语言型',
 '你心情低落时，什么样的陪伴最有效？',
 '他关掉手机，认真听我说一个小时',
 '他拉住我的手，或者把我抱得紧紧的',
 '他跟我说：你不是一个人，我支持你',
 '他帮我安排好接下来的事，让我不用担心',
 NULL,
 'T2+2','T5+2','T1+1','T4+1',NULL,
 21,'V2','T2/T5对照；C=T1+1 D=T4+1 副得分')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D4-Q04','情感','T3/T4','惊喜/服务','爱的语言型',
 '哪种惊喜最能让你感到幸福？',
 '他记住你随口提过的小细节，某天突然实现了',
 '他在你最忙的时候，把所有后勤都悄悄安排好了',
 '他专门为你策划了一次只有你们两个的特别约会',
 '他在纪念日前写了一封信，说了很多平时不说的话',
 NULL,
 'T3+2','T4+2','T2+1','T1+1',NULL,
 22,'V2','T3/T4对照；C=T2+1 D=T1+1 副得分')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D4-Q05','情感','T1/T2','言语/精心','爱的语言型',
 '吵架和好后，哪种方式最让你感到被修复？',
 '他主动道歉并说清楚自己哪里错了',
 '他说：我们去吃你喜欢的，什么都别想了',
 '他直接拥抱你，不说话',
 '他帮你做了一件你一直拖着的事情',
 NULL,
 'T1+2','T2+2','T5+1','T4+1',NULL,
 23,'V2','T1/T2对照；C=T5+1 D=T4+1 副得分')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D4-Q06','情感','T3/T5','惊喜/接触','爱的语言型',
 '对你来说，哪种「我爱你」的表达方式最真实？',
 '他记得你某天说的某句话，后来悄悄为你做到了',
 '他习惯摸摸你的头，或者走路时不自觉牵你的手',
 '他经常明确说出「我选择你」这类话',
 '他在生活细节上替你想好了，让你不用操心',
 NULL,
 'T3+2','T5+2','T1+1','T4+1',NULL,
 24,'V2','T3/T5对照；C=T1+1 D=T4+1 副得分')
ON CONFLICT (question_id) DO NOTHING;

-- D5 风格表达 (6题)
INSERT INTO questions VALUES
('D5-Q01','风格','S1','直接性','双子面型',
 '遇到意见不同的时候，你更倾向于？',
 '直接说出我的看法，就事论事',
 '先听对方说完，再表达自己',
 '通常选择顺着，避免正面冲突',
 '沉默或转移话题，不想争论',
 NULL,
 '+2','+1','-1','-2',NULL,
 25,'V2','S1 直接性：意见表达场景')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D5-Q02','风格','S1','直接性','双子面型',
 '你在新认识一个人时，通常怎么介绍自己？',
 '直接说我做什么、想什么、喜欢什么',
 '根据对方的问题来说，不主动多说',
 '比较笼统，不太习惯直接表达喜好',
 '很少主动介绍，等别人先了解我',
 NULL,
 '+2','+1','-1','-2',NULL,
 26,'V2','S1 直接性：自我表露场景')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D5-Q03','风格','S1','直接性','双子面型',
 '对方说了让你不开心的话，你会？',
 '当场说：这句话让我不舒服，你是这个意思吗？',
 '稍后找合适时机说',
 '不说，但内心记住了',
 '完全不说，可能就这样过了',
 NULL,
 '+2','+1','-1','-2',NULL,
 27,'V2','S1 直接性：负面反馈场景')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D5-Q04','风格','S2','分享欲','双子面型',
 '你刷到很有意思的内容时，第一反应是？',
 '马上转给几个人，想一起聊',
 '存下来，如果话题合适才分享',
 '自己看完就算了，不太想分享',
 '从来不分享，觉得没必要',
 NULL,
 '+2','+1','-1','-2',NULL,
 28,'V2','S2 分享欲：内容传播冲动')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D5-Q05','风格','S2','分享欲','双子面型',
 '在感情里，你通常怎么分享自己的日常？',
 '主动讲，细节也说，喜欢让对方知道我的生活',
 '对方问才说，不太主动',
 '分享比较少，觉得日常没什么好说的',
 '几乎不分享，觉得各自的生活应该分开',
 NULL,
 '+2','+1','-1','-2',NULL,
 29,'V2','S2 分享欲：日常生活分享习惯')
ON CONFLICT (question_id) DO NOTHING;

INSERT INTO questions VALUES
('D5-Q06','风格','S2','分享欲','双子面型',
 '你遇到高兴或难过的事情时，更想做什么？',
 '第一时间告诉对方，或发朋友圈',
 '情绪稳定后再说，或选择性分享',
 '通常自己消化，不太想跟人说',
 '完全自己处理，不分享个人情绪',
 NULL,
 '+2','+1','-1','-2',NULL,
 30,'V2','S2 分享欲：情绪事件分享意愿')
ON CONFLICT (question_id) DO NOTHING;

-- =============================================================================
-- 字段 COMMENT（语义权威说明，幂等执行）
-- =============================================================================

COMMENT ON TABLE  questions               IS '30 题题库。一行=一道题；30 题分布在 5 个维度（D1-D5），每维 6 题。题库版本由 version 字段管理';

COMMENT ON COLUMN questions.question_id   IS '题目唯一 ID，格式 {维度代码}-Q{两位序号}，如 D1-Q01 ~ D5-Q06';
COMMENT ON COLUMN questions.dimension     IS '维度中文名：依恋 / 边界 / 冲突 / 情感 / 风格，对应 D1~D5';
COMMENT ON COLUMN questions.signal_code   IS '维度内细化信号代码：S1-S5（5 个心理信号），D4-Q01 用 ALL（基线五语均测）';
COMMENT ON COLUMN questions.signal_name   IS '信号中文名，如「不确定性解读」「越界识别」「追逃模式」等；面向开发者';
COMMENT ON COLUMN questions.question_type IS '题型：强度型 / 爱的语言型 / 双子面型，决定 Agent A 的打分逻辑';
COMMENT ON COLUMN questions.stem          IS '题干文本，前端原样展示';
COMMENT ON COLUMN questions.option_a      IS '选项 A 文本';
COMMENT ON COLUMN questions.option_b      IS '选项 B 文本';
COMMENT ON COLUMN questions.option_c      IS '选项 C 文本';
COMMENT ON COLUMN questions.option_d      IS '选项 D 文本';
COMMENT ON COLUMN questions.option_e      IS '选项 E 文本，仅 D4-Q01 使用（五语均测），其他题为 NULL';
COMMENT ON COLUMN questions.score_a       IS '选项 A 的分值字符串。强度型用 +2/+1/-1/-2，爱的语言型用 T1+2 / T3+2 等指向爱语类型';
COMMENT ON COLUMN questions.score_b       IS '选项 B 的分值字符串，含义同 score_a';
COMMENT ON COLUMN questions.score_c       IS '选项 C 的分值字符串。注意 D3-Q06 的 C 含 score_meta={"pursue_avoid":"pursue"} 追型标记';
COMMENT ON COLUMN questions.score_d       IS '选项 D 的分值字符串。注意 D3-Q06 的 D 含 score_meta={"pursue_avoid":"avoid"} 逃型标记';
COMMENT ON COLUMN questions.score_e       IS '选项 E 的分值字符串，仅 D4-Q01 使用';
COMMENT ON COLUMN questions.sort_order    IS '题目展示顺序 1~30，前端按此顺序播放';
COMMENT ON COLUMN questions.version       IS '题库版本号，当前 V2。修订题目时升级版本，answer_package_builder 会带上 question_set_version';
COMMENT ON COLUMN questions.notes         IS '题目设计意图说明，仅供开发/运营查阅，不向用户/AI 暴露';
