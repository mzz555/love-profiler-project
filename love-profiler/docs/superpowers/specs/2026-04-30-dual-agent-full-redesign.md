# 设计文档：双 Agent 完整实现 + 本地 Supabase + 全链路日志

**日期：** 2026-04-30
**项目：** love-profiler 抖音小程序（快速模式）
**依据：** 双Agent架构思路与决策 v0、双Agent Prompts v0.1、V2题库

---

## 一、背景与目标

当前代码库用 Python（`quiz_scorer.py`）做打分，再调一次 LLM 生成报告。与设计文档的双 Agent 架构存在根本差距：

| 项目 | 现有代码 | 目标架构 |
|------|----------|---------|
| Agent A | Python 打分 | LLM 调用，输出 6 类结构化诊断包 |
| Agent A 输出 | 简化5维度数值 | 信号级分数 + 6条交叉验证 + 4个全局标记 + 16类分型 + 诊断洞察 |
| Agent B 输入 | 简化分数 | Agent A 完整 JSON |
| Agent B 输出 | 纯文字 | JSON（report_text + sections 结构） |
| 答题包 | question_id + option | 含 dimension_code / signal_code / score_value / score_meta |
| 数据库 | SQLite | 本地 Supabase CLI（localhost:54322） |

---

## 二、完整数据流

```
POST /quiz/start
  └─ Supabase 拉 30 题 → 返回 session_id + questions

用户逐题作答（前端本地，30 题选完）

POST /quiz/submit（30 个答案）
  └─ answer_package_builder：查 Supabase 题目元数据，组装答题包 JSON
  └─ agent_a.run(answer_package) → 诊断包 JSON（LLM，temp=0.1）
  └─ 存入 assessment：answers_json / diagnosis_json / status="analyzed"
  └─ 返回 { assessment_id, status: "analyzed" }

用户看广告 → POST /unlock/ad → 解锁

POST /result
  └─ 查 assessment（status=="analyzed" 且已解锁）
  └─ agent_b.run(diagnosis_json) → 报告 JSON（LLM，temp=0.6）
  └─ 存入 assessment：report_json / report_text / personality_type / status="complete"
  └─ 返回 { personality_type, report_text, summary }
  └─ 重复调用直接返回缓存（status=="complete"）
```

---

## 三、数据库

### 3.1 连接配置

