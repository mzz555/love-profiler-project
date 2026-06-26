# 双人落差测评 · 计划 B（服务化外壳）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **前置依赖：** 本计划依赖**计划 A（引擎核心闭环）已完成**——`couple_scoring_engine.run()`、`couple_answer_package_builder.build_couple_answer_package()`、`schemas/couple_briefing.CoupleBriefing` 均已就绪。

**Goal:** 在计划 A 的引擎之上搭建数据层（`couple_sessions` 表）、报告 Agent（卡片 JSON）、质检门、后台 runner 与 `/couple/*` HTTP 接口，形成完整的双人异步配对闭环。

**Architecture:** 复用现有 `quiz.py`/`result.py` 路由模式、`report_writer_runner` 后台调度模式（条件更新避竞态 + fire-and-forget）、`report_quality_gate` 双层校验模式。报告 Agent 输出卡片 JSON——盲区卡片逐个 LLM 生成（主菜），其余段模板组装。状态机由 `couple_sessions` 单表 + 条件更新驱动。

**Tech Stack:** FastAPI、SQLAlchemy、slowapi、豆包 LLM（`chat_completion`）、pytest + TestClient。

## Global Constraints

> 每个任务的要求都隐含包含本节。

- **依赖计划 A**：消费 `couple_scoring_engine.run`、`build_couple_answer_package`、`CoupleBriefing`，不重复实现。
- **隐私红线**：任何端点都不下发对方的 `a_answers_json`/`b_answers_json`；`result` 只返回报告卡片。
- **作答归属**：`answer` 按 `user_id` 判定写 A 列 / B 列，都不匹配 → 403。
- **防自配对**：`join` 校验 `partner_user_id != initiator_user_id` 且 session 尚无 partner。
- **反判决 BANNED**：`["匹配度","合适吗","不合适","注定","分数低","及格","不及格","般配"]`，质检命中即 reject。
- **校准前不判决**：报告对 `topic_only`/`calibrated_relevant=false` 维度只轻提，不严肃解读。
- **触发并发安全**：条件更新 `status: waiting_partner→computing` 保证双方齐时只触发一次计算。
- **命名**：`couple_` 前缀；异常 `CoupleReportWriterError`/`CoupleQualityGateError`。
- **业务表 vs 配置表**：`couple_sessions` 走 SQLAlchemy（main.py 注册）；`couple_questions` 走 Supabase migration（一文件一表）。
- **文件 ≤500 行；单次写入 ≤150 行（分批）。**
- **鉴权**：全部走现有 `get_current_user_id`（JWT）；测试用现有 `auth_headers`/`user_id` fixture。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `supabase/migrations/{date}_create_couple_questions.sql` | 新建 | 题干表（配置表，前端拉题用） |
| `app/services/supabase_client.py` | 改 | 加 `fetch_couple_questions()` |
| `app/models/couple_session.py` | 新建 | `couple_sessions` 业务表（SQLAlchemy） |
| `app/main.py` | 改 | 注册 model + `couple.router` |
| `docs/couple-report-system-prompt.md` | 新建 | 报告 Agent 反判决铁律 prompt |
| `app/agents/couple_report_writer.py` | 新建 | briefing → 卡片 JSON（盲区卡片 LLM + 模板组装） |
| `app/services/couple_report_quality_gate.py` | 新建 | 卡片质检（BANNED / complementary 负面 / 过度解读） |
| `app/services/couple_report_runner.py` | 新建 | 后台调度报告 Agent，落库 |
| `app/api/couple.py` | 新建 | `/couple/create|join|answer|result` |
| `tests/...` | 新建 | 各层测试 |

依赖方向：`api/couple → couple_scoring_engine + couple_answer_package_builder + couple_report_runner + couple_session + supabase_client`；`couple_report_runner → couple_report_writer → couple_report_quality_gate + llm_client`。

**任务清单（8 个）：** ①题干表+fetch → ②couple_session model → ③quality_gate → ④prompt+report_writer → ⑤report_runner → ⑥api create+join → ⑦api answer(触发) → ⑧api result+路由注册。

---

### Task B1: couple_questions 题干表 + fetch

**Files:**
- Create: `supabase/migrations/20260626_create_couple_questions.sql`
- Modify: `app/services/supabase_client.py`（追加 fetch 函数）
- Test: `tests/services/test_couple_questions_fetch.py`

**Interfaces:**
- Produces: `fetch_couple_questions() -> list[dict]`（进程内缓存）、`clear_couple_questions_cache() -> None`

- [ ] **Step 1: 写失败测试**（只验证缓存逻辑，不依赖真实 DB）

