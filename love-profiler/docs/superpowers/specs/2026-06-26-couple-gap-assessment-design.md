# 设计文档：情侣双人落差测评系统（后端核心闭环）

**日期：** 2026-06-26
**项目：** love-profiler 抖音小程序（双人模式）
**入口：** 快速模式报告页之后
**依据：** 情侣双人落差测评 PRD v1.0、技术设计文档 v1.0、双人题库 v1.0
**本期范围：** 后端"算 → 判 → 译"核心闭环 + 最小异步配对。前端双人作答页（predicted 轮 UI）、支付墙、流式 WS、DRSA 真实校准各自作为后续独立 spec。

---

## 一、背景与目标

### 1.1 产品是什么

一对情侣分别在手机上**独立异步作答**，系统计算两人在少数几个"差距确实与关系体验相关"的维度上的**落差**，并特别抓出"你以为一致、其实差很远"的**盲区**，最后生成一份帮助两人对话的报告。

明确**不做**：匹配度 / 合不合适评分、长期陪伴、社交聊天、分手结婚建议。它是一次性深度测评 + 一份报告，用完即走。

### 1.2 与现有单人模式的同构性（最关键的复用判断）

双人模式的技术架构，与现有 love-profiler 双引擎**几乎同构**，可一一映射。这决定了落地方式：复用分层模式，算法/结构全新。

| 双人技术文档 | 现有 love-profiler | 复用程度 |
|---|---|---|
| 作答数据 → 计算引擎(纯代码) | answer_package → `scoring_engine.py`(纯 Python) | 分层模式直接复用，算法全新 |
| 契约 JSON（引擎↔Agent 唯一接口） | `diagnosis_json` + `schemas/diagnosis.py` | 模式复用，结构全新 |
| 报告 Agent(LLM、被强约束) | `report_writer.py` + 质检门 | 模式 + 质检门思想直接复用 |
| 反判决铁律 / 互补型禁负面 | `report_quality_gate.py` 软硬双层校验 | 同机制，扩词表 + 新规则 |
| 后台调度 LLM + 轮询出结果 | `report_writer_runner.py` + `/result` | 同模式（条件更新避竞态 + fire-and-forget） |

### 1.3 与单人模式的 4 个本质差异（真正的新东西）

1. **异步双人配对**——单人是即时出结果；双人要"A 答完 → 邀请链接 → B 答完 → 才解锁"。
2. **predicted 轮（猜对方）**——全新作答机制，`apply_prediction=true` 的维度题量翻倍，是盲区计算的数据来源。
3. **全新题库结构**——slider/likert7 + `apply_prediction`/`reverse`/`anchors`/`layer`/`complementary`/`level_only`，与现有 `questions` 表（score_a~e）完全不同。
4. **calibration.json（DRSA 校准表）**——MVP 无 200 对样本，必须先用临时阈值 + 全维度 `topic_only` 上线（"校准前不判决"铁律）。

### 1.4 本期范围边界

**做**：题干表 + 维度注册表(58 全量) + calibration(临时默认) + 计算引擎(全 7 步) + 契约层 + 报告 Agent(卡片 JSON) + 质检门 + 最小异步配对 API + 测试。

**不做**（各自后续 spec）：前端双人作答页 / 支付墙 / 流式 WS / DRSA 真实校准 / admin 编辑双人题库。

---

## 二、架构落点（新增代码挂在现有哪层）

完全复用现有 `api/agents/services/models` 分层（**按层不按功能**，遵守 love-profiler-architecture 硬约束），新增物按层就位：

