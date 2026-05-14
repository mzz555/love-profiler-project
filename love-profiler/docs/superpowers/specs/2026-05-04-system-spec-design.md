# 恋爱侧写 · 系统规格文档 v1.0

> 本文档为「恋爱侧写」抖音小程序的后端系统规格，涵盖架构设计、数据模型、Python 计算层、Agent B 接口、API 接口及完整题库与人物映射表。面向开发团队与产品团队，是系统实现的单一真相源。

**版本：** v1.0 · 2026-05-04  
**状态：** 已审定

---

## 目录

1. [产品概述与整体架构](#第一章产品概述与整体架构)
2. [数据模型](#第二章数据模型)
3. [Python 计算层规格](#第三章python-计算层规格)
4. [Agent B 接口规格](#第四章agent-b-接口规格)
5. [API 接口定义](#第五章api-接口定义)
- [附录 A：完整 30 题题库](#附录-a完整-30-题题库)
- [附录 B：32 人物完整映射表](#附录-b32-人物完整映射表)

---

## 第一章：产品概述与整体架构

### 1.1 产品定义

「恋爱侧写」是一款运行于抖音平台的小程序，用户完成 30 道固定选择题后，系统自动生成一份 1200-1800 字的恋爱人格测评报告。报告从依恋模式、边界意识、冲突处理、情感需求、风格表达五个维度刻画用户的关系底色，并映射至 16 种经典文学人物原型，通过看激励视频广告或付费解锁。

**核心价值主张：** 让用户在 3 分钟内完成测评、15-30 秒内拿到报告，并获得一段「想截图分享」的文学映射卡片。

---

### 1.2 架构核心决策：Python 代码层替代 Agent A

原方案由 Agent A（LLM）负责打分计算，现改为 Python 代码层执行全部确定性计算，Agent B（LLM）仅负责报告文案生成。

**五条核心优点：**

| 优点 | 原方案（Agent A 为 LLM） | 新方案（Python 代码层） |
|------|--------------------------|------------------------|
| 准确性 | LLM 有小概率算错，无法根治 | if-else 加减乘除，单元测试 100% 覆盖 |
| 速度 | Agent A 生成 JSON 需 30-60 秒 | 代码层计算 < 100 毫秒 |
| 成本 | 两次 LLM 调用（A+B） | 仅一次 LLM 调用（B） |
| 可维护性 | 改规则需改 prompt 并做回归测试 | 改一行代码，单元测试即时验证 |
| 可追溯性 | LLM 输出有 5% 概率结构漂移 | 所有中间结果结构化入库 |

---

### 1.3 完整数据流

```
用户填写 30 题（前端本地逐题展示，一答一问）
    ↓
POST /quiz/submit  →  后端接收 30 题答案 JSON
    ↓
【第 1 层】answers_json 存入 assessments 表（原始答题永久保留）
    ↓
【第 2 层】Python 计算层（替代原 Agent A）
    ├─ 模块 1：五维度得分计算
    ├─ 模块 2：维度内交叉验证（3 条规则）
    ├─ 模块 3：维度间交叉验证（3 条规则）
    ├─ 模块 4：全局复合诊断（4 个标记）
    ├─ 模块 5：16 型分型映射 + 文学人物注入（查 literary_mappings 表）
    └─ 模块 6：关键诊断洞察提取
    输出：完整 Python dict → 存入 assessments.diagnosis_json
    assessment.status 更新为 "analyzed"
    ↓
用户观看激励广告 → POST /unlock/ad → 解锁
    ↓
GET /result  →  触发 Agent B
    ↓
【第 3 层】Agent B（LLM）接收 diagnosis_json，生成报告文案
    输出：report_text（markdown 全文）+ report_json（分段结构）
    存入 assessments.report_text / report_json
    assessment.status 更新为 "complete"
    ↓
前端流式渲染报告（重复调用直接返回缓存）
```

---

### 1.4 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | 抖音小程序（TTML / TTSS / JS） | 字节跳动开发者工具 |
| 后端 | FastAPI + SQLAlchemy | Python 异步框架 |
| 数据库 | Supabase PostgreSQL | 本地 CLI 开发（localhost:54322），REST API（localhost:54321） |
| LLM | 豆包（字节跳动火山引擎） | 模型：doubao-seed-2-0-pro，异步调用 |
| 限流 | slowapi | 按 IP 限流 |
| 认证 | JWT（HS256） | 抖音 openid 换 token |

---

### 1.5 版本字段追踪策略

系统中所有可迭代的组件均有独立版本字段，确保历史数据可溯源、A/B 测试可分析：

| 版本字段 | 存储位置 | 示例值 | 用途 |
|---------|---------|--------|------|
| `question_set_version` | assessments 表 | `V2` | 识别用户做的是哪版题库 |
| `algorithm_version` | assessments 表 | `v1.0` | 识别用的是哪版打分算法 |
| `prompt_version` | assessments 表 | `v2.0` | 识别 Agent B 用的是哪版 prompt |
| `model_name` | assessments 表 | `doubao-seed-2-0-pro` | 识别用的是哪个模型 |

---

## 第二章：数据模型

### 2.1 表结构总览

系统共 5 张表，其中 4 张现有表在原有基础上修改，1 张新增：

| 表名 | 管理方式 | 变更 |
|------|---------|------|
| `users` | SQLAlchemy | 新增 `gender` 字段 |
| `assessments` | SQLAlchemy | 新增 5 个版本追踪字段 |
| `orders` | SQLAlchemy | 无变更 |
| `questions` | Supabase migrations | 无变更 |
| `literary_mappings` | Supabase migrations | **新增表** |

**三层数据独立性原则：**
- `answers_json`（原始答题）→ `diagnosis_json`（计算结果）→ `report_json`（报告文案）
- 任意一层数据可从上一层重建，互不依赖

---

### 2.2 users 表

```sql
-- 现有字段（保留）
id          INTEGER PRIMARY KEY
openid      VARCHAR(64) UNIQUE NOT NULL
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()

-- 新增字段
gender      VARCHAR(8) NOT NULL DEFAULT 'other'
            -- 取值：'M'（男）| 'F'（女）| 'other'
            -- 用途：Agent B 默认引用与用户同性别的文学人物
```

---

### 2.3 assessments 表

```sql
-- 现有字段（保留，含义不变）
id               INTEGER PRIMARY KEY
user_id          INTEGER NOT NULL REFERENCES users(id)
session_id       VARCHAR(64) UNIQUE NOT NULL
signals          TEXT NOT NULL DEFAULT '{}'
personality_type VARCHAR(32)         -- 16 型代码，如 'A-BL-P'
report_text      TEXT                -- Agent B 生成的 markdown 全文
summary          TEXT
status           VARCHAR(16) NOT NULL DEFAULT 'pending'
                 -- 流转：pending → analyzed → complete
mode             VARCHAR(16) NOT NULL DEFAULT 'quiz'
dimension_scores TEXT                -- D1-D5 维度分数（冗余字段，diagnosis_json 内已含）
answers_json     TEXT                -- 用户原始 30 题答案 JSON
diagnosis_json   TEXT                -- Python 计算层完整输出 JSON
report_json      TEXT                -- Agent B 完整输出 JSON（含 sections 分段结构）
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()

-- 新增字段（版本追踪）
algorithm_version   VARCHAR(16)     -- 打分算法版本，如 'v1.0'
question_set_version VARCHAR(8)     -- 题库版本，如 'V2'
prompt_version      VARCHAR(16)     -- Agent B prompt 版本，如 'v2.0'
model_name          VARCHAR(64)     -- LLM 模型名，如 'doubao-seed-2-0-pro'
token_usage         TEXT            -- JSON：{prompt_tokens, completion_tokens, total_tokens}
```

**status 流转规则：**

```
pending    → 测评创建，用户还未提交答题
analyzed   → Python 计算层执行完成，diagnosis_json 已写入
complete   → Agent B 生成报告完成，report_json / report_text 已写入
```

---

### 2.4 orders 表（无变更）

```sql
id            INTEGER PRIMARY KEY
user_id       INTEGER NOT NULL REFERENCES users(id)
assessment_id INTEGER NOT NULL REFERENCES assessments(id)
out_trade_no  VARCHAR(64) UNIQUE NOT NULL   -- 商户侧幂等键
amount        INTEGER NOT NULL              -- 金额，单位：分（¥9.9 → 990）
status        VARCHAR(16) NOT NULL DEFAULT 'pending'
              -- 取值：pending | paid | failed
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

---

### 2.5 questions 表（无变更，Supabase migrations 管理）

```sql
question_id   TEXT PRIMARY KEY         -- 如 'D1-Q01'
dimension     TEXT NOT NULL            -- 如 '依恋'
signal_code   TEXT NOT NULL            -- 如 'S1'
signal_name   TEXT NOT NULL            -- 如 '不确定性解读'
question_type TEXT NOT NULL            -- '强度型' | '爱的语言型' | '双子面型'
stem          TEXT NOT NULL            -- 题目文本
option_a ~ option_e  TEXT             -- 选项文本（D1-D3/D5 用 A-D，D4 用 A-E）
score_a ~ score_e    TEXT             -- 分值（D1-D3/D5 为 +2/+1/-1/-2；D4 为 T1+2 等）
sort_order    INTEGER NOT NULL         -- 展示顺序（1-30）
version       TEXT DEFAULT 'V2'
notes         TEXT                     -- 题目设计说明
```

---

### 2.6 literary_mappings 表（新增）

存储 32 个文学人物映射（16 型 × 男女各 1），Python 计算层 Module 5 查此表注入人物信息。

```sql
CREATE TABLE literary_mappings (
    id             BIGSERIAL PRIMARY KEY,
    type_code      VARCHAR(16) NOT NULL,   -- 如 'A-BL-P'
    gender         VARCHAR(1)  NOT NULL,   -- 'M' 或 'F'
    type_name      VARCHAR(64) NOT NULL,   -- 如 '为爱奋不顾身的人'
    character_name VARCHAR(64) NOT NULL,   -- 如 '少年维特'
    work           VARCHAR(128) NOT NULL,  -- 如 '《少年维特之烦恼》'
    author         VARCHAR(64) NOT NULL,   -- 如 '歌德'
    archetype      TEXT NOT NULL,          -- 一句话原型概括（Agent B 构造比喻的素材）
    usage_note     TEXT,                   -- 使用限制，NULL 表示无限制
    fit_score      INTEGER,                -- 三模型综合契合度（0-100）
    UNIQUE(type_code, gender)
);
```

**查询方式：** `SELECT * FROM literary_mappings WHERE type_code = $1 AND gender = $2`

**数据来源：** 见附录 B，以数据库为准，附录 B 为文档备份。

---

## 第三章：Python 计算层规格

Python 计算层接收用户 30 题答案，按顺序执行 6 个模块，输出完整的 `diagnosis_json`，结构与 `AgentAOutput` TypedDict 定义一致。

**输入格式（answers_json）：**
```json
[
  {"question_id": "D1-Q01", "selected_option": "C", "score_value": -1, "score_meta": {}},
  {"question_id": "D3-Q06", "selected_option": "C", "score_value": -2, "score_meta": {"pursue_avoid": "pursue"}},
  ...
]
```

---

### 3.1 模块 1：五维度得分计算

#### D1 依恋 / D2 边界 / D3 冲突（强度型）

**Step 1：** 累加该维度 6 道题的 `score_value`，得到 `raw_total`（范围 -12 ~ +12）

**Step 2：** 5 档解释标签映射：

| raw_total | D1 依恋 | D2 边界 | D3 冲突 |
|-----------|---------|---------|---------|
| ≥ 6 | secure（安全型） | clear（边界清晰） | healthy（健康） |
| 3 ~ 5 | moderate_secure | moderate_clear | moderate_healthy |
| -2 ~ 2 | mixed（混合型） | mixed | mixed |
| -5 ~ -3 | moderate_anxious | moderate_blurred | moderate_problematic |
| ≤ -6 | anxious（焦虑型） | blurred（边界模糊） | problematic（问题型） |

> ⚠️ 边界值：raw_total = -3 归入 mixed；raw_total = -6 归入问题端。

**⚠️ D3-Q06 特殊规则：**

| 选项 | score_value | score_meta |
|------|------------|------------|
| A（觉察打破循环） | +2 | `{}` |
| B（无固定模式） | +1 | `{}` |
| C（追的角色） | **-2** | `{"pursue_avoid": "pursue"}` |
| D（逃的角色） | **-2** | `{"pursue_avoid": "avoid"}` |

C/D 分值相同但 score_meta 不同，报告路径完全不同，**答题包组装时必须写入 score_meta**。

#### D4 情感需求（类型学型）

**Step 1：** 按各题 score_meta 中的类型标记累加原始分（T1~T5）

**Step 2：** 归一化（原始分 ÷ 最大可能得分）：

| 类型 | 最大可能得分 |
|------|------------|
| T1 言语肯定 | 9 |
| T2 精心时刻 | 8 |
| T3 用心小惊喜 | **6（必须归一化，否则系统性低估 T3 用户）** |
| T4 服务行动 | 9 |
| T5 身体接触 | 8 |

**Step 3：** 取归一化最高的两类 = `top2`

**Step 4：** 自我认知一致性：D4-Q01 的 `primary_choice` vs `top2[0]`，不一致触发爱之语盲区洞察。

#### D5 风格表达（双子面型）

| 子面 | 题目 | 得分范围 | 标签 |
|------|------|---------|------|
| S1 直接度 | Q01/Q02/Q03 | -6 ~ +6 | >3 高直接；-3~3 中直接；<-3 高含蓄 |
| S2 分享欲 | Q04/Q05/Q06 | -6 ~ +6 | >3 高分享；-3~3 中分享；<-3 低分享 |

组合成 4 个主象限：高直接×高分享=直爽热情型、高直接×低分享=清爽利落型、高含蓄×高分享=碎碎念含蓄型、高含蓄×低分享=安静含蓄型；中间区间加"偏中"标记。

---

### 3.2 模块 2：维度内交叉验证（3 条规则）

**CV_D1_S4_consistency：**
```
分差 = abs(D1-Q04.score_value - D1-Q05.score_value)
≤1 → "high"；=2 → "medium"；≥3 → "low"（自我认知盲区）
```

**CV_D2_S1_awareness_gap_local：**
```
D2-Q01 选项 ∈ {A,B} AND D2-Q05 选项 ∈ {C,D} → True（能挡一次，挡不了一千次）
```

**CV_D3_S1_pressure_resilience：**
```
Q01 ≥1 AND Q05 ≥1 → "high"
Q01 ≥1 AND Q05 <0 → "low"（平时会表达，压力下退缩）
其他 → "medium"
```

---

### 3.3 模块 3：维度间交叉验证（3 条规则）

**CV_Cross_D2D3_S1_pattern（外强内弱）：**
```
D2-Q01.score_value = -2 AND D3-Q01.score_value = -2 → "aggressive_passive"
否则 → "normal"
```

**CV_Cross_D1D5_S2_pattern（焦虑型回避伪装）：**
```
D1-Q02.score_value = -2 AND D5-Q05.score_value = -2 → "anxious_avoidant_disguise"
否则 → "normal"
```

**CV_Cross_D2D5_S1_self_dissolution_risk（自我消融风险）：**
```
D2-Q02.score_value ≤ -1 AND D5-Q01/Q02/Q03 中 ≥2 题 score_value ≤ -1 → "high"
否则 → "low"
```

---

### 3.4 模块 4：全局复合诊断（4 个标记）

**awareness_gap_global：**
```
D1-Q01选D + D2-Q05选D + D3-Q03选D，三道中 ≥2 道选D → True（习惯性自我追责）
```

**pursue_avoid_role：** 直接由 D3-Q06 的 score_meta 决定：
- A → `"aware_breaker"`；B → `"stable"`；C → `"pursue"`；D → `"avoid"`

**stable_personality：** 30 题中 score_value ≥ 1 的题数 ≥ 18（60%）→ True（触发优势放大写作模式）

**love_language_self_awareness：** alignment_with_primary=True → "aligned"；False → "misaligned"

---

### 3.5 模块 5：16 型分型映射 + 文学人物注入

**5 档标签 → 类型码折叠规则（用户确认）：**

| 维度 | raw_total | 类型码 |
|------|-----------|--------|
| 依恋 | ≥6 | S |
| 依恋 | 3~5 | MS |
| 依恋 | 0~2（mixed 偏正） | MS |
| 依恋 | -1~-3（mixed 偏负） | MA |
| 依恋 | -4~-5 | MA |
| 依恋 | ≤-6 | A |
| 边界 | ≥0 | CL |
| 边界 | -1~-3（mixed 偏负） | BL |
| 边界 | ≤-4 | BL |
| 冲突 | ≥0 | H |
| 冲突 | -1~-3（mixed 偏负） | P |
| 冲突 | ≤-4 | P |

**type_code 拼装：** `{依恋码}-{边界码}-{冲突码}`，如 `"A-BL-P"`

**文学人物注入：**
```sql
SELECT * FROM literary_mappings
WHERE type_code = :type_code AND gender = :user_gender
-- user.gender: M→男版，F→女版，other→女版
```

---

### 3.6 模块 6：关键诊断洞察提取

| code | 触发条件 | severity |
|------|---------|----------|
| `boundary_persistent_silence` | CV_D2_S1_awareness_gap_local = True | high |
| `global_self_blame_pattern` | awareness_gap_global = True | high |
| `S1_pressure_drop` | CV_D3_S1_pressure_resilience = "low" | moderate |
| `love_language_blind_spot` | love_language_self_awareness = "misaligned" | moderate |
| `pursue_avoid_loop` | pursue_avoid_role ∈ {"pursue","avoid"} | moderate |
| `secure_baseline` | stable_personality = True | low |

输出列表按 high → moderate → low 排序，Agent B 按此决定段落展开优先级。

---

## 第四章：Agent B 接口规格

Agent B 是唯一的 LLM 调用环节，接收 Python 计算层的 `diagnosis_json`，输出结构化报告。

### 4.1 输入

| 字段 | 来源 | 说明 |
|------|------|------|
| `diagnosis_json` | assessments.diagnosis_json | Python 计算层完整输出 |
| `user_gender` | users.gender | 'M'/'F'/'other'，决定文学人物性别 |

### 4.2 输出结构（写入 report_json + report_text）

```json
{
  "report_text": "完整 markdown 报告全文（1200-1800 字）",
  "sections": {
    "type_name": "为爱奋不顾身的人",
    "type_tagline": "8-15 字 tagline，有记忆点",
    "opening": "开篇画像（80-120 字）",
    "dimensions": {
      "attachment": "依恋维度解读（150-200 字）",
      "boundary": "边界维度解读（150-200 字）",
      "conflict": "冲突维度解读（150-200 字）",
      "emotional_needs": "情感需求解读（150-200 字）",
      "expression_style": "风格表达解读（150-200 字）"
    },
    "compound_insights": [
      {
        "code": "global_self_blame_pattern",
        "title": "你不是在反思，你在习惯性认领过错",
        "finding": "30 字内客观事实陈述",
        "content": "100-150 字洞察段落"
      }
    ],
    "advice": "关系建议（200-300 字）",
    "closing": "结尾（60-100 字）",
    "literary_card": {
      "character_name": "陌生女人",
      "work": "《一个陌生女人的来信》",
      "author": "茨威格",
      "echo_line": "呼应 archetype 的一句话"
    }
  }
}
```

### 4.3 文学人物使用规则

1. **性别匹配：** user_gender=M 用男版；F 用女版；other 默认女版
2. **主体段落不出现人物名：** 用 `archetype` 构造比喻，不直说人名
3. **末尾卡片揭示人物：** 先让用户认同画像，再揭示原型（「被解谜」传播感）
4. **严格遵守 usage_note：** usage_note 不为 null 时，所有比喻和描写不得违反

**关键 usage_note 清单（违反即产品事故）：**

| 人物 | usage_note |
|------|-----------|
| 安娜·卡列尼娜 | 仅使用婚外情爆发前的克制相，绝不出现火车站结局 |
| 少年维特（最终相） | 文案与视觉避开手枪、绝望意象 |
| 苔丝 | 聚焦田野劳作 + 与安吉尔重逢前的清醒，不强调死亡 |
| 罗切斯特 | 必须使用失明后的相位 |
| 芳汀 | 聚焦早期寄钱给珂赛特的温柔状态，避开后期衰败 |
| 简·爱 | 必须注明复合后/成熟后的相位 |

### 4.4 写作规则摘要

- **报告长度：** 1200-1800 字
- **视角：** 全篇第二人称「你」，不使用「用户」
- **禁止：** 题号、维度代码（D1/S1/CV_）、「作为AI」「根据数据」等元话语
- **禁止：** 精神病学化术语（「焦虑型依恋」「人格障碍」）；改用行为化描述
- **稳定型特殊处理：** `stable_personality=True` 时切换「优势放大」写作模式，建议段改为「如何放大优势」
- **洞察严格性：** 严格忠于输入数据，不软化、不夸大。`awareness_gap_global=True` 必须在报告中体现

### 4.5 完整 System Prompt

```
你是恋爱性格测评的「报告写作 Agent」。接收上游代码层产出的结构化测评数据，生成温暖、专业、有共鸣的中文测评报告。

# 关键约束
1. **严格忠于输入数据中的所有判断**。不允许软化、夸大、或主观推翻任何分数与诊断。
2. **不重新打分、不质疑数据**。输入数据的每一个数字、每一个标签都是事实。
3. **避免精神病学化语言**。不写「焦虑型依恋」「人格障碍倾向」等术语，改用行为化描述。
4. **第二人称视角**，全篇用「你」而非「用户」。
5. **不出现「作为AI」「根据数据」「根据测评结果」「系统判定」等元话语**。
6. **不出现题号、维度代码、内部字段名**（如 D1、S1、CV_、type_code 等）。

# 输入数据格式
你会收到一个 JSON 对象，核心字段如下：
- dimension_scores: 5 个维度的详细分数
- cross_validation: 6 条交叉验证结果
- global_markers: 4 个全局复合诊断
- personality_typing: type_code / type_name / literary_mapping（含 archetype / usage_note）
- diagnostic_highlights: 触发的洞察列表（每条含 code / severity）
- user_gender: 用户性别

# 文学人物使用规则
1. 默认参照同性别人物（M→男版，F/other→女版）
2. 报告主体不出现人物姓名，用 archetype 构造比喻
3. 报告末尾「文学映射卡片」中明说人物
4. 严格遵守 usage_note，违反即产品事故

# 报告结构（必须严格遵守）

### Section 1：开篇画像（80-120 字）
- 第一句：type_name + tagline（8-15 字，像专辑名/书名）
- 2-3 句定锚：关系底色，隐含 archetype 描述但不说人名

### Section 2：五维度解读（每维度 150-200 字）
顺序：依恋 → 边界 → 冲突 → 情感需求 → 风格表达
- 每段：1 句点核心特征 + 1-2 个具体题目场景（不报题号）+ 描述不评判

### Section 3：复合诊断洞察（仅触发时生成）
每条 highlight 写一段，包含：
- title：出戏的深夜博客式标题
- finding：30-60 字客观事实陈述
- content：100-150 字洞察（指出 + 共情 + 不解决）
severity=high 的必须放在前面详写；moderate 可短带；low 可省略

### Section 4：关系建议（200-300 字）
- 2-3 条建议，具体到行为层级
- stable_personality=True 时改为「优势如何放大」

### Section 5：结尾（60-100 字）
- 邀请式收尾，不用「加油」等廉价鼓励

### Section 6：文学映射卡片（必有）
「你的文学映射：{人物名} / 出自{作者}《{作品名}》/ {呼应 archetype 的一句话}」

# 输出格式
严格输出一个 JSON 对象（第一个字符是 {，最后一个字符是 }，不输出代码围栏）：
{
  "report_text": "完整 markdown 格式报告全文",
  "sections": {
    "type_name": "...",
    "type_tagline": "...",
    "opening": "...",
    "dimensions": {"attachment":"...","boundary":"...","conflict":"...","emotional_needs":"...","expression_style":"..."},
    "compound_insights": [{"code":"...","title":"...","finding":"...","content":"..."}],
    "advice": "...",
    "closing": "...",
    "literary_card": {"character_name":"...","work":"...","author":"...","echo_line":"..."}
  }
}
```

---

## 第五章：API 接口定义

**基础 URL：** `http://localhost:8000`（开发）  
**认证：** 除 `/auth/login` 外，所有接口需 `Authorization: Bearer <jwt>` 请求头

### 5.1 POST /auth/login

抖音 code 换 JWT token。

**请求体：**
```json
{"code": "抖音授权 code"}
```

**响应：**
```json
{"token": "jwt_string", "user_id": 123}
```

**限流：** 10 次/分钟/IP

---

### 5.2 POST /quiz/start

从 Supabase 拉取 V2 题库，创建 assessment 记录，返回 30 道题。

**请求体：** 无

**响应：**
```json
{
  "session_id": "uuid",
  "questions": [
    {
      "question_id": "D1-Q01",
      "stem": "题目文本",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "question_type": "强度型"
    }
  ]
}
```

**限流：** 5 次/分钟/IP

---

### 5.3 POST /quiz/submit

提交 30 题答案，触发 Python 计算层，写入 diagnosis_json，status → analyzed。

**请求体：**
```json
{
  "session_id": "uuid",
  "answers": [
    {"question_id": "D1-Q01", "selected_option": "C"},
    ...
  ]
}
```

**后端流程：**
1. `answer_package_builder` 组装答题包（解析分值、写入 score_meta、标记 D3-Q06 亚型）
2. 调用 Python 计算层 6 个模块
3. 写入 `assessments.answers_json` + `diagnosis_json` + `algorithm_version` + `question_set_version`
4. 更新 `personality_type`，status → `analyzed`

**响应：**
```json
{"status": "analyzed", "personality_type": "A-BL-P"}
```

---

### 5.4 POST /unlock/ad

激励广告验证通过后解锁报告（不立即生成报告，仅更新解锁状态）。

**请求体：**
```json
{"session_id": "uuid", "ad_token": "抖音激励广告验证 token"}
```

**响应：**
```json
{"unlocked": true}
```

---

### 5.5 GET /result

读取报告。若已 complete 直接返回缓存；若 analyzed 且已解锁则触发 Agent B 生成报告。

**查询参数：** `?session_id=uuid`

**后端流程（首次调用）：**
1. 从 assessments 读取 diagnosis_json + user_gender
2. 调用 Agent B（豆包 API，流式输出）
3. 写入 report_json + report_text + prompt_version + model_name + token_usage
4. status → complete

**响应（流式 SSE 或一次性返回，取决于前端实现）：**
```json
{
  "status": "complete",
  "report_text": "markdown 报告全文",
  "sections": { ... },
  "personality_type": "A-BL-P",
  "type_name": "为爱奋不顾身的人"
}
```

**限流：** 10 次/分钟/IP

---

### 5.6 GET /history

用户历史测评列表。

**响应：**
```json
{
  "assessments": [
    {
      "session_id": "uuid",
      "personality_type": "A-BL-P",
      "type_name": "为爱奋不顾身的人",
      "status": "complete",
      "created_at": "2026-05-04T10:00:00Z"
    }
  ]
}
```

---

### 5.7 开发模式专用接口（DEV_MODE=true）

| 接口 | 说明 |
|------|------|
| `POST /auth/dev-login` | 跳过抖音 OAuth，直接获取 JWT |
| `POST /pay/dev-callback` | 模拟支付回调 |

⚠️ **生产环境必须设 `DEV_MODE=false` 或不设置。**

---

## 附录 A：完整 30 题题库

> 数据来源：`supabase/migrations/20260430_create_questions_table.sql`（V2 版本），以数据库为准。

| 题号 | 维度 | 信号 | 题型 | 题干 | 选项 A | 选项 B | 选项 C | 选项 D | 选项 E | 分值 A | 分值 B | 分值 C | 分值 D | 分值 E | 备注 |
|------|------|------|------|------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|------|
| D1-Q01 | 依恋 | S1 不确定性解读 | 强度型 | 你正在等对方回消息，发现他「正在输入…」后突然消失，消息迟迟不来，你的第一反应是？ | 没什么，他可能临时有事，等等就好 | 有点好奇他在忙什么，但不会追问 | 有点担心，忍不住回看聊天记录找原因 | 开始焦虑，觉得是不是自己说错了什么 | — | +2 | +1 | -1 | -2 | — | S1 测对方「无回应」时的默认解读方向 |
| D1-Q02 | 依恋 | S2 距离容忍度 | 强度型 | 你们已经三天没怎么联系，对方偶尔发来一个表情，你感觉怎么样？ | 感觉很好，各自有各自的节奏 | 有点思念，但能接受这种状态 | 有些不安，担心感情在降温 | 非常焦虑，想主动联系但又怕打扰 | — | +2 | +1 | -1 | -2 | — | S2 测能忍受多久没有联系而不触发焦虑 |
| D1-Q03 | 依恋 | S3 第三者敏感度 | 强度型 | 你刷到对方朋友圈，发现有个陌生异性频繁点赞评论，你的反应是？ | 不在意，对方有自己的社交圈很正常 | 留意了一下，但没放在心上 | 有点不舒服，开始查这个人的主页 | 很不安，忍不住问对方那是谁 | — | +2 | +1 | -1 | -2 | — | S3 测对潜在竞争者的情绪反应强度 |
| D1-Q04 | 依恋 | S4 激活后表达（核心） | 强度型 | 对方最近突然变得冷淡，消息回复变少，你通常会怎么做？ | 直接和他说：我最近感觉你有点疏远我，我们谈谈吧 | 找个轻松的话题试探，看他反应 | 等他主动，自己默默担心 | 表现出更多关心或主动联系，但心里越来越焦虑 | — | +2 | +1 | -1 | -2 | — | S4 核心题：依恋系统激活后的行为输出 |
| D1-Q05 | 依恋 | S4 激活后表达（验证） | 强度型 | 和对方约好的计划，他临时取消了，你通常的处理方式是？ | 直接表达失望：这次我很失望，以后麻烦提前说 | 表示理解，内心有些不开心但没说 | 嘴上说没事，但心里一直记着这件事 | 开始担心他是不是不想见自己了，反复找理由解释 | — | +2 | +1 | -1 | -2 | — | S4 验证题：换情境复测，对抗社会期望污染 |
| D1-Q06 | 依恋 | S5 安全感来源 | 强度型 | 在一段关系里，什么样的相处方式最让你有「被坚定选择」的踏实感？ | 他主动分享生活细节，让我觉得被纳入他的世界 | 我们彼此保有空间，但关键时刻都在 | 他对我很好，但我总担心这种好会突然消失 | 只有他主动找我、安抚我，我才能暂时安心 | — | +2 | +1 | -1 | -2 | — | S5 测安全感的来源机制 |
| D2-Q01 | 边界 | S1 越界识别（核心） | 强度型 | 你不在时，对方坦白偷看了你的手机，你的反应是？ | 直接表达：这不可以，请你解释一下，以后不能这样 | 有些不舒服，问他为什么这样做 | 心里不开心，但觉得在关系里这很正常，没有说 | 心里难受但不敢说，担心提了会闹矛盾 | — | +2 | +1 | -1 | -2 | — | S1 核心题：对单次越界能否清晰响应 |
| D2-Q02 | 边界 | S2 自我维持 | 强度型 | 恋爱后，你的个人时间、朋友圈、兴趣爱好的状态是？ | 完全保持，恋爱是我生活的一部分，不是全部 | 有些调整，但核心还在 | 大部分让步了，总觉得对方比自己重要 | 几乎全让步了，生活重心完全转移到关系上 | — | +2 | +1 | -1 | -2 | — | S2 测恋爱后自我身份的保存程度 |
| D2-Q03 | 边界 | S3 异性相处共识 | 强度型 | 对于伴侣与异性朋友的相处方式，你们的态度是？ | 信任为基础，不需要额外的报备或限制 | 大多信任，偶尔确认一下 | 需要明确规则，否则会有点不安 | 希望知道所有细节，否则会持续焦虑 | — | +2 | +1 | -1 | -2 | — | S3 测对伴侣异性社交的边界设定 |
| D2-Q04 | 边界 | S4 付出对等 | 强度型 | 在关系里，你们的情感付出和日常照顾是否相对平衡？ | 基本平衡，有时我多有时他多，但整体我们都会提出来 | 有些不均衡，但偶尔会提出来 | 明显不均衡，我付出更多，但觉得这是正常的 | 我几乎全部承担，但说了会被说太计较 | — | +2 | +1 | -1 | -2 | — | S4 测付出失衡时的觉察与表达意愿 |
| D2-Q05 | 边界 | S1 越界识别（验证） | 强度型 | 对方在争吵中翻旧账、持续贬低你，你通常的反应是？ | 当场说清楚：这种方式我不接受，我们就事论事 | 表示不喜欢，但说得不够明确 | 选择沉默，等他消气后再说 | 接受了，心里认为也许是自己的问题 | — | +2 | +1 | -1 | -2 | — | S1 验证题：对持续性伤害能否响应 |
| D2-Q06 | 边界 | S5 隐私空间 | 强度型 | 你认为健康的恋爱关系应该是？ | 两个人都有独立的私人空间，不强制透明 | 基本信任透明，但保留小部分个人空间 | 应该尽量开放，保密会让对方不安心 | 情侣就应该完全透明，有秘密就是不信任 | — | +2 | +1 | -1 | -2 | — | S5 测对隐私与透明度的基本信念 |
| D3-Q01 | 冲突 | S1 表达方式（核心） | 强度型 | 对方做了让你不舒服的小事，你通常会怎么开口？ | 直接说清楚：刚才那件事，我感觉……是因为…… | 找个时机说，但措辞比较迂回 | 用冷淡或沉默暗示，希望对方自己发现 | 忍着不说，等积累到一定程度再爆发 | — | +2 | +1 | -1 | -2 | — | S1 核心题：小摩擦时的表达风格 |
| D3-Q02 | 冲突 | S2 修复主动性 | 强度型 | 你们冷战了，双方都没有主动，通常会怎么发展？ | 我会主动打破，觉得冷战比解决问题更浪费时间 | 我会找机会试探，但不一定是第一个开口 | 等对方先主动，我很难迈出第一步 | 会一直僵着，直到外部事件迫使我们开口 | — | +2 | +1 | -1 | -2 | — | S2 测冷战后的主动修复意愿 |
| D3-Q03 | 冲突 | S3 责任归因 | 强度型 | 争吵冷静下来后，你通常怎么看这次冲突的根源？ | 双方都有责任，我主动想想自己能改进什么 | 觉得大部分是他的问题，但我也有一点 | 主要是他的问题，但为了和好我可能先低头 | 完全是他的问题，但我说了也没用，算了 | — | +2 | +1 | -1 | -2 | — | S3 测冲突后的责任归因模式 |
| D3-Q04 | 冲突 | S4 情绪淹没管理 | 强度型 | 你感到情绪快要失控时，你怎么处理？ | 主动说：我现在状态不好，需要冷静一下，稍后再谈 | 尽量控制，但有时会带出来 | 通常会直接爆发，事后后悔 | 压下去，用沉默回避，但情绪一直都在 | — | +2 | +1 | -1 | -2 | — | S4 测情绪淹没阈值下的自我调节能力 |
| D3-Q05 | 冲突 | S1 表达方式（验证） | 强度型 | 你们在关于未来的重大问题上出现了分歧，你怎么处理？ | 认真说清楚各自的立场和需求，找到共同点 | 表达了自己的看法，但说得不够完整 | 表面顺着对方，心里保留意见 | 回避这个话题，不想为此引发矛盾 | — | +2 | +1 | -1 | -2 | — | S1 验证题：高压场景（未来分歧）下的表达韧性 |
| D3-Q06 | 冲突 | S5 追逃模式 | 强度型 | 回顾你经历过的摩擦或争吵，你在其中更多扮演的是？ | 会主动觉察我们的模式，推动双方跳出追/逃循环 | 没有固定模式，情况不同角色也不同 | 主要是「追」的那方：想解决、想连接、想被回应 | 主要是「逃」的那方：需要空间、回避冲突、用沉默应对 | — | +2 | +1 | **-2** | **-2** | — | ⚠️ C/D 同为 -2 但 score_meta 不同：C→pursue_avoid:pursue，D→pursue_avoid:avoid |
| D4-Q01 | 情感 | ALL 五语均测 | 爱的语言型 | 在某个疲惫的夜晚，你最希望伴侣能做什么让你感到被爱？ | 主动说：你今天辛苦了，我很感激你一直这样 | 坐下来陪着你，什么也不用做，就是在你身边 | 在你桌上放一个你最近想要的小东西 | 悄悄把家务都做完，让你不用操心任何事 | 从背后抱着你，或者帮你按摩肩膀 | T1+2 | T2+2 | T3+2 | T4+2 | T5+2 | 全五语开放选：基线偏好探测（primary_choice） |
| D4-Q02 | 情感 | T1/T4 言语/服务 | 爱的语言型 | 关系稳定下来后，什么样的日常最让你觉得「我们感情很好」？ | 他经常夸我、肯定我做的事 | 他主动帮我处理我头疼的事情 | 每隔一段时间会一起认真规划一次约会 | 他随口的一个小拥抱或者牵手 | — | T1+2 | T4+2 | T2+1 | T5+1 | — | T1/T4 对照；C=T2+1 D=T5+1 副得分 |
| D4-Q03 | 情感 | T2/T5 精心/接触 | 爱的语言型 | 你心情低落时，什么样的陪伴最有效？ | 他关掉手机，认真听我说一个小时 | 他拉住我的手，或者把我抱得紧紧的 | 他跟我说：你不是一个人，我支持你 | 他帮我安排好接下来的事，让我不用担心 | — | T2+2 | T5+2 | T1+1 | T4+1 | — | T2/T5 对照；C=T1+1 D=T4+1 副得分 |
| D4-Q04 | 情感 | T3/T4 惊喜/服务 | 爱的语言型 | 哪种惊喜最能让你感到幸福？ | 他记住你随口提过的小细节，某天突然实现了 | 他在你最忙的时候，把所有后勤都悄悄安排好了 | 他专门为你策划了一次只有你们两个的特别约会 | 他在纪念日前写了一封信，说了很多平时不说的话 | — | T3+2 | T4+2 | T2+1 | T1+1 | — | T3/T4 对照；C=T2+1 D=T1+1 副得分 |
| D4-Q05 | 情感 | T1/T2 言语/精心 | 爱的语言型 | 吵架和好后，哪种方式最让你感到被修复？ | 他主动道歉并说清楚自己哪里错了 | 他说：我们去吃你喜欢的，什么都别想了 | 他直接拥抱你，不说话 | 他帮你做了一件你一直拖着的事情 | — | T1+2 | T2+2 | T5+1 | T4+1 | — | T1/T2 对照；C=T5+1 D=T4+1 副得分 |
| D4-Q06 | 情感 | T3/T5 惊喜/接触 | 爱的语言型 | 对你来说，哪种「我爱你」的表达方式最真实？ | 他记得你某天说的某句话，后来悄悄为你做到了 | 他习惯摸摸你的头，或者走路时不自觉牵你的手 | 他经常明确说出「我选择你」这类话 | 他在生活细节上替你想好了，让你不用操心 | — | T3+2 | T5+2 | T1+1 | T4+1 | — | T3/T5 对照；C=T1+1 D=T4+1 副得分 |
| D5-Q01 | 风格 | S1 直接性 | 双子面型 | 遇到意见不同的时候，你更倾向于？ | 直接说出我的看法，就事论事 | 先听对方说完，再表达自己 | 通常选择顺着，避免正面冲突 | 沉默或转移话题，不想争论 | — | +2 | +1 | -1 | -2 | — | S1 直接性：意见表达场景 |
| D5-Q02 | 风格 | S1 直接性 | 双子面型 | 你在新认识一个人时，通常怎么介绍自己？ | 直接说我做什么、想什么、喜欢什么 | 根据对方的问题来说，不主动多说 | 比较笼统，不太习惯直接表达喜好 | 很少主动介绍，等别人先了解我 | — | +2 | +1 | -1 | -2 | — | S1 直接性：自我表露场景 |
| D5-Q03 | 风格 | S1 直接性 | 双子面型 | 对方说了让你不开心的话，你会？ | 当场说：这句话让我不舒服，你是这个意思吗？ | 稍后找合适时机说 | 不说，但内心记住了 | 完全不说，可能就这样过了 | — | +2 | +1 | -1 | -2 | — | S1 直接性：负面反馈场景 |
| D5-Q04 | 风格 | S2 分享欲 | 双子面型 | 你刷到很有意思的内容时，第一反应是？ | 马上转给几个人，想一起聊 | 存下来，如果话题合适才分享 | 自己看完就算了，不太想分享 | 从来不分享，觉得没必要 | — | +2 | +1 | -1 | -2 | — | S2 分享欲：内容传播冲动 |
| D5-Q05 | 风格 | S2 分享欲 | 双子面型 | 在感情里，你通常怎么分享自己的日常？ | 主动讲，细节也说，喜欢让对方知道我的生活 | 对方问才说，不太主动 | 分享比较少，觉得日常没什么好说的 | 几乎不分享，觉得各自的生活应该分开 | — | +2 | +1 | -1 | -2 | — | S2 分享欲：日常生活分享习惯 |
| D5-Q06 | 风格 | S2 分享欲 | 双子面型 | 你遇到高兴或难过的事情时，更想做什么？ | 第一时间告诉对方，或发朋友圈 | 情绪稳定后再说，或选择性分享 | 通常自己消化，不太想跟人说 | 完全自己处理，不分享个人情绪 | — | +2 | +1 | -1 | -2 | — | S2 分享欲：情绪事件分享意愿 |

---

## 附录 B：32 人物完整映射表

> 数据来源：三模型（Claude / Gemini / GPT）综合判断 + 最终审定。**以 `literary_mappings` 数据库表为准，本附录为文档备份。**  
> 入库时每型拆为两行（M/F 各一行），按 `type_code + gender` 唯一索引查询。

| # | type_code | type_name | 性别 | 人物名 | 作品 | 作者 | archetype（原型概括） | usage_note | 契合度 |
|---|-----------|-----------|------|--------|------|------|----------------------|-----------|--------|
| 01 | S-CL-H | 稳重的航标 | M | 达西先生 | 《傲慢与偏见》 | 奥斯汀 | 表面冷漠但底层稳定、边界清晰、行动负责，危机时默默解决问题而不声张 | — | 95 |
| 01 | S-CL-H | 稳重的航标 | F | 伊丽莎白·班内特 | 《傲慢与偏见》 | 奥斯汀 | 自尊清醒、边界健康、敢于正面冲突，既能拒绝也能承认错误 | — | 92 |
| 02 | S-CL-P | 温和但回避深度的人 | M | 列文 | 《安娜·卡列尼娜》 | 托尔斯泰 | 对凯蒂的爱是慢的、内敛的、刻意回避剧烈情感冲突的，安全感来自内省而非关系确认 | — | 80 |
| 02 | S-CL-P | 温和但回避深度的人 | F | 范妮·普莱斯 | 《曼斯菲尔德庄园》 | 奥斯汀 | 安静、温和、有底线，但极少正面冲突，用低表达、高忍耐维持边界 | — | 90 |
| 03 | S-BL-H | 温暖的渗透者 | M | 米里哀主教 | 《悲惨世界》 | 雨果 | 主动越过陌生人边界，以银烛台改变冉·阿让的命运，是以更高伦理修复他人而非失序越界 | — | 96 |
| 03 | S-BL-H | 温暖的渗透者 | F | 多萝西娅·布鲁克 | 《米德尔马契》 | 乔治·艾略特 | 边界开放、主动渗透他人生命，嫁给卡萨邦帮其完成研究，冲突处理具建设性 | — | 93 |
| 04 | S-BL-P | 本能式的迁就者 | M | 霍拉旭 | 《哈姆雷特》 | 莎士比亚 | 稳定、可靠，本能地把自己放在哈姆雷特身后，用沉默的支撑代替自我主张 | — | 85 |
| 04 | S-BL-P | 本能式的迁就者 | F | 贝思·马奇 | 《小妇人》 | 奥尔科特 | 温和、稳定，自然地把他人放在前面，不是软弱而是天性的迁就 | — | 90 |
| 05 | MS-CL-H | 靠岸的航行者 | M | 皮埃尔·别祖霍夫 | 《战争与和平》 | 托尔斯泰 | 私生子→婚姻挫败→战争→俘虏→重建，破碎后仍能找到方向靠岸 | — | 88 |
| 05 | MS-CL-H | 靠岸的航行者 | F | 娜塔莎·罗斯托娃 | 《战争与和平》 | 托尔斯泰 | 青春热烈→战争创伤→成熟重建，与皮埃尔形成同书镜像配对 | — | 84 |
| 06 | MS-CL-P | 理智的孤勇者 | M | 巴扎罗夫 | 《父与子》 | 屠格涅夫 | 公开宣称「爱情是浪漫主义胡说八道」，表白被拒后平静离开，用理性压制一切情感冲突 | — | 92 |
| 06 | MS-CL-P | 理智的孤勇者 | F | 埃莉诺·达什伍德 | 《理智与情感》 | 奥斯汀 | 深爱但极度克制，把情感压入规则和责任中维持生活秩序 | — | 94 |
| 07 | MS-BL-H | 柔软的修复师 | M | 罗切斯特（失明后） | 《简·爱》 | 夏洛蒂·勃朗特 | 从早期暴躁傲慢转为柔软接受，主动修复对简·爱的欺骗，是关系中真诚的修复者 | 必须使用失明后的相位 | 90 |
| 07 | MS-BL-H | 柔软的修复师 | F | 简·爱（复合后） | 《简·爱》 | 夏洛蒂·勃朗特 | 既能爱也能守住尊严，主动回到罗切斯特身边但不失去自我 | 必须注明复合后/成熟后的相位 | 90 |
| 08 | MS-BL-P | 沉默的付出者 | M | 威廉·多宾 | 《名利场》 | 萨克雷 | 从军校时代爱阿米莉娅，她嫁给他人时默默支撑，从不开口，「说不出口+用行动表达」的极致 | — | 95 |
| 08 | MS-BL-P | 沉默的付出者 | F | 芳汀 | 《悲惨世界》 | 雨果 | 默默为珂赛特积攒的温柔，把一切付出压进沉默里 | 聚焦早期寄钱给珂赛特的温柔状态，避开后期衰败与死亡意象 | 80 |
| 09 | MA-CL-H | 高敏感的清醒者 | M | 聂赫留朵夫 | 《复活》 | 托尔斯泰 | 法庭上认出玛丝洛娃后对每个细节极度敏锐，主动跟随流放，焦虑中保持清醒 | — | 90 |
| 09 | MA-CL-H | 高敏感的清醒者 | F | 艾伦·奥伦斯卡 | 《纯真年代》 | 华顿 | 对纽约社交潜规则极度敏锐，深爱纽兰却坚守边界，冲突时不歇斯底里 | — | 90 |
| 10 | MA-CL-P | 守得住自己，吵不到点上 | M | 纽兰·阿切尔 | 《纯真年代》 | 华顿 | 对艾伦的爱是终生隐忍，几十年后在巴黎选择不上楼，所有戏都在心里 | — | 95 |
| 10 | MA-CL-P | 守得住自己，吵不到点上 | F | 安娜·卡列尼娜（早期克制相） | 《安娜·卡列尼娜》 | 托尔斯泰 | 表面优雅克制，内心情感强烈波动，用社交礼法压抑真实欲望 | 仅使用婚外情全面爆发前的克制相，绝不出现火车站结局意象 | 90 |
| 11 | MA-BL-H | 用力过猛的温柔 | M | 阿尔芒·杜瓦尔 | 《茶花女》 | 小仲马 | 为玛格丽特承担经济压力，嫉妒愤怒时做错事但能回头修复，爱得过猛却真诚 | — | 90 |
| 11 | MA-BL-H | 用力过猛的温柔 | F | 玛格丽特·戈蒂埃 | 《茶花女》 | 小仲马 | 为阿尔芒伪装抛弃他、默默承受所有羞辱，爱到失去边界但始终想修复 | — | 90 |
| 12 | MA-BL-P | 小心翼翼的同行者 | M | 白夜梦人 | 《白夜》 | 陀思妥耶夫斯基 | 胆怯、谦恭、陪伴式靠近，最终选择祝福娜斯坚卡而非自毁，小人物的克制 | — | 88 |
| 12 | MA-BL-P | 小心翼翼的同行者 | F | 娜斯坚卡 | 《白夜》 | 陀思妥耶夫斯基 | 多年默默等待房客回来娶她，与梦人相遇时怯生生，不敢说、走得很轻 | — | 85 |
| 13 | A-CL-H | 战斗中的清醒者 | M | 冉·阿让 | 《悲惨世界》 | 雨果 | 终生背负「我曾是罪人」的焦虑，但用一辈子的清醒和善行证明焦虑还在、却不让它驱动行为 | — | 96 |
| 13 | A-CL-H | 战斗中的清醒者 | F | 苔丝 | 《德伯家的苔丝》 | 哈代 | 在田野中劳作的清醒与倔强，焦虑底色下仍保持对自己的诚实 | 聚焦田野劳作 + 与安吉尔重逢前的清醒状态，不强调死亡结局 | 80 |
| 14 | A-CL-P | 理智抑制焦虑的人 | M | 于连·索雷尔 | 《红与黑》 | 司汤达 | 用理智、规则、阶层野心压抑自卑和焦虑，对每个动作都做精密算计 | — | 92 |
| 14 | A-CL-P | 理智抑制焦虑的人 | F | 德·瑞那夫人 | 《红与黑》 | 司汤达 | 用礼法、婚姻规则和宗教压抑对于连的情感，与男版于连形成同书配对 | — | 88 |
| 15 | A-BL-H | 激烈但真诚的爱人 | M | 希斯克利夫 | 《呼啸山庄》 | 艾米莉·勃朗特 | 「我无法没有我的灵魂活下去」，爱得激烈但诚恳，与凯瑟琳互为镜像 | — | 88 |
| 15 | A-BL-H | 激烈但真诚的爱人 | F | 凯瑟琳·恩肖 | 《呼啸山庄》 | 艾米莉·勃朗特 | 「我就是希斯克利夫」，边界融合、爱得不计后果但真诚至极 | — | 88 |
| 16 | A-BL-P | 为爱奋不顾身的人 | M | 少年维特（最终相） | 《少年维特之烦恼》 | 歌德 | 把整个生命意义压在所爱之人身上，爱无法实现时自我边界彻底崩塌 | 文案与视觉避开手枪、绝望意象，聚焦痴迷与燃烧感 | 95 |
| 16 | A-BL-P | 为爱奋不顾身的人 | F | 陌生女人 | 《一个陌生女人的来信》 | 茨威格 | 把整个人生献给一个不记得她的人，不索取、不打扰、不被认出 | — | 96 |

---

*文档结束*

> **说明：** 产品交互文档（前端 UX 流程：注册→答题→等待→解锁→报告→分享卡片）将在单独文档中规格化，本文档专注后端系统规格。