```python
# tests/services/test_couple_questions_fetch.py
import asyncio
from app.services import supabase_client as sc

def test_fetch_couple_questions_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(sc, "_fetch_couple_questions_sync",
                        lambda: (calls.append(1), [{"question_id": "A1-1"}])[1])
    sc.clear_couple_questions_cache()
    r1 = asyncio.run(sc.fetch_couple_questions())
    r2 = asyncio.run(sc.fetch_couple_questions())
    assert r1 == r2 == [{"question_id": "A1-1"}]
    assert len(calls) == 1     # 第二次命中缓存
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/services/test_couple_questions_fetch.py -v` → FAIL（AttributeError: `_fetch_couple_questions_sync`）

- [ ] **Step 3a: 写 migration（建表 + 录入 58 题）**

按《双人题库v1.md》第一部分**逐题录入全部 58 题**，字段与下方 3 题样例对齐。`item_type` ∈ {slider,likert7}；slider 题填 anchor_low/high，likert 题留空；`apply_prediction` 取该维度的标志。

```sql
-- supabase/migrations/20260626_create_couple_questions.sql
CREATE TABLE IF NOT EXISTS couple_questions (
    question_id      TEXT PRIMARY KEY,
    dimension_id     TEXT NOT NULL,
    cluster          TEXT NOT NULL,
    item_type        TEXT NOT NULL,
    reverse          BOOLEAN NOT NULL DEFAULT FALSE,
    stem             TEXT NOT NULL,
    anchor_low       TEXT,
    anchor_high      TEXT,
    apply_prediction BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order       INTEGER NOT NULL,
    version          TEXT DEFAULT 'v1'
);

INSERT INTO couple_questions VALUES
('A1-1','money','A','slider',FALSE,'对待钱，我更倾向于——','存下来更安心','花在当下更值得',TRUE,1,'v1'),
('A1-3','money','A','likert7',TRUE,'我觉得为了将来，现在省一点是值得的。',NULL,NULL,TRUE,3,'v1'),
('E1-1','emotional_stability','E','likert7',TRUE,'我的情绪比较容易因为小事起伏。',NULL,NULL,FALSE,50,'v1')
-- … 其余 55 题同法录入
ON CONFLICT (question_id) DO NOTHING;

COMMENT ON TABLE couple_questions IS '双人题库题干表（58 题）。一行=一道题；item_type=slider/likert7；apply_prediction 标记需 predicted 轮的题';
```

- [ ] **Step 3b: 追加 fetch 到 `supabase_client.py`**（接在 `fetch_questions` 之后）

```python
_couple_questions_cache: list[dict] | None = None


def clear_couple_questions_cache() -> None:
    global _couple_questions_cache
    _couple_questions_cache = None


def _fetch_couple_questions_sync() -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM couple_questions ORDER BY sort_order ASC"))
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_couple_questions() -> list[dict]:
    """Fetch 双人题库题干（首次后进程内缓存）。"""
    global _couple_questions_cache
    if _couple_questions_cache is None:
        _couple_questions_cache = await run_in_threadpool(_fetch_couple_questions_sync)
    return _couple_questions_cache
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/services/test_couple_questions_fetch.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260626_create_couple_questions.sql app/services/supabase_client.py tests/services/test_couple_questions_fetch.py
git commit -m "feat(couple): couple_questions 题干表 + fetch"
```

---

### Task B2: couple_session 业务表 model

**Files:**
- Create: `app/models/couple_session.py`
- Modify: `app/main.py`（注册 model 触发建表）
- Test: `tests/models/test_couple_session.py`

**Interfaces:**
- Produces: `CoupleSession`（SQLAlchemy model，`__tablename__="couple_sessions"`）
- 字段：`id, session_id, pairing_token, initiator_user_id, partner_user_id, a_answers_json, b_answers_json, a_status, b_status, briefing_json, report_json, report_text, status, question_set_version, created_at`

> 说明：加 `session_id`（uuid，A/B 共享的对外标识）细化 spec 4.1——spec 4.4/8.1 已用 `session_id` 作请求/查询键；`pairing_token` 仅 B join 用。

- [ ] **Step 1: 写失败测试**

```python
# tests/models/test_couple_session.py
def test_couple_session_model_fields():
    from app.models.couple_session import CoupleSession
    assert CoupleSession.__tablename__ == "couple_sessions"
    cols = set(CoupleSession.__table__.columns.keys())
    assert {"session_id", "pairing_token", "initiator_user_id", "partner_user_id",
            "a_answers_json", "b_answers_json", "a_status", "b_status",
            "briefing_json", "report_json", "status"} <= cols
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/models/test_couple_session.py -v` → FAIL

- [ ] **Step 3a: 写 model**