```
app/
├── api/
│   └── couple.py                    ← 新路由 /couple/*（entrypoint）
├── agents/
│   ├── couple_scoring_engine.py     ← 纯算入口 run()（无 LLM/DB），对标 scoring_engine.py
│   ├── couple_scoring/              ← 拆分子包（避免单文件破 500 行）
│   │   ├── normalize.py             ·  归一化 slider/likert7 + reverse + 同维度多题聚合
│   │   ├── triplet.py               ·  三件套（gap / direction / levels）
│   │   ├── blindspot.py             ·  Cluster F 盲区计算 + narrative_fact 生成
│   │   ├── pairings.py              ·  组合规则（demand_withdraw / anxious_avoidant）
│   │   ├── salience.py              ·  分档 gap_level + salience 排序
│   │   └── supercluster.py          ·  4 超类聚合
│   └── couple_report_writer.py      ← LLM 翻译 → 卡片 JSON，对标 report_writer.py
├── services/
│   ├── couple_registry.py           ← infra：加载维度注册表 + calibration 配置文件
│   ├── couple_answer_package_builder.py ← raw 作答 + 题库 → item 级富化包（对标现有 builder）
│   └── couple_report_runner.py      ← orchestration：调度 couple_report_writer
├── schemas/
│   └── couple_briefing.py           ← 契约层 pydantic（引擎↔Agent 接口）
├── models/
│   └── couple_session.py            ← 业务表（SQLAlchemy）
└── agents/couple_data/              ← repo 配置文件（算法参数）
    ├── dimensions.yaml              ·  维度注册表（58 维度）
    └── calibration.json             ·  校准表（MVP 临时默认阈值）
supabase/migrations/
└── {date}_create_couple_questions.sql  ← 题干表（配置表，一文件一表）
```

**依赖方向**（严守现有规则）：`couple.py → couple_scoring_engine / couple_report_runner → couple_report_writer → llm_client`；`couple_registry`(infra) 被引擎读取；`couple_answer_package_builder`(infra) 被 api 调用；`couple_session`(model) 只 import `database.Base`。

**配置层存储决策（混合）**：题干进 Supabase 表（前端拉题 + admin 编辑），维度注册表 + calibration 进 repo 配置文件（算法参数，改它=改判断行为，须 code review + 可单测 + 可复现；技术文档本就把 `calibration.json` 当运行时只读文件）。

---

## 三、配置层设计

### 3.1 维度注册表 `agents/couple_data/dimensions.yaml`

引擎与未来前端的"维度真相源"，由双人题库 v1 第二部分的 YAML 直接落地（58 维度全量录入）。`couple_registry.py` 启动时加载并校验。单维度结构：

```yaml
- id: money                  # 维度唯一标识
  cluster: A                 # 所属簇 A~E（F 是 apply_prediction 维度自带的第二轮，非独立簇）
  layer: interpretation      # interpretation | topic_only（运行时受 calibration 实际控制）
  apply_prediction: true     # 是否加 predicted 轮（自答 + 猜对方）→ 触发盲区计算
  complementary: false       # true 则禁止负面措辞（如 values_openness）
  level_only: false          # true 则只呈现双方水平、禁止对差距判决（如 emotional_stability）
  skippable: false           # true 则允许跳过（如 religiosity），跳过维度不参与该用户落差/盲区
  anchors: { low: "存下来更安心", high: "花在当下更值得" }  # 方向标签来源
  items:                     # 该维度的题目，归一化后取均值合成单维度分
    - { id: A1-1, type: slider,  reverse: false }
    - { id: A1-2, type: slider,  reverse: false }
    - { id: A1-3, type: likert7, reverse: true }
```

**6 个 apply_prediction 维度**：`money / intimacy_freq / chores / children / values_transcend / values_openness`——这些维度题量翻倍，是盲区轨道的数据来源。

### 3.2 校准表 `agents/couple_data/calibration.json`（MVP 红线落地）

```jsonc
{
  "_meta": { "calibrated": false, "note": "MVP 临时默认阈值，DRSA 未跑，全维度 topic_only" },
  "_defaults": {
    "calibrated_relevant": false,
    "gap_thresholds": { "small": 18, "moderate": 40 },
    "effect_size": 0.0,
    "direction_hurts": "incongruent"
  }
}
```

**"校准前不判决"由配置默认值兜死，而非靠代码记得**：`couple_registry.get_calibration(dim_id)` 查不到该维度专属记录时一律返回 `_defaults` → `calibrated_relevant=false` → 引擎强制该维度 `topic_only`、`salience=-1`、不进超类聚合。未来 DRSA 跑完，只需把通过校准的维度逐个写进本文件（覆盖默认），无需改一行引擎代码。

### 3.3 题干表 `couple_questions`（Supabase migration）

对齐现有 `fetch_questions` 模式，由 `/couple/create` 与 `/couple/join` 返回题库、admin 编辑题面。一文件一表（`{date}_create_couple_questions.sql`）：

