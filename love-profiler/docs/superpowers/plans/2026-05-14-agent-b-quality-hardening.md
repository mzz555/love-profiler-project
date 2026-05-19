# Agent B 报告生成质量加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有"Agent A 算分 + Agent B 写报告"双 Agent 流程的基础上，补全 7 项缺失的质量保障层——目前 LLM 写得好不好基本靠运气，没有 fail-fast、没有趋势监控、没有版本回溯。

**Background:** 见 `docs/agent-b-workflow.html` 与现有评估。核心问题：
1. `--Section--` 协议是字符串约定，LLM 漏一个 marker 前端面板空白，后端不报错
2. `diagnosis` 字段缺失会让 prompt 静默退化（少一段 enrich → 少一段输出）
3. 没有输出质量门，字数/section 数/关键元素全靠 LLM 自觉
4. 报告无版本号，prompt 改了之后老用户报告永远是旧版
5. 成本控制只到 IP 级，没有 user 维度 quota
6. 流式失败 = 整段重写，中断 UX 不友好
7. 观测性中等，无 P50/P95 / 错误分类聚合 / 用户成本归因
8. （根本问题）输出质量无 CI 校验，无趋势监控

**Architecture:** 不重构现有架构，**在 5 个边界点**注入校验/观测层：

```
[1] /quiz/submit ─── 加 Diagnosis pydantic schema 校验
                     ↓
[2] DB 落库      ─── 加 prompt_version / report_version 列
                     ↓
[3] Agent B 调用前 ─ 加 user 维度 daily token quota 拦截
                     ↓
[4] LLM 输出后   ─── 加 Section 完整性 + 字数 + 关键元素质量门
                     ↓
[5] _SectionStreamer ─ 加 section-level 持久化（失败可续）
                     ↓
[6] /admin/logs  ─── 加 P50/P95 + 成本趋势 + 质量审计面板
```

**Tech Stack:** FastAPI · pydantic v2 · SQLAlchemy · pytest · slowapi（已用）

---

## 工作量估计

| Phase | 主题 | 工作量 | 价值 |
|---|---|---|---|
| A | 输入/输出 schema 校验 + 版本化 | 1.5 天 | 🔴 高（修最根本的"静默退化"问题） |
| B | user 维度 quota + 重试策略 | 1 天 | 🟠 中（财务安全 + 抗抖动） |
| C | section-level 流式可恢复 | 2 天 | 🟡 低优先（UX 优化，工作量最大） |
| D | 观测面板 + 质量审计 | 1.5 天 | 🟢 高（看不见就管不了） |

**推荐执行顺序：A → B → D → C**。A 是基础所有其他依赖；D 接 A 的版本字段做趋势；C 工作量大且依赖前三 phase 稳定。

---

## 文件变更清单

```
新增：
  app/schemas/diagnosis.py                     — Phase A.1 pydantic 模型
  app/services/report_quality_gate.py          — Phase A.2 输出质量校验
  app/services/token_quota.py                  — Phase B.1 user 维度 quota
  supabase/migrations/
    20260515_add_versions_to_assessments.sql   — Phase A.3 加 prompt_version 列
    20260515_create_user_token_quota_table.sql — Phase B.1
    20260515_create_report_quality_audit_table.sql — Phase D.2
  tests/services/test_report_quality_gate.py
  tests/services/test_token_quota.py
  tests/schemas/test_diagnosis_schema.py

修改：
  app/api/quiz.py            — A.1 接入 schema 校验
  app/agents/agent_b.py      — A.2/A.3 接入质量门 + 版本号注入
  app/api/ws_result.py       — A.2/C.1 接入质量门 + section 持久化
  app/services/agent_b_runner.py — A.2 接入质量门 + 重试
  app/services/llm_client.py — B.2 改进重试策略
  app/api/admin.py           — D.1 新增 metrics endpoint + 质量审计查询
  static/admin/index.html    — D.1 趋势图卡片
  app/models/assessment.py   — A.3 加 prompt_version 列
```

---

# Phase A：输入/输出 schema 校验 + 版本化

## Task A.1: Diagnosis pydantic 模型 + /quiz/submit 接入校验

**Why:** 当前 `build_user_message(diagnosis)` 默默接受任何 dict，缺字段就少写一段。要让 enrich 阶段任何一个 DB 查询返回 None 都能在 502 时立即被发现，而不是混入 LLM prompt 静默退化。