```python
# app/models/couple_session.py
"""CoupleSession — 一对情侣一次双人测评（异步配对 + 契约 + 报告）。"""
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CoupleSession(Base):
    __tablename__ = "couple_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    pairing_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    initiator_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    partner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    a_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    b_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    a_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    b_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    briefing_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting_partner")
    question_set_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 3b: 在 `main.py` 注册 model**（与现有 `report_quality_audit` import 同处追加一行）

```python
from app.models import couple_session  # noqa: F401 — registers CoupleSession with Base
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/models/test_couple_session.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/couple_session.py app/main.py tests/models/test_couple_session.py
git commit -m "feat(couple): couple_sessions 业务表 model"
```

---

### Task B3: couple_report_quality_gate（卡片质检门）

**Files:**
- Create: `app/services/couple_report_quality_gate.py`
- Test: `tests/services/test_couple_report_quality_gate.py`

**Interfaces:**
- Produces:
  - `CoupleQualityGateError(Exception)`
  - `check_cards(cards: dict, briefing: dict) -> list[str]`（硬失败 raise；返回软警告列表）

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_couple_report_quality_gate.py
import pytest
from app.services.couple_report_quality_gate import check_cards, CoupleQualityGateError

def _briefing(comp=False):
    return {"dimensions": [{"dimension_id": "money", "complementary": comp,
            "blindspot": {"narrative_fact": "A 比 B 预想的更倾向「存钱」"}}]}

def _cards(body):
    return {"opening": {"body": ""},
            "blindspot_cards": [{"dimension_id": "money", "title": "t", "body": body, "talk_prompt": ""}],
            "friction_section": {"body": ""}, "strengths_section": {"body": ""}, "closing": {"body": ""}}

def test_banned_word_rejected():
    with pytest.raises(CoupleQualityGateError):
        check_cards(_cards("你们的匹配度很高"), _briefing())

def test_complementary_negative_rejected():
    with pytest.raises(CoupleQualityGateError):
        check_cards(_cards("这是你们关系的缺陷"), _briefing(comp=True))

def test_fact_reference_soft_warning():
    assert any("fact_not_referenced" in w for w in check_cards(_cards("完全无关的内容"), _briefing()))

def test_clean_card_passes():
    assert check_cards(_cards("A 比 B 预想的更倾向存钱，这值得聊聊"), _briefing()) == []
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/services/test_couple_report_quality_gate.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/services/couple_report_quality_gate.py
"""Couple 报告卡片质检门（对标 report_quality_gate 的硬失败/软警告双层）。"""
from __future__ import annotations

BANNED = ("匹配度", "合适吗", "不合适", "注定", "分数低", "及格", "不及格", "般配")
_NEGATIVE = ("缺陷", "糟", "失败", "不足", "病态")


class CoupleQualityGateError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        super().__init__(f"{kind}: {detail}" if detail else kind)


def _all_text(cards: dict) -> str:
    parts = [cards.get(k, {}).get("body", "") for k in
             ("opening", "friction_section", "strengths_section", "closing")]
    for c in cards.get("blindspot_cards", []):
        parts += [c.get("title", ""), c.get("body", ""), c.get("talk_prompt", "")]
    return "\n".join(parts)


def _fact_referenced(fact: str, body: str) -> bool:
    key = fact.strip()
    if len(key) < 4:
        return key in body
    return any(key[i:i + 4] in body for i in range(min(len(key) - 3, 6)))


def check_cards(cards: dict, briefing: dict) -> list[str]:
    if (hit := [w for w in BANNED if w in _all_text(cards)]):
        raise CoupleQualityGateError("banned_word", str(hit))
    dims = {d["dimension_id"]: d for d in briefing.get("dimensions", [])}
    for c in cards.get("blindspot_cards", []):
        d = dims.get(c.get("dimension_id"), {})
        if d.get("complementary") and (neg := [w for w in _NEGATIVE if w in c.get("body", "")]):
            raise CoupleQualityGateError("negative_on_complementary", f"{c['dimension_id']}:{neg}")
    warnings: list[str] = []
    for c in cards.get("blindspot_cards", []):
        fact = (dims.get(c.get("dimension_id"), {}).get("blindspot") or {}).get("narrative_fact", "")
        if fact and not _fact_referenced(fact, c.get("body", "")):
            warnings.append(f"fact_not_referenced:{c.get('dimension_id')}")
    return warnings
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/services/test_couple_report_quality_gate.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/couple_report_quality_gate.py tests/services/test_couple_report_quality_gate.py
git commit -m "feat(couple): 报告卡片质检门"
```

---

### Task B4: report system prompt + couple_report_writer

**Files:**
- Create: `docs/couple-report-system-prompt.md`
- Create: `app/agents/couple_report_writer.py`
- Test: `tests/agents/test_couple_report_writer.py`