| 列 | 类型 | 说明 |
|---|---|---|
| `question_id` | text PK | 如 `A1-1` |
| `dimension_id` | text | 关联 dimensions.yaml 的 `id` |
| `cluster` | text | A~E |
| `item_type` | text | `slider` \| `likert7` |
| `reverse` | bool | 反向计分 |
| `stem` | text | 题干 |
| `anchor_low` / `anchor_high` | text | slider 两端锚点（likert 可空） |
| `apply_prediction` | bool | 该题是否需要 predicted 轮 |
| `version` | text | 题库版本，如 `v1` |

> 注：`reverse`/`apply_prediction` 在题干表与 dimensions.yaml 都出现，**dimensions.yaml 为算法真相源**，题干表副本仅供前端渲染；引擎只信 dimensions.yaml（避免 DB 改题面误伤算法）。

---

## 四、数据建模 + 异步配对

### 4.1 `couple_sessions` 业务表（SQLAlchemy，对标 `assessments`）

一对情侣一次测评 = 一行。单表承载双方作答 + 契约 + 报告（"双方都 done 才解锁"的判断只读一行最简单）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `pairing_token` | str(64) unique | 邀请配对凭证（`secrets.token_urlsafe`，防猜） |
| `initiator_user_id` | int FK→users | A |
| `partner_user_id` | int FK→users nullable | B（join 前为空） |
| `a_answers_json` / `b_answers_json` | text nullable | 各自 self+predicted 作答（**分列存，隐私隔离**） |
| `a_status` / `b_status` | str(16) | `pending` → `done` |
| `briefing_json` | text nullable | 契约层产物（会话级） |
| `report_json` / `report_text` | text nullable | 报告 Agent 产物 |
| `status` | str(16) | `waiting_partner`→`computing`→`analyzed`→`generating`→`complete` |
| `question_set_version` | str | 题库版本 |
| `created_at` | datetime tz | |

启动时由 SQLAlchemy 自动建表，在 `main.py` 注册（业务表惯例）。

### 4.2 状态机

```
A: /couple/create ─▶ status=waiting_partner, a_status=pending, 生成 pairing_token
A: /couple/answer ─▶ a_answers_json 落库, a_status=done
B: /couple/join   ─▶ partner_user_id=B（校验 token & B≠A & 未被占）
B: /couple/answer ─▶ b_answers_json 落库, b_status=done
   └─ 使双方都 done 的那次 answer 触发（条件更新 status: waiting_partner→computing，只触发一次）
        ├─ 同步 couple_scoring_engine → briefing_json → status=analyzed
        └─ couple_report_runner.schedule()：status→generating →（后台 LLM）→ report → status=complete
双方: /couple/result ─▶ waiting/computing→409 ｜ analyzed/generating→202 ｜ complete→200 卡片
```

> 触发不绑定"B 的提交"，而绑定"使双方 done 的那次提交"（A/B 作答顺序任意）。条件更新 `waiting_partner→computing` 保证并发双触发只算一次。

### 4.3 隐私红线 + 防自配对

- **作答归属**：`/couple/answer` 按 `user_id` 判定写 A 列还是 B 列（`user_id==initiator`→A，`==partner`→B，都不是→403）。
- **不泄露裸答案**：任何端点都不下发对方的 `a_answers_json`/`b_answers_json`；`result` 只返回经报告 Agent 处理过的卡片。
- **防自配对**：`/couple/join` 校验 `partner_user_id != initiator_user_id`，且该 session 尚无 partner。
- **身份与配对解耦**：身份走现有 JWT（`get_current_user_id`），`pairing_token` 只作配对凭证，不作身份令牌。

### 4.4 输入作答数据结构（前端 → `/couple/answer`）

```jsonc
{
  "session_id": "uuid",
  "self":      [{ "question_id": "A1-1", "value": 18 }, ...],   // slider 0-100 / likert 1-7 原始值
  "predicted": [{ "question_id": "A1-1", "value": 35 }, ...],   // 仅 apply_prediction 维度的题
  "skipped":   ["religiosity"]                                   // skippable 维度可跳过
}
```

`value` 是**原始值**（引擎内部归一化），与技术文档 3.2 的 `normalize` 一致。触发计算时，`couple_answer_package_builder` 读取 `a_answers_json` + `b_answers_json`，用 dimensions.yaml 富化并**合并成含双方的 item 级包** `{"A":{self,predicted}, "B":{self,predicted}}`；引擎再聚合到维度级 `s_A / s_B / p_A→B / p_B→A`。