**Files:**
- Create: `app/schemas/diagnosis.py`
- Create: `tests/schemas/test_diagnosis_schema.py`
- Modify: `app/api/quiz.py`

- [ ] **Step 1: TDD — 写 schema 测试**

```python
# tests/schemas/test_diagnosis_schema.py
def test_diagnosis_requires_type_code_and_type_name():
    """缺 type_name 应抛 ValidationError"""
def test_diagnosis_requires_all_dimensions_d1_through_d5():
    """五维度任何一个缺失都失败"""
def test_d4_top2_must_match_d4_details():
    """top2=['T1','T2'] 但 D4_details 只有 T1 → 失败"""
def test_d5_quadrant_must_have_guide():
    """有 quadrant 但无 D5_guide → 失败"""
def test_highlights_codes_must_have_db_enriched_fields():
    """highlights[].name_cn / report_seed / interp_path 必须全在"""
def test_valid_diagnosis_passes():
    """完整 diagnosis 通过校验"""
```

- [ ] **Step 2: 定义模型**

```python
# app/schemas/diagnosis.py
from pydantic import BaseModel, Field, model_validator

class D4Detail(BaseModel):
    code: str  # T1-T5
    name: str
    detail: str

class HighlightEnriched(BaseModel):
    code: str
    name_cn: str
    severity: Literal["high", "moderate", "info"]
    is_positive: bool
    report_seed: str
    interp_path: str
    trigger_condition: str

class DimensionsBlock(BaseModel):
    D1: dict
    D2: dict
    D3: dict
    D4: dict
    D5: dict

class Diagnosis(BaseModel):
    type_code: str = Field(min_length=1)
    type_name: str = Field(min_length=1)
    type_anchor: str = Field(min_length=10)  # 开篇必须靠它，不能空
    type_tagline: str = ""
    dimensions: DimensionsBlock
    D4_details: list[D4Detail]
    D5_guide: str = ""
    D5_style_name: str = ""
    segment_decode: list[dict] = []
    highlights: list[HighlightEnriched] = []

    @model_validator(mode="after")
    def validate_d4_alignment(self):
        # top2 中每个 code 必须在 D4_details 里
        ...
```

- [ ] **Step 3: 接入 quiz.py · submit 流程**

```python
# app/api/quiz.py（enrich 完之后）
from app.schemas.diagnosis import Diagnosis
try:
    validated = Diagnosis.model_validate(diagnosis)
except ValidationError as exc:
    logger.error("[quiz/submit] diagnosis schema 校验失败: %s", exc)
    raise HTTPException(502, "诊断数据缺失，请重试")
```

**验收点:**
- ✅ Diagnosis 模型测试全过
- ✅ 故意把 enrich 的 fetch_d5_guide 返回 None，/quiz/submit 返回 502 而不是写库
- ✅ 现有 211 个测试不破坏

---

## Task A.2: 输出质量门（Section 完整性 + 字数 + 关键元素）

**Why:** LLM 漏 `--D3--` 标记前端面板空白；写 50 字凑数前端段落空洞；highlights 写了但漏关键词。当前唯一校验是"非空"，过于宽松。

**Files:**
- Create: `app/services/report_quality_gate.py`
- Create: `tests/services/test_report_quality_gate.py`
- Modify: `app/agents/agent_b.py`, `app/api/ws_result.py`, `app/services/agent_b_runner.py`

- [ ] **Step 1: TDD — 质量门测试**

```python
def test_quality_gate_passes_complete_report():
    """完整含 8 sections + 字数达标 → ok"""
def test_quality_gate_fails_missing_required_section():
    """缺 --D3-- → QualityGateError(missing_section, 'D3')"""
def test_quality_gate_fails_too_short_section():
    """D1 段只有 30 字（要求 ≥ 100）→ QualityGateError(too_short, 'D1', 30)"""
def test_quality_gate_warns_missing_highlight_seed_keywords():
    """highlight 段没引用 report_seed 关键词 → warning（不 block，记 metric）"""
```

- [ ] **Step 2: 实现**