**Interfaces:**
- Consumes: `chat_completion`（llm_client）、`check_cards`（Task B3）
- Produces:
  - `CoupleReportWriterError(Exception)`
  - `build_card_user_message(dim: dict) -> str`
  - `async run(briefing: dict, session_id=None) -> dict` → `{opening, blindspot_cards[], friction_section, strengths_section, closing, quality_warnings}`

> MVP：盲区卡片逐个 LLM 生成（主菜），开场/摩擦/互补/结尾用模板；质检 hard fail 直接抛（不重写），由 runner 回退重试。`agent="couple_report"` 是新日志标签（不复用 agent_a/b）。

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/test_couple_report_writer.py
import asyncio, json
import pytest
from app.agents import couple_report_writer as crw

def _briefing():
    return {"session_id": "s",
        "overview": {"top_blindspots": ["money"], "high_friction_pairings": [],
                     "complementary_strengths": [], "supercluster_scores": {}},
        "dimensions": [{"dimension_id": "money", "complementary": False, "gap_level": "large",
            "direction": {"higher_partner": "B", "label_a": "存钱", "label_b": "花钱"},
            "blindspot": {"narrative_fact": "A 比 B 预想的更倾向「存钱」", "exists": True}}]}

def test_run_generates_cards(monkeypatch):
    async def fake_chat(**kw):
        return json.dumps({"title": "金钱观盲区",
            "body": "A 比 B 预想的更倾向存钱，这值得聊聊", "talk_prompt": "多出一笔钱你会怎么花？"})
    monkeypatch.setattr(crw, "chat_completion", fake_chat)
    report = asyncio.run(crw.run(_briefing(), session_id="s"))
    assert len(report["blindspot_cards"]) == 1
    assert report["blindspot_cards"][0]["dimension_id"] == "money"
    assert report["quality_warnings"] == []
    assert "opening" in report and "closing" in report

def test_run_no_blindspots_raises(monkeypatch):
    monkeypatch.setattr(crw, "chat_completion", lambda **kw: _aret("{}"))
    b = _briefing(); b["overview"]["top_blindspots"] = []
    with pytest.raises(crw.CoupleReportWriterError):
        asyncio.run(crw.run(b, session_id="s"))

async def _aret(v): return v
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/test_couple_report_writer.py -v` → FAIL

- [ ] **Step 3a: 写 `docs/couple-report-system-prompt.md`**

```markdown
<!-- prompt-version: 1.0 -->
你是关系测评报告的撰写助手。你只能基于传入的结构化数据写作，不得引入任何外部信息或自补心理学结论。

【铁律，违反即失败】
1. 禁止判决性表达：不得出现"匹配度/合不合适/注定/般配/及格"等。落差一律框定为"值得一起聊的话题"。
2. complementary 维度只能写成优势或中性，禁止任何负面措辞。
3. topic_only / calibrated_relevant=false 维度最多轻提，不做严肃解读。
4. level_only 维度只描述各自节奏/状态，不把"差距"说成问题。
5. 每张盲区卡片：先给中性事实（忠实转述 narrative_fact），再给一个开放式引导问题。
6. 用 gap_level 的语义（小/中/大）说话，不要念出数字分数。

【输出格式】仅输出一个 JSON 对象：{"title":"…","body":"…","talk_prompt":"…"}，不要输出任何额外文字或代码围栏。
```

- [ ] **Step 3b: 写 `couple_report_writer.py`**

```python
# app/agents/couple_report_writer.py
"""Couple report writer — briefing → 卡片 JSON。盲区卡片 LLM 生成，其余段模板。"""
from __future__ import annotations
import json, pathlib
from app.services.llm_client import chat_completion
from app.services.couple_report_quality_gate import check_cards

_PROMPT_FILE = pathlib.Path(__file__).parents[2] / "docs" / "couple-report-system-prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")
_PAIRING_TEMPLATES = {
    "demand_withdraw": "你们可能出现「一个想立刻谈、一个想先躲开」的节奏差，值得各自说说舒服的方式。",
    "anxious_avoidant": "你们一个更需要靠近确认、一个更需要空间喘息，这不是对错，是不同的安全感来源。",
}


class CoupleReportWriterError(Exception):
    pass


def build_card_user_message(dim: dict) -> str:
    bs = dim.get("blindspot") or {}
    return "\n".join([
        f"# 盲区维度：{dim['dimension_id']}",
        f"- 中性事实（必须忠实转述）：{bs.get('narrative_fact', '')}",
        f"- 落差档位：{dim.get('gap_level', '')}",
        f"- 方向：{dim.get('direction', {})}",
        '请按系统要求输出 JSON：{"title":"...","body":"...","talk_prompt":"..."}',
    ])