---

## 五、计算引擎 `couple_scoring_engine`

技术文档第四部分的 7 步，落成纯算流水线（对标 `scoring_engine.run`：`async` 签名、**无 LLM、无 DB**）。

### 5.1 流水线总览

```
item 级 package（self + predicted）
   │  normalize.py：单题归一化(slider直通 / likert7→(x-1)/6*100 / reverse→100-x)
   │            + 同维度多题取均值 ⇒ s_A, s_B, p_A→B, p_B→A
   ▼
┌──────────── 维度级处理（遍历每个 dimension）────────────┐
│ triplet.py    gap / direction(anchor标签) / levels{a,b}  │
│ blindspot.py  仅 apply_prediction：accuracy_error / who / │
│               assumed_close / narrative_fact             │
└──────────────────────────────────────────────────────────┘
   │
   ├─▶【判决轨道】salience.py 分档+排序 → supercluster.py 4超类聚合
   │      ⚠ 全程受 calibrated_relevant 闸门；MVP 全 false ⇒ 整条降级
   │
   ├─▶【盲区轨道】top_blindspots = 按 accuracy_error 降序取 topN
   │      ✅ 不受校准闸门；MVP 照常输出 —— 报告主菜
   │
   └─▶【全局信号】pairings.py：demand_withdraw / anxious_avoidant（维度无关 flag）
   ▼
组装契约 JSON（见第六章）→ pydantic 自检
```

### 5.2 决定 MVP 成败的双轨道解耦（核心设计）

MVP 阶段 `calibration.json` 全 `calibrated_relevant=false`，**判决轨道整条降级**：salience 全 `-1`、超类分数全 `None`、所有维度强制 `topic_only`。若报告主菜押在判决层，MVP 就是空的。

**破解**：盲区（Cluster F）的价值不需要 DRSA 证明——"你以为一致、其实不一致"本身就成立。故**盲区轨道与判决轨道彻底解耦**：`top_blindspots` 按 `accuracy_error` 排序，独立于 `calibrated_relevant`。

> MVP 报告 = **盲区卡片为主菜**（完整可用）+ 判决话题轻提（降级）+ 超类分数省略（全 None）。恰是技术文档附录 B 第 1 步"用临时默认阈值先跑通端到端"的现实形态，守住"校准前不判决"铁律。未来 DRSA 跑完，判决轨道自动激活，无需改引擎。

### 5.3 子模块职责与签名（前半）

**`normalize.py`**——归一化 + 维度聚合：

```python
def normalize_item(raw: float, item_type: str, reverse: bool) -> float:
    x = float(raw) if item_type == "slider" else (float(raw) - 1) / 6 * 100  # likert7
    return round(100 - x if reverse else x, 2)

def aggregate(dim_id: str, items: list[dict], answers: dict) -> float:
    # 同维度多题归一化后取均值（题库附录 1）；skippable 跳过维度返回 None
    ...
```

**`triplet.py`**——三件套（永不只给裸差值；保留 levels 才能区分高-高/低-低/高-低）：

```python
def triplet(s_A, s_B, dim_cfg) -> dict:
    return {
        "gap": round(abs(s_A - s_B), 2),
        "direction": { "higher_partner": "A" if s_A > s_B else "B",
                       "label_a": anchor_label(s_A, dim_cfg),   # 分值→锚点语义
                       "label_b": anchor_label(s_B, dim_cfg) },
        "levels": { "a": s_A, "b": s_B },
    }
```

**`blindspot.py`**——仅 `apply_prediction=true`，盲区轨道数据源。`narrative_fact` 由引擎生成中性事实句（基于 direction + anchors），**不交给 LLM**：

```python
def blindspot(s_A, s_B, p_A2B, p_B2A, dim_cfg) -> dict:
    actual_gap = abs(s_A - s_B)
    accuracy_A, accuracy_B = abs(p_A2B - s_B), abs(p_B2A - s_A)   # 谁把对方猜错多少
    who = "A" if accuracy_A >= accuracy_B else "B"
    err = max(accuracy_A, accuracy_B)
    assumed = abs(s_A - p_A2B) if who == "A" else abs(s_B - p_B2A)
    return {
        "exists": bucket(err, THRESH_BLINDSPOT) != "none",
        "severity": bucket(err, THRESH_BLINDSPOT),           # low/moderate/high
        "who_misjudged": who,
        "assumed_close": assumed < actual_gap,
        "accuracy_error": round(err, 2),
        "narrative_fact": build_fact(who, dim_cfg, s_A, s_B), # 中性事实，引擎产出
    }
# THRESH_BLINDSPOT = {"low": 15, "moderate": 35}
```