```
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

本地 Supabase CLI，localhost，**不需要 SSL**。`database.py` 的 `connect_args` 判断逻辑不变（非 sqlite 时为空 dict）。

### 3.2 Assessment 模型变更

新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `answers_json` | TEXT nullable | 原始答案包（审计/重跑用） |
| `diagnosis_json` | TEXT nullable | Agent A 完整输出 JSON |
| `report_json` | TEXT nullable | Agent B 完整输出 JSON |

废弃字段：`dimension_scores`（数据已被 `diagnosis_json` 覆盖，保留列但不再写入新数据）。

`report_text` / `personality_type` 保留——从 `report_json` 里提取后写入，供前端直接读取。

### 3.3 Questions 表（本地 Supabase migration）

本地 Supabase CLI 需要建 questions 表并导入 30 道题数据。Migration SQL 文件放在 `supabase/migrations/` 目录下，由 `supabase db push` 应用。

questions 表关键字段（已有，确认本地存在）：

```sql
question_id   TEXT UNIQUE,   -- D1-Q01 ... D5-Q06
dimension     TEXT,          -- 依恋/边界/冲突/情感/风格
signal_code   TEXT,          -- S1-S5 / T1-T5
signal_name   TEXT,
question_type TEXT,          -- 核心题/验证题
stem          TEXT,
option_a/b/c/d/e  TEXT,
score_a/b/c/d/e   TEXT,      -- "+2"/"-1"/"T1+2" 等
sort_order    INTEGER,
version       TEXT,          -- 题目版本号（如 "V2"），迭代时升版
notes         TEXT           -- 设计备注，记录关键限定说明，供后续根据用户反馈调整
```

`version` 和 `notes` 为可选字段（nullable）。每次根据内测反馈修改题目时，同步更新 `version` 和 `notes`，无需改动后端打分逻辑。`answer_package_builder` 拉取题目时会将 `version` 一并传入答题包（`question_set_version` 字段），Agent A 可感知题库版本。

---

## 四、服务层

### 4.1 文件变动清单

| 操作 | 文件 |
|------|------|
| 新增 | `app/services/answer_package_builder.py` |
| 新增 | `app/agents/agent_a.py` |
| 重写 | `app/agents/agent_b.py`（原 agent2_analysis.py） |
| 新增 | `app/services/llm_logger.py` |
| 修改 | `app/services/llm_client.py`（加日志埋点） |
| 修改 | `app/main.py`（加文件日志） |
| **删除** | `app/services/quiz_scorer.py` |

### 4.2 `answer_package_builder.py`

纯代码，不调用 LLM。

职责：
1. 接收用户原始答案 `[{question_id, chosen_option}]`
2. 从 Supabase 拉取题目元数据（复用 `supabase_client.fetch_questions()`）
3. 对每道题，解析所选选项的分值字符串：
   - `"+2"` → `score_value=2, score_meta={}`
   - `"T1+2"` → `score_value=2, score_meta={"type": "T1"}`
   - `"-2"` → `score_value=-2, score_meta={}`
4. 组装并返回答题包：

```json
{
  "session_id": "uuid",
  "question_set_version": "V2",
  "answers": [
    {
      "question_code": "D1-Q01",
      "dimension_code": "D1",
      "signal_code": "S1",
      "signal_name": "不确定性解读",
      "question_type": "核心题",
      "selected_option": "A",
      "score_value": 2,
      "score_meta": {}
    }
  ]
}
```

分值解析逻辑直接迁移自现有 `quiz_scorer._parse_score()`，不重复造轮子。

### 4.3 `agent_a.py`

- `system_prompt`：PDF《双Agent Prompts v0.1》中 Agent A 完整内容（Python 常量，v0 不入库）
- `temperature`：0.1
- 调用 `chat_completion(system_prompt, [{"role": "user", "content": json.dumps(answer_package)}])`
- JSON 校验：解析失败最多重试 2 次（重试时在 user message 末尾追加 `\n\n严格要求：第一个字符必须是{，最后一个字符必须是}`）
- 仍失败：抛 `AgentAError`，调用方记录 `status="failed"`
- 成功：返回诊断包 dict

### 4.4 `agent_b.py`（原 agent2_analysis.py）

- `system_prompt`：PDF 中 Agent B 完整内容
- `temperature`：0.6
- 输入：Agent A 诊断包 dict（直接传，代码侧不加工）
- 调用 `chat_completion(system_prompt, [{"role": "user", "content": json.dumps(diagnosis)}])`
- 同样的 JSON 校验 + 最多 2 次重试
- 成功：返回报告 dict（含 `report_text` 和 `sections`）

### 4.5 `llm_logger.py`

写入 `logs/ai_calls.jsonl`（JSON Lines，追加）。每条记录：

```json
{
  "ts": "ISO8601",
  "call_id": "uuid4",
  "type": "agent_a | agent_b | stream",
  "model": "doubao-pro-32k",
  "ok": true,
  "elapsed_ms": 2341,
  "prompt_tokens": 1200,
  "completion_tokens": 800,
  "total_tokens": 2000,
  "system_prompt": "完整 system prompt 原文",
  "messages": [...],
  "response": "完整 response 原文"
}
```

失败时有 `"ok": false` 和 `"error"` 字段。写入失败静默忽略（不影响主流程）。

### 4.6 `llm_client.py` 埋点

- `chat_completion()`：调用前后计时，提取 `response.json()["usage"]`，调用 `llm_logger.log_ai_call()`
- `stream_chat_completion()`：累积 chunks，流结束后记日志（无 token 数）

### 4.7 `main.py` 文件日志

启动时加 `RotatingFileHandler` 写 `logs/app.log`（10MB × 5）。`logs/` 加入 `.gitignore`。

---

## 五、API 变更

### `/quiz/submit`

```python
# 新流程
answer_package = await build_answer_package(session_id, answers, questions)
diagnosis = await agent_a.run(answer_package)          # LLM 调用
assessment.answers_json = json.dumps(answers)
assessment.diagnosis_json = json.dumps(diagnosis)
assessment.status = "analyzed"
```

返回结构：`{ assessment_id, status: "analyzed" }`（前端只判断非错误即可，无需读 status 值）。

### `/result`

```python
# 新流程
if assessment.status == "complete":
    return cached_report()                             # 缓存命中，不重跑