def _parse_card(raw: str, dim_id: str) -> dict:
    try:
        obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise CoupleReportWriterError(f"card parse failed: {dim_id}") from exc
    return {"dimension_id": dim_id, "title": obj.get("title", ""),
            "body": obj.get("body", ""), "talk_prompt": obj.get("talk_prompt", "")}


async def run(briefing: dict, session_id: str | None = None) -> dict:
    ov = briefing["overview"]
    dims = {d["dimension_id"]: d for d in briefing["dimensions"]}
    cards = []
    for dim_id in ov["top_blindspots"]:
        if (dim := dims.get(dim_id)) is None:
            continue
        raw = await chat_completion(system_prompt=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_card_user_message(dim)}],
            temperature=0.6, agent="couple_report", session_id=session_id)
        cards.append(_parse_card(raw, dim_id))
    if not cards:
        raise CoupleReportWriterError("no blindspot cards generated")
    report = {
        "opening": {"body": "下面是你们这次双人测评里最值得一起聊的几个话题。"},
        "blindspot_cards": cards,
        "friction_section": {"body": "\n".join(_PAIRING_TEMPLATES.get(f, "")
                                               for f in ov.get("high_friction_pairings", []))},
        "strengths_section": {"body": "你们在一些方面的差异更像互补，是关系里的弹性来源。"
                              if ov.get("complementary_strengths") else ""},
        "closing": {"body": "这些话题没有标准答案，重要的是借它们多了解彼此一点。"},
    }
    report["quality_warnings"] = check_cards(report, briefing)
    return report
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/test_couple_report_writer.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add docs/couple-report-system-prompt.md app/agents/couple_report_writer.py tests/agents/test_couple_report_writer.py
git commit -m "feat(couple): 报告 Agent prompt + 卡片生成"
```

---

### Task B5: couple_report_runner（后台调度）

**Files:**
- Create: `app/services/couple_report_runner.py`
- Test: `tests/services/test_couple_report_runner.py`

**Interfaces:**
- Consumes: `couple_report_writer.run`（Task B4）、`CoupleSession`（Task B2）
- Produces:
  - `async run_and_persist(session_id: str, briefing: dict, *, log_prefix="couple/bg") -> None`
  - `schedule(session_id: str, briefing: dict, *, log_prefix="couple/bg") -> asyncio.Task`
- 行为：成功落 `report_json` + `status=complete`；失败回退 `status=analyzed`（条件更新仅作用于 `status=generating` 的行）

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_couple_report_runner.py
import asyncio, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.couple_session import CoupleSession
from app.services import couple_report_runner as runner

def _db(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    TS = sessionmaker(bind=eng)
    monkeypatch.setattr(runner, "SessionLocal", TS)
    return TS

def test_run_and_persist_success(monkeypatch):
    TS = _db(monkeypatch)
    async def fake_report(briefing, session_id=None):
        return {"opening": {"body": "x"}, "blindspot_cards": [{"dimension_id": "money"}]}
    monkeypatch.setattr(runner, "write_couple_report", fake_report)
    db = TS()
    db.add(CoupleSession(session_id="s1", pairing_token="t1", initiator_user_id=1,
                         status="generating", a_status="done", b_status="done"))
    db.commit(); db.close()
    asyncio.run(runner.run_and_persist("s1", {"overview": {}, "dimensions": []}))
    db = TS(); row = db.query(CoupleSession).filter_by(session_id="s1").first()
    assert row.status == "complete"
    assert json.loads(row.report_json)["blindspot_cards"][0]["dimension_id"] == "money"
    db.close()

def test_run_and_persist_failure_resets(monkeypatch):
    TS = _db(monkeypatch)
    from app.agents.couple_report_writer import CoupleReportWriterError
    async def boom(briefing, session_id=None): raise CoupleReportWriterError("x")
    monkeypatch.setattr(runner, "write_couple_report", boom)
    db = TS()
    db.add(CoupleSession(session_id="s2", pairing_token="t2", initiator_user_id=1, status="generating"))
    db.commit(); db.close()
    asyncio.run(runner.run_and_persist("s2", {"overview": {}, "dimensions": []}))
    db = TS(); assert db.query(CoupleSession).filter_by(session_id="s2").first().status == "analyzed"; db.close()
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/services/test_couple_report_runner.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/services/couple_report_runner.py
"""Couple report runner — 后台调度报告 Agent 并落库（对标 report_writer_runner）。"""
from __future__ import annotations
import asyncio, json, logging
from app.agents.couple_report_writer import CoupleReportWriterError, run as write_couple_report
from app.database import SessionLocal
from app.models.couple_session import CoupleSession
from app.services.couple_report_quality_gate import CoupleQualityGateError
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)


async def run_and_persist(session_id: str, briefing: dict, *, log_prefix: str = "couple/bg") -> None:
    db = SessionLocal()
    try:
        report = await write_couple_report(briefing, session_id=session_id)
        updated = (db.query(CoupleSession)
                   .filter(CoupleSession.session_id == session_id, CoupleSession.status == "generating")
                   .update({"report_json": json.dumps(report, ensure_ascii=False), "status": "complete"},
                           synchronize_session=False))
        db.commit()
        logger.info("[%s] 完成 session=%s cards=%d updated=%d", log_prefix, session_id[:8],
                    len(report.get("blindspot_cards", [])), updated)
    except (CoupleReportWriterError, CoupleQualityGateError, LLMError) as exc:
        logger.error("[%s] 报告失败 session=%s: %s", log_prefix, session_id[:8], exc)
        (db.query(CoupleSession)
           .filter(CoupleSession.session_id == session_id, CoupleSession.status == "generating")
           .update({"status": "analyzed"}, synchronize_session=False))
        db.commit()
    finally:
        db.close()


def schedule(session_id: str, briefing: dict, *, log_prefix: str = "couple/bg") -> asyncio.Task:
    return asyncio.create_task(run_and_persist(session_id, briefing, log_prefix=log_prefix))
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/services/test_couple_report_runner.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/couple_report_runner.py tests/services/test_couple_report_runner.py
git commit -m "feat(couple): 报告后台 runner"
```