### 5.4 子模块职责与签名（后半）

**`pairings.py`**——高摩擦信号来自**组合**而非差距大小，命中即打全局 flag（维度无关，挂 `overview.high_friction_pairings`）：

```python
HIGH = 60
def pairings(scores: dict) -> list[str]:   # scores[user][dim] = 维度分
    flags = []
    if cross(scores, "confront", "withdraw"):        flags.append("demand_withdraw")
    if cross(scores, "attach_anxiety", "attach_avoid"): flags.append("anxious_avoidant")
    return flags   # cross(): 一方维度A>HIGH 且 另一方维度B>HIGH（两个方向都查）
```

**`salience.py`**——分档 + 判决轨道排序（**校准闸门在此**）：

```python
def gap_level(gap, th) -> str:    # none(<8) / small / moderate / large
    ...
def salience(dim_result, calib) -> float:
    if not calib["calibrated_relevant"]:
        return -1.0               # 未过校准 → 强制 topic_only，不参与排序
    g = norm(dim_result["gap"])
    b = norm(dim_result["blindspot"]["accuracy_error"]) if dim_result["blindspot"]["exists"] else 0
    return calib["effect_size"] * (0.6 * g + 0.4 * b)
# relevant 维度按 salience 降序赋 salience_rank = 1,2,3...（连续唯一）
```

**`supercluster.py`**——4 超类聚合（仅 `calibrated_relevant=true` 维度按 `effect_size` 加权；MVP 全 None）：

```python
SUPERCLUSTERS = {
    "life_expectations":    ["cluster A 维度"],
    "conflict_process":     ["cluster B 维度", "emotional_stability"],
    "values_attachment":    ["cluster C 维度", "cluster D 维度"],
    "perceptual_blindspot": ["所有 apply_prediction 维度的盲区"],
}
def supercluster_score(dim_ids, results, calib) -> float | None:
    num = den = 0
    for d in dim_ids:
        if not calib[d]["calibrated_relevant"]: continue
        num += calib[d]["effect_size"] * results[d]["gap"]; den += calib[d]["effect_size"]
    return round(num / den, 1) if den else None
```

> `level_only` 维度（`emotional_stability`）特例：在 `conflict_process` 超类里**只取双方水平均值、不计 gap**（守 level_only 铁律，禁止对差距判决）。MVP 因超类全 None 不触发，未来校准后按此实现。

### 5.5 引擎入口 `couple_scoring_engine.run()`

```python
async def run(answer_pkg, session_id=None, question_set_version="v1") -> dict:
    # answer_pkg：含双方的 item 级包 {"A":{self,predicted}, "B":{self,predicted}}，
    #             由 couple_answer_package_builder 从 a/b_answers_json 合并组装
    if not answer_pkg: raise CoupleScoringError("empty package")
    s = aggregate_all(answer_pkg)                           # 维度级 s_A/s_B/p_A2B/p_B2A
    dims = [build_dimension(d, s, registry) for d in registry.dimensions]
    # build_dimension 内：triplet + blindspot + gap_level + salience（查 calibration）
    assign_salience_ranks(dims)                              # relevant 维度连续赋秩
    overview = {
        "top_blindspots": top_n_by_accuracy_error(dims, N=3),       # 盲区轨道，独立于校准
        "supercluster_scores": {k: supercluster_score(...) for k in SUPERCLUSTERS},
        "high_friction_pairings": pairings(s),
        "complementary_strengths": [d.id for d in dims if d.complementary and d.gap_level == "large"],
    }
    return { "session_id": session_id, "overview": overview, "dimensions": dims,
             "question_set_version": question_set_version }
```

`CoupleScoringError` 对标 `ScoringError`（引擎无法完成计算时 raise，api 层转 502）。

---

## 六、契约层 `schemas/couple_briefing.py`