```python
# app/services/report_quality_gate.py
REQUIRED_SECTIONS = ["Title", "Opening", "D1", "D2", "D3", "D4", "D5", "Suggestion"]
MIN_SECTION_CHARS = {"Title": 4, "Opening": 80, "D1": 100, ..., "Suggestion": 60}

class QualityGateError(Exception):
    def __init__(self, kind: str, section: str, value: Any = None): ...

def check_report(text: str, diagnosis: dict) -> list[Warning]:
    sections = _parse_sections(text)
    for req in REQUIRED_SECTIONS:
        if req not in sections:
            raise QualityGateError("missing_section", req)
        if len(sections[req]) < MIN_SECTION_CHARS[req]:
            raise QualityGateError("too_short", req, len(sections[req]))
    warnings = _soft_checks(sections, diagnosis)  # report_seed 关键词覆盖等
    return warnings
```

- [ ] **Step 3: 接入 run_stream / agent_b_runner**

```python
# app/agents/agent_b.py · run_stream 末尾
if not all_text.strip():
    raise AgentBError("...")
try:
    warnings = check_report(all_text, diagnosis)
except QualityGateError as exc:
    raise AgentBError(f"quality_gate_failed: {exc}") from exc
for w in warnings:
    logger.warning("[agent_b/quality] %s", w)
yield {"report_text": all_text, "quality_warnings": [str(w) for w in warnings]}
```

- [ ] **Step 4: ws_result / agent_b_runner 接异常**

LLM 输出不达标时 raise AgentBError → 现有 502 + status 回滚到 analyzed 链路自动覆盖。

**验收点:**
- ✅ quality_gate 测试 100% 覆盖
- ✅ Mock LLM 输出缺 D3 → /ws/result 发 error code=502，status 回滚到 analyzed
- ✅ 真实测试一份 report，warnings 数量记到 ai_call_logs

---

## Task A.3: 报告版本化（prompt_version / report_version）

**Why:** prompt 改了之后老用户 report_text 永远停留在旧版，无法批量回溯/迁移，也没法 A/B test。

**Files:**
- Create: `supabase/migrations/20260515_add_versions_to_assessments.sql`
- Modify: `app/models/assessment.py`, `app/agents/agent_b.py`, `app/services/agent_b_runner.py`, `app/api/ws_result.py`

- [ ] **Step 1: Migration**

```sql
-- supabase/migrations/20260515_add_versions_to_assessments.sql
ALTER TABLE assessments
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS report_version SMALLINT DEFAULT 1;

COMMENT ON COLUMN assessments.prompt_version
    IS 'Agent B system prompt 版本号（从 docs/agent-b-system-prompt.md 头部解析）';
COMMENT ON COLUMN assessments.report_version
    IS '报告 schema 版本，结构发生不兼容变化时升级（如 section 改名/拆分）';
```

- [ ] **Step 2: prompt 文件头部加版本号**

```markdown
<!-- docs/agent-b-system-prompt.md 顶部 -->
<!-- version: 2.1 -->
# Agent B System Prompt
...
```

- [ ] **Step 3: 加载时解析版本**

```python
# app/agents/agent_b.py
_PROMPT_VERSION_RE = re.compile(r'<!--\s*version:\s*([\d.]+)\s*-->')
m = _PROMPT_VERSION_RE.search(_PROMPT_FILE.read_text())
PROMPT_VERSION = m.group(1) if m else "unknown"
```

- [ ] **Step 4: 写库时同步版本**

```python
# agent_b_runner.run_and_persist + ws_result._stream_agent_b
rec.prompt_version = PROMPT_VERSION
rec.report_version = REPORT_VERSION  # 在 agent_b.py 定义常量
```

**验收点:**
- ✅ migration apply 成功，新字段可空兼容旧数据
- ✅ 新生成报告含 prompt_version
- ✅ /admin/api/assessments 列表显示版本列

---

# Phase B：成本控制 + 重试策略

## Task B.1: User 维度 daily token quota

**Why:** slowapi 是 IP 级，VPN/移动网络不稳定时误伤；同时一个用户开多 tab 反复触发能堆出账单。

**Files:**
- Create: `app/services/token_quota.py`
- Create: `supabase/migrations/20260515_create_user_token_quota_table.sql`
- Create: `tests/services/test_token_quota.py`
- Modify: `app/agents/agent_b.py` (前置检查)

- [ ] **Step 1: 表结构**

```sql
CREATE TABLE IF NOT EXISTS user_token_quota (
    user_id      INTEGER NOT NULL,
    date         DATE    NOT NULL,
    tokens_used  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);
```

- [ ] **Step 2: TDD + 实现**