---

### Task B6: api/couple.py — create + join（含路由注册）

**Files:**
- Create: `app/api/couple.py`（本任务只写 create + join）
- Modify: `app/main.py`（`include_router(couple.router)`）
- Test: `tests/api/test_couple.py`（本任务写 create/join 用例）

**Interfaces:**
- Consumes: `CoupleSession`、`fetch_couple_questions`、`get_current_user_id`、`limiter`
- Produces: `router`（prefix `/couple`）；`POST /couple/create`、`POST /couple/join`

- [ ] **Step 1: 写失败测试**

```python
# tests/api/test_couple.py
from app.models.user import User
from app.middleware.auth import create_access_token

def _headers(db_session, openid):
    u = User(openid=openid); db_session.add(u); db_session.commit(); db_session.refresh(u)
    return {"Authorization": f"Bearer {create_access_token(u.id)}"}

def _mock_q(monkeypatch):
    from app.api import couple
    async def fake_q(): return [{"question_id": "A1-1"}]
    monkeypatch.setattr(couple, "fetch_couple_questions", fake_q)

def test_create_and_join(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    r = client.post("/couple/create", headers=a)
    assert r.status_code == 200
    token, sid = r.json()["pairing_token"], r.json()["session_id"]
    b = _headers(db_session, "uB")
    r2 = client.post("/couple/join", headers=b, json={"pairing_token": token})
    assert r2.status_code == 200 and r2.json()["session_id"] == sid

def test_self_pair_rejected(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    token = client.post("/couple/create", headers=a).json()["pairing_token"]
    assert client.post("/couple/join", headers=a, json={"pairing_token": token}).status_code == 409

def test_join_unknown_token_404(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    b = _headers(db_session, "uB")
    assert client.post("/couple/join", headers=b, json={"pairing_token": "nope"}).status_code == 404
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/api/test_couple.py -v` → FAIL（404，路由未注册）

- [ ] **Step 3a: 写 `app/api/couple.py`**

```python
# app/api/couple.py
"""Couple API — 双人异步配对：create / join / answer / result。"""
import secrets, uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.couple_session import CoupleSession
from app.services.supabase_client import fetch_couple_questions

router = APIRouter(prefix="/couple", tags=["couple"])


class JoinRequest(BaseModel):
    pairing_token: str


@router.post("/create")
@limiter.limit("5/minute")
async def couple_create(request: Request, user_id: int = Depends(get_current_user_id),
                        db: Session = Depends(get_db)) -> dict:
    sess = CoupleSession(session_id=str(uuid.uuid4()), pairing_token=secrets.token_urlsafe(24),
                         initiator_user_id=user_id, status="waiting_partner",
                         a_status="pending", b_status="pending")
    db.add(sess); db.commit(); db.refresh(sess)
    return {"session_id": sess.session_id, "pairing_token": sess.pairing_token,
            "questions": await fetch_couple_questions()}


@router.post("/join")
@limiter.limit("10/minute")
async def couple_join(request: Request, body: JoinRequest,
                      user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.pairing_token == body.pairing_token).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="邀请无效")
    if sess.initiator_user_id == user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="不能和自己配对")
    if sess.partner_user_id is not None and sess.partner_user_id != user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该测评已有搭档")
    sess.partner_user_id = user_id
    db.commit()
    return {"session_id": sess.session_id, "questions": await fetch_couple_questions()}
```