引擎产出即被此 pydantic schema 校验（对标 `schemas/diagnosis.py`），校验失败显式拒绝——**避免静默退化喂给 Agent**。技术文档 5.1 + 5.2 落地。

### 6.1 单维度结果对象

```python
class CoupleBlindspot(BaseModel):
    exists: bool
    severity: Literal["none", "low", "moderate", "high"]
    who_misjudged: Literal["A", "B"]
    assumed_close: bool
    accuracy_error: float
    narrative_fact: str = ""          # exists=true 时必填（见 6.3 自检）

class CoupleDimensionResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    dimension_id: str
    cluster: str
    layer: Literal["interpretation", "topic_only"]
    calibrated_relevant: bool
    complementary: bool
    level_only: bool
    gap: float
    gap_level: Literal["none", "small", "moderate", "large"]
    direction: dict                   # {higher_partner, label_a, label_b}
    levels: dict                      # {a, b}
    blindspot: CoupleBlindspot | None # 仅 apply_prediction 维度有
    salience_rank: int                # -1 表示未进判决层
```

### 6.2 全局简报对象（顶层）

```python
class CoupleOverview(BaseModel):
    top_blindspots: list[str]                  # 盲区轨道排序结果
    supercluster_scores: dict[str, float | None]
    high_friction_pairings: list[str]
    complementary_strengths: list[str]

class CoupleBriefing(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    overview: CoupleOverview
    dimensions: list[CoupleDimensionResult]
    question_set_version: str = ""
```

### 6.3 自检约束（`model_validator`，把铁律编码成不可绕过的约束）

技术文档 5.3 的产出前自检，全部落成 pydantic 校验器：

1. **盲区事实必填**：`blindspot.exists=true` 的维度，`narrative_fact` 非空。
2. **salience 连续唯一**：`calibrated_relevant=true` 的维度，`salience_rank` 从 1 开始连续且互不重复。
3. **互补型禁负面**：`complementary=true` 维度的 `direction.label_a/label_b` 不得命中负面词典。
4. **判决须有校准**：`layer="interpretation"` 但 `calibrated_relevant=false` 的维度——引擎层已强制降级 `topic_only`；schema 复核到 `layer` 与 `calibrated_relevant` 矛盾时报错（防漏降级）。

> MVP 现实：约束 2/4 在全 `topic_only` 下天然满足（无 relevant 维度→无 salience_rank 需校验）；约束 1/3 是盲区轨道与互补维度的护栏，**MVP 即生效**。

---

## 七、报告 Agent `couple_report_writer`

对标 `report_writer.py`，但**输出形态改为卡片 JSON**（技术文档 6.4），不走 `--Section--` 纯文本流式——本期不含前端，一次性生成卡片即可；流式 WS 留给前端 spec。`CoupleReportWriterError` 对标 `ReportWriterError`。

### 7.1 输出格式（卡片 JSON）

```jsonc
{
  "opening":   { "body": "..." },
  "blindspot_cards": [
    { "dimension_id": "money", "title": "金钱观：一个你们没聊透的盲区",
      "body": "你以为你们在花钱上挺合拍，其实 TA 比你想象中更愿意为当下花费……",
      "talk_prompt": "如果这个月多出一笔钱，你的第一反应是存起来还是用掉？为什么？" }
  ],
  "friction_section":  { "body": "..." },   // high_friction_pairings，每 flag 配中性化模板
  "strengths_section": { "body": "..." },   // complementary_strengths
  "closing":   { "body": "..." }
}
```

### 7.2 System prompt（反判决铁律，硬编码）

技术文档 6.2 的完整 prompt 落进 `docs/couple-report-system-prompt.md`（对标现有 `docs/agent-b-system-prompt.md`，含 `<!-- prompt-version: x.y -->` 注解，`couple_report_writer` 启动加载）。核心铁律：禁判决性表达、`complementary` 只写优势/中性、`topic_only` 最多轻提、`level_only` 只描述各自节奏、每个落差先中性事实（`narrative_fact`）再开放式引导问题、用 `gap_level` 语义而非念数字。

### 7.3 分段生成流程（技术文档 6.3）

逐段调用、每次只喂相关数据（上下文干净、便于单段质检与重试）：