```python
DAILY_LIMIT = int(os.getenv("USER_DAILY_TOKEN_LIMIT", "20000"))

async def check_and_reserve(user_id: int, estimated: int) -> bool:
    """原子检查 + 占额。超 quota 返回 False，由调用方抛 429。"""

async def commit_actual(user_id: int, actual: int):
    """LLM 完成后修正实际消耗（estimated 通常偏多）。"""
```

- [ ] **Step 3: 接入 Agent B 入口**

```python
# ws_result._stream_agent_b 开头
if not await token_quota.check_and_reserve(user_id, estimated=3000):
    await _send(websocket, {"type": "error", "code": 429, "message": "今日额度已用完"})
    return
```

**验收点:**
- ✅ 同 user 多次请求累加，超 limit 返 429
- ✅ 跨日自动清零（PK 含 date）
- ✅ LLM 失败时不扣额

---

## Task B.2: LLM 调用重试策略

**Why:** 当前 `chat_completion` 有限重试（空响应试 1 次），但 stream 失败/网络抖动直接传到用户。需要指数退避 + 区分错误类型。

**Files:**
- Modify: `app/services/llm_client.py`

- [ ] **Step 1: 加重试装饰器**

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
)
async def chat_completion(...): ...
```

- [ ] **Step 2: stream 失败的中段恢复（简化版）**

Stream 中途断开通常无法接续（豆包不支持）；只做"首字节前的失败可重试"。

**验收点:**
- ✅ 模拟 503 连续 2 次 + 1 次 200，最终成功
- ✅ 4xx 不重试（直接抛）

---

# Phase C：流式失败可恢复（高工作量）

## Task C.1: Section-level 持久化

**Why:** LLM 写到 D4 段崩了，前面 Title/Opening/D1-D3 全丢，必须从头再来——浪费成本 + UX 差。

**Files:**
- Modify: `app/api/ws_result.py`, `app/services/agent_b_runner.py`
- Create: `supabase/migrations/20260515_add_partial_sections_to_assessments.sql`

- [ ] **Step 1: 加 partial_sections JSONB 字段**

```sql
ALTER TABLE assessments
    ADD COLUMN IF NOT EXISTS partial_sections JSONB DEFAULT '{}'::jsonb;
COMMENT ON COLUMN assessments.partial_sections
    IS '已完成的 section 缓存：{"Title": "...", "Opening": "..."}；status=complete 后清空';
```

- [ ] **Step 2: _SectionStreamer 增量持久化**

每个 section_end 触发后异步 UPDATE `partial_sections[section_name] = text`。失败重试时跳过已完成 section。

- [ ] **Step 3: prompt 加 "continue from" 提示**

```
<!-- 重试 user message 头部 -->
# 接续生成（前面段落已完成，请跳过）
- Title: <已生成>
- Opening: <已生成>
- D1: <已生成>
现在请从 --D2-- 开始生成。
```

**验收点:**
- ✅ Mock D3 段抛错 → DB 中 partial_sections 含 Title/Opening/D1/D2
- ✅ 重试时 prompt 内含"接续生成"标记
- ✅ status=complete 后 partial_sections 清空

**风险:** 豆包对接续生成的语义连贯性需要试运行验证；如果效果差，回退为"清空 partial_sections 全量重写"。

---

# Phase D：观测面板 + 质量审计

## Task D.1: /admin/logs 升级（P50/P95 + 成本趋势）

**Files:**
- Modify: `app/api/admin.py`, `static/admin/index.html`

- [ ] **Step 1: 新增 metrics API**

```python
@router.get("/admin/api/metrics/llm")
async def llm_metrics(window: str = "24h", db: Session = Depends(get_db)):
    """返回 P50/P95 latency, 错误率, token 趋势（按小时桶聚合）"""