- [ ] **Step 3b: 在 `main.py` 注册路由**（与现有 `include_router` 同处）

```python
from app.api import couple  # 加进现有 app.api import 行
app.include_router(couple.router)
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/api/test_couple.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/couple.py app/main.py tests/api/test_couple.py
git commit -m "feat(couple): /couple/create + /couple/join"
```

---

### Task B7: api/couple.py — answer（触发计算 + 调度报告）

**Files:**
- Modify: `app/api/couple.py`（追加 import + `POST /couple/answer`）
- Modify: `tests/api/test_couple.py`（追加用例）

**Interfaces:**
- Consumes: `build_couple_answer_package`（计划 A）、`couple_scoring_engine.run`（计划 A）、`couple_report_runner.schedule`（Task B5）
- Produces: `POST /couple/answer` → `{status}`；双方齐时条件更新触发计算（仅一次）

> 状态：`computing` 后直接写 `briefing_json` 并转 `generating`（`analyzed` 中间态省略，briefing 非空即算完）。引擎失败回退 `waiting_partner`。

- [ ] **Step 1: 写失败测试**（追加到 `tests/api/test_couple.py`）

```python
def test_answer_triggers_compute(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    from app.api import couple
    async def fake_score(pkg, session_id=None):
        return {"session_id": session_id, "overview": {"top_blindspots": []}, "dimensions": []}
    monkeypatch.setattr(couple, "couple_score_run", fake_score)
    monkeypatch.setattr(couple.couple_report_runner, "schedule", lambda *a, **k: None)
    a = _headers(db_session, "uA"); b = _headers(db_session, "uB")
    token = client.post("/couple/create", headers=a).json()["pairing_token"]
    sid = client.post("/couple/join", headers=b, json={"pairing_token": token}).json()["session_id"]
    ra = client.post("/couple/answer", headers=a,
                     json={"session_id": sid, "self": [{"question_id": "A1-1", "value": 18}]})
    assert ra.status_code == 200 and ra.json()["status"] == "waiting_partner"
    rb = client.post("/couple/answer", headers=b,
                     json={"session_id": sid, "self": [{"question_id": "A1-1", "value": 72}]})
    assert rb.json()["status"] == "generating"

def test_answer_forbidden_for_outsider(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA"); c = _headers(db_session, "uC")
    sid = client.post("/couple/create", headers=a).json()["session_id"]
    r = client.post("/couple/answer", headers=c, json={"session_id": sid, "self": []})
    assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/api/test_couple.py -k answer -v` → FAIL

- [ ] **Step 3: 追加 import 与端点到 `app/api/couple.py`**

```python
# 顶部追加：
import json
from pydantic import Field, ConfigDict
from app.agents.couple_scoring_engine import CoupleScoringError, run as couple_score_run
from app.services.couple_answer_package_builder import build_couple_answer_package
from app.services import couple_report_runner


class AnswerItem(BaseModel):
    question_id: str
    value: float


class AnswerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_id: str
    self_answers: list[AnswerItem] = Field(default_factory=list, alias="self")
    predicted: list[AnswerItem] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


async def _compute_and_launch(db: Session, session_id: str, a_json: str, b_json: str) -> None:
    pkg = build_couple_answer_package(json.loads(a_json), json.loads(b_json))
    try:
        briefing = await couple_score_run(pkg, session_id=session_id)
    except CoupleScoringError as exc:
        db.query(CoupleSession).filter(CoupleSession.session_id == session_id).update(
            {"status": "waiting_partner"}, synchronize_session=False)
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="计算失败") from exc
    db.query(CoupleSession).filter(CoupleSession.session_id == session_id).update(
        {"briefing_json": json.dumps(briefing, ensure_ascii=False), "status": "generating"},
        synchronize_session=False)
    db.commit()
    couple_report_runner.schedule(session_id, briefing)


@router.post("/answer")
@limiter.limit("5/minute")
async def couple_answer(request: Request, body: AnswerRequest,
                        user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.session_id == body.session_id).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="测评不存在")
    raw = {"self": [{"question_id": i.question_id, "value": i.value} for i in body.self_answers],
           "predicted": [{"question_id": i.question_id, "value": i.value} for i in body.predicted],
           "skipped": body.skipped}
    if user_id == sess.initiator_user_id:
        sess.a_answers_json = json.dumps(raw, ensure_ascii=False); sess.a_status = "done"
    elif user_id == sess.partner_user_id:
        sess.b_answers_json = json.dumps(raw, ensure_ascii=False); sess.b_status = "done"
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权作答该测评")
    db.commit()
    if sess.a_status == "done" and sess.b_status == "done":
        triggered = db.query(CoupleSession).filter(
            CoupleSession.session_id == body.session_id, CoupleSession.status == "waiting_partner"
        ).update({"status": "computing"}, synchronize_session=False)
        db.commit()
        if triggered:
            await _compute_and_launch(db, body.session_id, sess.a_answers_json, sess.b_answers_json)
    db.refresh(sess)
    return {"status": sess.status}
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/api/test_couple.py -k answer -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/couple.py tests/api/test_couple.py
git commit -m "feat(couple): /couple/answer 触发计算与报告调度"
```