```
1) 开场段     ← overview（top_blindspots + supercluster_scores）
2) 盲区卡片[]  ← 逐个 top_blindspot 维度对象 → 一卡（MVP 主菜）
3) 摩擦组合段  ← high_friction_pairings（每 flag 专属中性模板）
4) 互补优势段  ← complementary_strengths
5) 结尾段     ← overview（温和的"接下来怎么做"）
```

### 7.4 质检门 `services/couple_report_quality_gate.py`

新写，对标 `report_quality_gate.py` 的硬失败 / 软警告双层（技术文档 6.5）：

- **硬层（命中即 reject 重写）**：BANNED 反判决词表 `["匹配度","合适吗","不合适","注定","分数低","及格","不及格","般配"]`；`complementary=true` 维度卡片出现负面情绪；`topic_only`/`calibrated_relevant=false` 维度被严肃解读。
- **软层（仅日志）**：盲区卡片是否忠实引用 `narrative_fact`（"说中感"必须来自转述事实而非夸张）；规训语气巡检（复用现有 `_NORMATIVE_PATTERNS`）。

### 7.5 模板 + Agent 混合（技术文档 6.6）+ orchestration

- **模板渲染（无 LLM）**：超类分数条、图例、固定结构说明——省钱零波动。**MVP 超类全 None → 整条省略**。
- **Agent 生成（LLM）**：盲区卡片、引导问题、互补段——最需要"说中你"的地方。
- **`couple_report_runner.py`**（orchestration，对标 `report_writer_runner.py`）：条件更新避竞态（`status: generating` 时才写）+ `asyncio.create_task` fire-and-forget；成功落 `report_json`/`report_text`、`status→complete`，失败回退 `status→analyzed` 供下次轮询重试。

---

## 八、API 接口 `api/couple.py`

新开 `/couple/*` 路由，全部走现有 JWT（`get_current_user_id`）。**scoring 同步跑、report 异步后台 + result 轮询**——与现有 `/quiz/submit`(同步算) + `/result`(后台 LLM) 模式一致。在 `main.py` `include_router`。

| 端点 | 限流 | 请求 | 响应 |
|---|---|---|---|
| `POST /couple/create` | 5/min | — | `{session_id, pairing_token, questions}` |
| `POST /couple/join` | 10/min | `{pairing_token}` | `{session_id, questions}`（校验失败 403/404/409） |
| `POST /couple/answer` | 5/min | 第 4.4 节结构 | `{status}`；触发计算时同步算 + 调度报告 |
| `GET /couple/result` | 30/min | `?session_id=` | 409 未齐 / 202 生成中 / 200 卡片 JSON |

### 8.1 端到端时序

```
A: POST /couple/create ─▶ session(waiting_partner) + pairing_token + questions
A: POST /couple/answer ─▶ a_answers_json 落库, a_status=done
B: POST /couple/join ──▶ 校验 token & B≠A & 未被占 → partner_user_id=B + questions
B: POST /couple/answer ─▶ b_answers_json 落库, b_status=done
   └─使双方 done 的那次 answer：条件更新 waiting_partner→computing（只触发一次）
       ├─ couple_answer_package_builder + couple_scoring_engine → briefing_json → analyzed
       └─ couple_report_runner.schedule() → generating →(后台 LLM)→ report → complete
双方: GET /couple/result ─▶ waiting/computing→409 ｜ analyzed/generating→202 ｜ complete→200
```

### 8.2 隐私 / 鉴权 / 错误约定

- **作答归属**：`answer` 按 `user_id` 判定写 A 列 / B 列，都不匹配 → 403。
- **不泄露裸答案**：`result` 只返回报告卡片，绝不下发 `a_answers_json`/`b_answers_json`。
- **join 校验**：token 不存在 → 404；`B==initiator` → 409 self_pair；已有 partner → 409 occupied。
- **错误码**：未齐 → `409 {"error":"incomplete"}`；引擎失败 → 502；生成中 → `202 {"status":"generating"}`。

---

## 九、测试策略

对标现有测试布局（内存 SQLite + StaticPool + LLM mock，见 `tests/conftest.py`）：