```

聚合 SQL 用 PostgreSQL 的 `PERCENTILE_CONT` + `date_trunc('hour', ts)`。

- [ ] **Step 2: 前端加趋势图**

最简单做法：纯 Canvas 画线图（项目已有 D4/D5 雷达图 Canvas 经验）。指标卡片：
- 24h P50 / P95 延迟
- 24h 错误率（按 agent / error_type 分组）
- 24h token 总量 + Top 5 用户
- 24h prompt_version 分布

**验收点:**
- ✅ /admin/logs 顶部新增 4 张指标卡 + 1 张 24h 趋势图
- ✅ 数据来自 ai_call_logs，无需新表

---

## Task D.2: 质量审计表 + 周抽查

**Why:** 同样的 diagnosis temperature=0.6 每次输出不同，没法 CI 回归；只能靠定期抽查发现风格漂移。

**Files:**
- Create: `supabase/migrations/20260515_create_report_quality_audit_table.sql`
- Create: `app/services/quality_audit.py`

- [ ] **Step 1: 表结构**

```sql
CREATE TABLE IF NOT EXISTS report_quality_audit (
    id              SERIAL PRIMARY KEY,
    assessment_id   INTEGER NOT NULL REFERENCES assessments(id),
    audit_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    prompt_version  TEXT,
    overall_score   SMALLINT,  -- 1-10
    dimension_scores JSONB,    -- {"Title": 9, "Opening": 8, ...}
    audit_notes     TEXT,
    auditor         TEXT       -- 'llm-judge' / 'human:zhi75426@gmail.com'
);
```

- [ ] **Step 2: LLM-as-judge 实现**

```python
# app/services/quality_audit.py
AUDIT_PROMPT = """你是报告质量审计员。请对以下人格报告按 10 分制打分..."""

async def audit_report(assessment_id: int) -> AuditResult:
    """喂报告 + diagnosis 给 LLM，让它打分。"""
```

- [ ] **Step 3: 调度方式（选其一）**

- 简单版：手动触发 admin 按钮 `POST /admin/api/audit/{assessment_id}`
- 自动版：每天定时跑 cron 抽 5 份（需 APScheduler / Supabase pg_cron）

推荐先做手动版，自动化等趋势数据足够后再加。

**验收点:**
- ✅ 手动触发审计写入 audit 表
- ✅ /admin 新增"质量审计"页查看历史评分趋势

---

# 总验收

执行完 4 个 Phase 后：

- [ ] 全部测试通过（211 + 新增 ~30 ≈ 240 passed）
- [ ] 总覆盖率维持 ≥ 90%
- [ ] 故意把 enrich fetch 注掉，/quiz/submit 返 502（A.1 生效）
- [ ] LLM mock 输出缺 D3，/result 返 502 + status 回滚（A.2 生效）
- [ ] 新报告 DB 行含 prompt_version="2.1"（A.3 生效）
- [ ] 同 user 5 次 /result 后第 6 次返 429（B.1 生效）
- [ ] 模拟豆包 503 重试 3 次后成功（B.2 生效）
- [ ] D3 段失败，partial_sections 含 D1/D2（C.1 生效）
- [ ] /admin/logs 顶部含 P50/P95 + 24h 趋势图（D.1 生效）
- [ ] 手动触发审计写入 report_quality_audit 表（D.2 生效）

---

## 不在本 plan 范围内

明确划线避免膨胀：
- ❌ A/B 测试框架（独立 experiment_id + 流量切分逻辑）
- ❌ 多模型混合（同时跑豆包 + 其他模型对比）
- ❌ 报告导出 PDF/分享卡片
- ❌ Agent A 的算法本身（已经 99% 覆盖且确定性，不动）

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| Phase A 校验过严，正常请求 502 飙升 | 灰度开关：环境变量 `STRICT_DIAGNOSIS_SCHEMA=false` 时只 warn 不 raise |
| Phase B quota 限额误判 | 初期 limit 设高（5w token/天）+ admin 可临时上调 |
| Phase C 接续生成语义断裂 | 失败时回退为"清空 partial_sections 全量重写" |
| 新增 SQL migration apply 失败 | 全部用 `IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`，幂等 |

---

## 开发节奏建议

| 推荐节奏 | 备注 |
|---|---|
| 一天一 Phase | A → 1.5 天，B → 1 天，D → 1.5 天，C → 2 天，合计约 6 天 |
| 每 Phase 独立 commit + push | 每个 Phase 内 Task 拆 2-3 commit |
| Phase A 完成必须先验收再进 B | A 是其他 Phase 的前置 |
| 不写 docs（除非影响协作的） | 这份 plan 本身已足够，每 Task 的 docstring 即文档 |

---

**审阅请关注：**
1. 7 条改进是否漏掉/无关项？
2. Phase 顺序（A→B→D→C）是否合理？
3. Task A.2 的"质量门"硬条件（字数下限、必备 section）是否过严？
4. Phase C 是否真有必要？（最贵，但 UX 价值争议）
5. D.2 的 LLM-as-judge 用哪个模型审？同一个豆包还是换 Claude？