---

### Task B8: api/couple.py — result（隐私安全的结果查询）

**Files:**
- Modify: `app/api/couple.py`（追加 `GET /couple/result`）
- Modify: `tests/api/test_couple.py`（追加用例）

**Interfaces:**
- Produces: `GET /couple/result?session_id=` → 409 未齐 / 202 生成中 / 200 卡片；**绝不下发对方裸答案**

- [ ] **Step 1: 写失败测试**（追加）

```python
def test_result_incomplete_409(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    sid = client.post("/couple/create", headers=a).json()["session_id"]
    assert client.get(f"/couple/result?session_id={sid}", headers=a).status_code == 409

def test_result_complete_returns_cards(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    sid = client.post("/couple/create", headers=a).json()["session_id"]
    from app.models.couple_session import CoupleSession
    row = db_session.query(CoupleSession).filter_by(session_id=sid).first()
    row.status = "complete"
    row.report_json = '{"blindspot_cards":[{"dimension_id":"money"}]}'
    db_session.commit()
    r = client.get(f"/couple/result?session_id={sid}", headers=a)
    assert r.status_code == 200
    assert r.json()["report"]["blindspot_cards"][0]["dimension_id"] == "money"
    assert "a_answers_json" not in r.json() and "b_answers_json" not in r.json()
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/api/test_couple.py -k result -v` → FAIL

- [ ] **Step 3: 追加端点到 `app/api/couple.py`**

```python
@router.get("/result")
@limiter.limit("30/minute")
async def couple_result(request: Request, session_id: str,
                        user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict:
    sess = db.query(CoupleSession).filter(CoupleSession.session_id == session_id).first()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="测评不存在")
    if user_id not in (sess.initiator_user_id, sess.partner_user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权查看")
    if sess.status in ("waiting_partner", "computing"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="对方尚未完成作答")
    if sess.status != "complete" or not sess.report_json:
        return {"status": "generating"}
    return {"status": "complete", "report": json.loads(sess.report_json)}
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/api/test_couple.py -v` → PASS（全部 couple api 用例）

- [ ] **Step 5: 跑全套 couple 测试 + Commit**

```bash
pytest tests/ -k couple -v
git add app/api/couple.py tests/api/test_couple.py
git commit -m "feat(couple): /couple/result 隐私安全的结果查询"
```

---

## Self-Review（计划作者已核对）

- **Spec 覆盖**：题干表（B1）→ spec 3.3；数据层 couple_sessions（B2）→ spec 4.1；质检门（B3）→ spec 6.5/7.4；报告 Agent 卡片（B4）→ spec 7.1–7.3；runner（B5）→ spec 7.5；create/join/answer/result（B6–B8）→ spec 第八章 + 状态机 4.2 + 隐私 4.3。
- **隐私红线验证**：`test_result_complete_returns_cards` 显式断言响应不含 `a_answers_json`/`b_answers_json`；`answer` 按 `user_id` 判定写列、outsider 403（`test_answer_forbidden_for_outsider`）。
- **并发触发**：`answer` 用条件更新 `waiting_partner→computing` 保证只触发一次（`triggered` 真值控制）。
- **跨计划类型一致性**：消费计划 A 的 `couple_score_run(pkg, session_id)`、`build_couple_answer_package(a_raw, b_raw)`、briefing 结构（`overview.top_blindspots` 等）与计划 A 产出一致；`couple_report_writer.run` 返回的卡片结构被 runner 落库、被 result 透传、被 quality_gate 校验，键名一致。
- **无占位符**：每步含可运行代码与命令；migration 58 题录入指明来源（题库 v1 第一部分）并给样例。

---

## Execution Handoff

计划 B 保存于 `docs/superpowers/plans/2026-06-26-couple-service-shell.md`，共 8 个任务，依赖计划 A 完成后执行。

至此双人模式后端规划完整：**设计 spec + 计划 A（引擎核心 10 任务）+ 计划 B（服务外壳 8 任务）**。执行时先 A 后 B，每个任务都是独立的 TDD 循环 + commit。