| 测试文件 | 覆盖 | 重点用例 |
|---|---|---|
| `tests/agents/test_couple_scoring_engine.py` | 各子模块 + `run()` | 盲区计算正确性；**MVP 全 topic_only 时盲区轨道仍输出**；calibration 缺失走 `_defaults`；salience 全 -1；reverse/likert 归一化 |
| `tests/schemas/test_couple_briefing.py` | 契约自检 | `narrative_fact` 必填；salience 连续唯一；`complementary` 负面拒绝；漏降级拒绝 |
| `tests/services/test_couple_report_quality_gate.py` | 质检门 | BANNED 词 reject；`complementary` 负面 reject；`topic_only` 过度解读 reject |
| `tests/agents/test_couple_report_writer.py` | Agent | user message 构建；卡片 JSON 解析；质检重写 |
| `tests/services/test_couple_registry.py` | 配置加载 | dimensions.yaml + calibration.json 加载；默认值兜底 |
| `tests/api/test_couple.py` | 全流程 | create→join→answer→result 状态机；隐私（A 读不到 B 裸答案）；防自配对；未齐 409；并发双触发只算一次 |

---

## 十、范围边界、非目标与实施顺序

### 10.1 本期做 / 不做

**做**：题干表 + 维度注册表(58 全量) + calibration(临时默认) + 计算引擎(全 7 步) + 契约层 + 报告 Agent(卡片) + 质检门 + 最小异步配对 API + 测试。

**不做**（各自后续独立 spec）：前端双人作答页（predicted 轮 UI、入口挂快速模式报告页后）/ 支付墙 / 流式 WS / DRSA 真实校准 / admin 编辑双人题库。

### 10.2 实施顺序（自底向上，每阶段可独立测）

```
① 配置层  dimensions.yaml + calibration.json + couple_questions migration + couple_registry
② 数据层  couple_session model + main.py 注册
③ 引擎    couple_answer_package_builder + couple_scoring/ 子包 + 引擎入口 + couple_briefing schema
④ Agent   couple-report-system-prompt.md + couple_report_writer + couple_report_quality_gate + couple_report_runner
⑤ 接口    api/couple.py + main.py 注册
⑥ 测试    贯穿 ①~⑤
```

### 10.3 命名一致性约束

新增代码统一 `couple_` 前缀，与现有 `scoring_engine`/`report_writer` 同构命名。**不复用** `ai_call_logs.agent` 的 `agent_a/agent_b` 字符串（那是单人模式历史数据，双人若需日志另立标签）。所有文件 ≤500 行（计算引擎已按子包拆分预防超限）。

---

## 十一、关键设计决策记录（ADR）

把 brainstorm 阶段拍板的决策与理由固化，供实现期与未来回溯：

| # | 决策 | 理由 | 备选与放弃原因 |
|---|---|---|---|
| 1 | 本期聚焦后端"算→判→译"核心闭环 + 最小配对 | 盲区是别人抄不走的核心，前端/支付相对标准化可后置 | 端到端整体蓝图——太大，不利聚焦核心 |
| 2 | 配置层混合存储（题干进 DB / 注册表+calibration 进文件） | 题干是内容（前端拉、admin 编辑）；注册表与阈值是算法参数，改它=改判断行为，须 code review + 可单测 + 可复现 | 全进 DB——阈值/权重进库后不易单测与版本复现 |
| 3 | `couple_sessions` 单表承载双方作答+契约+报告 | "双方都 done 才解锁"只读一行最简单；契约/报告是会话级产物 | 拆 participant 多表——解锁判断要跨行 join，更复杂 |
| 4 | MVP 注册表全量录入 58 维度、引擎全量支持 | 本期不含前端，无答题完成率压力；后端一次到位、未来 calibration 可全量校准 | 仅 A+B+F 核心——省的是前端题量，后端无收益 |
| 5 | 盲区轨道与校准解耦，作 MVP 报告主菜 | 盲区价值不需 DRSA 证明；判决轨道 MVP 必降级，主菜须押在盲区 | 主菜押判决层——MVP 全 topic_only 时报告为空 |
| 6 | 报告输出卡片 JSON、一次性生成（不流式） | 本期不含前端，无需流式 WS；卡片结构便于前端后续渲染 | 复用 --Section-- 流式——双人是卡片结构，且本期无前端消费 |

---

> **给实现期的话**：本设计严格复用现有双引擎分层与质检门机制，新增物按 `api/agents/services/models/schemas` 各就各位。落地时先读 `love-profiler-architecture` skill 复核依赖方向，再按第十章 ①~⑥ 顺序推进。任何字段或公式不清，回查技术设计文档对应节，不要臆测。