diagnosis = json.loads(assessment.diagnosis_json)
report = await agent_b.run(diagnosis)                  # LLM 调用
assessment.report_json = json.dumps(report)
assessment.report_text = report["report_text"]
assessment.personality_type = report["sections"]["type_name"]
assessment.status = "complete"
```

返回结构不变：`{ personality_type, report_text, summary }`。

### 其他接口不变

`/quiz/start` / `/unlock/ad` / `/auth/*` / `/pay/*` / `/history` 全部不改。

---

## 六、Prompt 管理策略

v0 阶段：两个 system prompt 作为 Python 模块常量存在 `agent_a.py` 和 `agent_b.py` 中。

迭代时更新代码文件（需重启服务）。DB 版本管理留待 v1（内测数据积累后再做）。

---

## 七、错误处理

| 场景 | 处理 |
|------|------|
| Agent A JSON 解析失败 | 重试最多 2 次；仍失败 → `assessment.status="failed"`，接口返回 502 |
| Agent B JSON 解析失败 | 同上 |
| Supabase 题目拉取失败 | 直接返回 503，不进入 Agent A |
| Agent A 成功但 Agent B 失败 | diagnosis_json 已存，`/result` 下次调用可重试 Agent B |

---

## 八、不在本次范围

- 深度模式、心动模式
- 前端任何改动（chat.js 已实现一答一问逻辑）
- Prompt DB 版本管理
- 生产环境部署

---

## 九、文件变更总清单

| 操作 | 文件 |
|------|------|
| 修改 | `app/models/assessment.py` |
| 修改 | `app/database.py`（确认 non-sqlite 不加 SSL） |
| 新增 | `app/services/answer_package_builder.py` |
| 新增 | `app/agents/agent_a.py` |
| 新增（重写）| `app/agents/agent_b.py` |
| 修改 | `app/api/quiz.py`（submit 对接 agent_a） |
| 修改 | `app/api/result.py`（对接 agent_b 新格式） |
| 新增 | `app/services/llm_logger.py` |
| 修改 | `app/services/llm_client.py` |
| 修改 | `app/main.py` |
| 新增 | `supabase/migrations/YYYYMMDD_questions.sql` |
| 修改 | `.env` |
| 修改 | `.env.example` |
| 修改 | `.gitignore` |
| 修改 | `requirements.txt`（加 psycopg2-binary） |
| **删除** | `app/services/quiz_scorer.py` |
| **删除/重命名** | `app/agents/agent2_analysis.py` |

---

## 十、实施顺序

1. 更新 `.env` DATABASE_URL，确认本地 Supabase 连通
2. 写 questions 表 migration，`supabase db push`，导入 30 道题
3. 更新 Assessment 模型，删旧 DB 文件（SQLite），重启建表
4. 实现 `answer_package_builder.py`
5. 实现 `agent_a.py`（含 Agent A system prompt）
6. 实现 `agent_b.py`（含 Agent B system prompt）
7. 修改 `/quiz/submit` 对接 agent_a
8. 修改 `/result` 对接 agent_b
9. 实现 `llm_logger.py`，修改 `llm_client.py`，修改 `main.py`
10. 删除 `quiz_scorer.py` / `agent2_analysis.py`
11. 全量测试 pytest + 端到端手动联调
