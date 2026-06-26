# 双人落差测评 · 计划 A（引擎核心闭环）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给定一对情侣的双方作答（self + predicted），用纯 Python 确定性引擎算出契约层 JSON（落差/盲区/salience/超类）并通过 pydantic 校验——不碰 DB、不碰 LLM、不碰 HTTP。

**Architecture:** 复用现有 `scoring_engine.py` 的纯算分层。配置层（维度注册表 + 校准表）从 repo 配置文件加载；`couple_scoring/` 子包按职责拆分 6 个纯函数模块（normalize/triplet/blindspot/pairings/salience/supercluster），引擎入口 `couple_scoring_engine.run()` 编排并组装契约，`schemas/couple_briefing.py` 在产出前做自检。

**Tech Stack:** Python 3.11+、PyYAML（读 dimensions.yaml）、Pydantic v2、pytest。

## Global Constraints

> 每个任务的要求都隐含包含本节。值均逐字摘自 spec（`docs/superpowers/specs/2026-06-26-couple-gap-assessment-design.md`）与 CLAUDE.md。

- **纯算铁律**：`couple_scoring_engine` 及 `couple_scoring/` 全部子模块**无 LLM 调用、无 DB 调用**，仅确定性算术。
- **校准前不判决**：`couple_registry.get_calibration(dim_id)` 查不到专属记录时返回 `_defaults`（`calibrated_relevant=false`）→ 引擎强制该维度 `topic_only`、`salience_rank=-1`、不进超类聚合。
- **盲区轨道解耦**：`top_blindspots` 按 `accuracy_error` 降序，**独立于** `calibrated_relevant`；判决轨道（salience/超类）受校准闸门。
- **归一化公式**：slider 直通；likert7 → `(x-1)/6*100`；reverse → `100-x`；保留 2 位小数。
- **盲区阈值**：`THRESH_BLINDSPOT = {"low": 15, "moderate": 35}`（0–100 量纲；err<15 低，15–35 中，>35 高）。
- **组合规则阈值**：`HIGH = 60`。
- **分档**：`gap_level` = none(`<8`)/small/moderate/large，small/moderate 阈值取该维度 calibration 的 `gap_thresholds`。
- **命名**：新增代码统一 `couple_` 前缀；异常 `CoupleScoringError` 对标 `ScoringError`。
- **文件体积**：任何 `.py` ≤500 行；单次写入 ≤150 行（分批）。
- **测试**：在 `love-profiler/` 目录下跑 `pytest`，内存无依赖（纯函数）。

---

## File Structure

新建文件（均在 `love-profiler/app/` 与 `love-profiler/tests/` 下）：

| 文件 | 职责 |
|---|---|
| `app/agents/couple_data/dimensions.yaml` | 维度注册表（58 维度，题库 v1 第二部分落地） |
| `app/agents/couple_data/calibration.json` | 校准表（MVP 临时默认，`_defaults` 兜底） |
| `app/services/couple_registry.py` | 加载并查询注册表 + calibration（infra service） |
| `app/services/couple_answer_package_builder.py` | 双方 raw 作答 → `{A,B,skipped}` 标准包（infra） |
| `app/agents/couple_scoring/__init__.py` | 子包标识（空） |
| `app/agents/couple_scoring/normalize.py` | 单题归一化 + 同维度多题聚合 |
| `app/agents/couple_scoring/triplet.py` | 三件套（gap/direction/levels）+ anchor 标签 |
| `app/agents/couple_scoring/blindspot.py` | Cluster F 盲区 + narrative_fact 生成 |
| `app/agents/couple_scoring/pairings.py` | 组合规则（demand_withdraw/anxious_avoidant） |
| `app/agents/couple_scoring/salience.py` | 分档 gap_level + salience 排序 |
| `app/agents/couple_scoring/supercluster.py` | 4 超类聚合 |
| `app/schemas/couple_briefing.py` | 契约层 pydantic + 自检 |
| `app/agents/couple_scoring_engine.py` | 引擎入口 `run()`，编排 + 组装契约 |
| `tests/agents/couple/__init__.py` | 测试子包 |
| `tests/agents/couple/test_*.py` | 各模块单测 |
| `tests/services/test_couple_registry.py` | 配置加载测试 |
| `tests/schemas/test_couple_briefing.py` | 契约自检测试 |

依赖方向：`couple_scoring_engine → couple_scoring/* + couple_registry + couple_briefing`；`couple_registry` 只读配置文件；子模块互不依赖（纯函数）。

**任务清单（10 个）：** ①registry+配置文件 → ②builder → ③normalize → ④triplet → ⑤blindspot → ⑥pairings → ⑦salience → ⑧supercluster → ⑨briefing schema → ⑩引擎入口编排。

---

### Task 1: 维度注册表 + 校准表 + couple_registry

**Files:**
- Create: `app/agents/couple_data/dimensions.yaml`
- Create: `app/agents/couple_data/calibration.json`
- Create: `app/services/couple_registry.py`
- Test: `tests/services/test_couple_registry.py`

**Interfaces:**
- Produces:
  - `DimensionConfig`（frozen dataclass）：`id, cluster, layer, apply_prediction, complementary, level_only, skippable, anchors: dict, items: tuple`
  - `all_dimensions() -> list[DimensionConfig]`
  - `get_dimension(dim_id: str) -> DimensionConfig | None`
  - `get_calibration(dim_id: str) -> dict`（含 `calibrated_relevant, gap_thresholds:{small,moderate}, effect_size, direction_hurts`；缺失走 `_defaults`）

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_couple_registry.py
from app.services import couple_registry as reg

def test_get_dimension_money():
    d = reg.get_dimension("money")
    assert d is not None and d.cluster == "A"
    assert d.apply_prediction is True
    assert d.anchors["low"] and d.anchors["high"]
    assert len(d.items) >= 2

def test_level_only_and_skippable_flags():
    assert reg.get_dimension("emotional_stability").level_only is True
    assert reg.get_dimension("religiosity").skippable is True

def test_get_calibration_missing_falls_back_to_defaults():
    c = reg.get_calibration("money")
    assert c["calibrated_relevant"] is False
    assert c["gap_thresholds"]["small"] == 18
    assert c["effect_size"] == 0.0

def test_unknown_dimension_returns_none():
    assert reg.get_dimension("not_a_dim") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/services/test_couple_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.couple_registry`

- [ ] **Step 3a: 写 `calibration.json`（完整）**

```json
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

- [ ] **Step 3b: 写 `dimensions.yaml`（录入全部 58 维度）**

把《双人题库v1.md》第二部分 `question_bank_v1.yaml` 的 `dimensions:` 段**逐维度录入**，每维度字段与下方 3 个代表样例（覆盖 apply_prediction / complementary / level_only / skippable 各标志）对齐。缺省值：`layer` 默认 `interpretation`，未标的布尔标志默认 `false`。

```yaml
- id: money
  cluster: A
  layer: interpretation
  apply_prediction: true
  anchors: { low: "存下来更安心", high: "花在当下更值得" }
  items:
    - { id: A1-1, type: slider,  reverse: false }
    - { id: A1-2, type: slider,  reverse: false }
    - { id: A1-3, type: likert7, reverse: true }
- id: values_openness
  cluster: C
  apply_prediction: true
  complementary: true            # 禁负面措辞
  anchors: { low: "稳定/传统", high: "新鲜/冒险" }
  items:
    - { id: C2-1, type: slider,  reverse: false }
    - { id: C2-2, type: likert7, reverse: false }
- id: emotional_stability
  cluster: E
  level_only: true               # 仅呈现水平，禁判差距
  items:
    - { id: E1-1, type: likert7, reverse: true }
    - { id: E1-3, type: likert7, reverse: false }
# … 其余 55 维度同法录入（religiosity 标 skippable: true）
```

- [ ] **Step 3c: 写 `couple_registry.py`（完整）**

```python
"""Couple dimension registry — 加载 dimensions.yaml + calibration.json（只读）。
算法参数真相源；无 DB、无 LLM。
"""
from __future__ import annotations
import json, pathlib
from dataclasses import dataclass
import yaml

_DATA_DIR = pathlib.Path(__file__).parents[1] / "agents" / "couple_data"


@dataclass(frozen=True)
class DimensionConfig:
    id: str; cluster: str; layer: str
    apply_prediction: bool; complementary: bool; level_only: bool; skippable: bool
    anchors: dict; items: tuple


def _load_dimensions() -> dict[str, DimensionConfig]:
    raw = yaml.safe_load((_DATA_DIR / "dimensions.yaml").read_text(encoding="utf-8"))
    out: dict[str, DimensionConfig] = {}
    for d in raw:
        out[d["id"]] = DimensionConfig(
            id=d["id"], cluster=d["cluster"], layer=d.get("layer", "interpretation"),
            apply_prediction=bool(d.get("apply_prediction", False)),
            complementary=bool(d.get("complementary", False)),
            level_only=bool(d.get("level_only", False)),
            skippable=bool(d.get("skippable", False)),
            anchors=d.get("anchors") or {}, items=tuple(d.get("items") or []),
        )
    return out


DIMENSIONS: dict[str, DimensionConfig] = _load_dimensions()
_CALIBRATION: dict = json.loads((_DATA_DIR / "calibration.json").read_text(encoding="utf-8"))


def all_dimensions() -> list[DimensionConfig]:
    return list(DIMENSIONS.values())


def get_dimension(dim_id: str) -> DimensionConfig | None:
    return DIMENSIONS.get(dim_id)


def get_calibration(dim_id: str) -> dict:
    merged = dict(_CALIBRATION["_defaults"])
    if (entry := _CALIBRATION.get(dim_id)) and not dim_id.startswith("_"):
        merged.update(entry)
    return merged
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/services/test_couple_registry.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_data/ app/services/couple_registry.py tests/services/test_couple_registry.py
git commit -m "feat(couple): 维度注册表 + 校准表 + couple_registry 加载层"
```

---

### Task 2: couple_answer_package_builder

**Files:**
- Create: `app/services/couple_answer_package_builder.py`
- Test: `tests/services/test_couple_answer_package_builder.py`

**Interfaces:**
- Produces: `build_couple_answer_package(a_raw: dict, b_raw: dict) -> dict`
  - 入参每侧 `{"self": [{question_id,value}], "predicted": [...], "skipped": [dim_id]}`
  - 出参 `{"A": {"self": {qid:value}, "predicted": {qid:value}}, "B": {...}, "skipped": {"A": [...], "B": [...]}}`

- [ ] **Step 1: 写失败测试**

```python
# tests/services/test_couple_answer_package_builder.py
from app.services.couple_answer_package_builder import build_couple_answer_package

def test_build_merges_both_sides():
    a = {"self": [{"question_id": "A1-1", "value": 18}],
         "predicted": [{"question_id": "A1-1", "value": 35}], "skipped": []}
    b = {"self": [{"question_id": "A1-1", "value": 72}],
         "predicted": [{"question_id": "A1-1", "value": 60}], "skipped": ["religiosity"]}
    pkg = build_couple_answer_package(a, b)
    assert pkg["A"]["self"]["A1-1"] == 18
    assert pkg["A"]["predicted"]["A1-1"] == 35
    assert pkg["B"]["self"]["A1-1"] == 72
    assert pkg["skipped"]["B"] == ["religiosity"]

def test_missing_predicted_defaults_empty():
    pkg = build_couple_answer_package({"self": [{"question_id": "A1-1", "value": 18}]},
                                      {"self": [{"question_id": "A1-1", "value": 72}]})
    assert pkg["A"]["predicted"] == {}
    assert pkg["skipped"]["A"] == []
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/services/test_couple_answer_package_builder.py -v` → FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# app/services/couple_answer_package_builder.py
"""Couple answer package builder — 双方 raw 作答 → 标准包（list→dict + skipped 透传）。"""
from __future__ import annotations


def _to_map(items: list[dict] | None) -> dict[str, float]:
    return {it["question_id"]: it["value"] for it in (items or [])}


def _side(raw: dict) -> dict:
    return {"self": _to_map(raw.get("self")), "predicted": _to_map(raw.get("predicted"))}


def build_couple_answer_package(a_raw: dict, b_raw: dict) -> dict:
    return {
        "A": _side(a_raw), "B": _side(b_raw),
        "skipped": {"A": list(a_raw.get("skipped") or []), "B": list(b_raw.get("skipped") or [])},
    }
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/services/test_couple_answer_package_builder.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/couple_answer_package_builder.py tests/services/test_couple_answer_package_builder.py
git commit -m "feat(couple): 双方作答包组装 builder"
```

---

### Task 3: normalize（归一化 + 维度聚合）

**Files:**
- Create: `app/agents/couple_scoring/__init__.py`（空）, `app/agents/couple_scoring/normalize.py`
- Create: `tests/agents/couple/__init__.py`（空）
- Test: `tests/agents/couple/test_normalize.py`

**Interfaces:**
- Consumes: `DimensionConfig`（Task 1）
- Produces:
  - `normalize_item(raw: float, item_type: str, reverse: bool) -> float`
  - `aggregate_side(dim: DimensionConfig, answers: dict[str, float]) -> float | None`（无有效题→None）

- [ ] **Step 1: 写失败测试**（先建两个空 `__init__.py`）

```python
# tests/agents/couple/test_normalize.py
from app.agents.couple_scoring.normalize import normalize_item, aggregate_side
from app.services.couple_registry import DimensionConfig

def _dim(items):
    return DimensionConfig(id="d", cluster="A", layer="interpretation", apply_prediction=False,
        complementary=False, level_only=False, skippable=False, anchors={}, items=tuple(items))

def test_normalize_slider_passthrough():
    assert normalize_item(18, "slider", False) == 18.0

def test_normalize_likert7():
    assert normalize_item(7, "likert7", False) == 100.0
    assert normalize_item(1, "likert7", False) == 0.0
    assert normalize_item(4, "likert7", False) == 50.0

def test_normalize_reverse():
    assert normalize_item(7, "likert7", True) == 0.0
    assert normalize_item(18, "slider", True) == 82.0

def test_aggregate_mean():
    dim = _dim([{"id": "A1-1", "type": "slider", "reverse": False},
                {"id": "A1-3", "type": "likert7", "reverse": True}])
    # A1-1 slider 30→30；A1-3 likert7=7 reverse→0；mean=15
    assert aggregate_side(dim, {"A1-1": 30, "A1-3": 7}) == 15.0

def test_aggregate_empty_returns_none():
    dim = _dim([{"id": "Z1", "type": "slider", "reverse": False}])
    assert aggregate_side(dim, {}) is None
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_normalize.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/normalize.py
"""Normalize + 维度聚合（纯函数）。slider 直通 / likert7→0-100 / reverse→100-x。"""
from __future__ import annotations
from app.services.couple_registry import DimensionConfig


def normalize_item(raw: float, item_type: str, reverse: bool) -> float:
    x = float(raw) if item_type == "slider" else (float(raw) - 1) / 6 * 100
    return round(100 - x if reverse else x, 2)


def aggregate_side(dim: DimensionConfig, answers: dict[str, float]) -> float | None:
    vals = [normalize_item(answers[it["id"]], it["type"], it["reverse"])
            for it in dim.items if it["id"] in answers]
    return round(sum(vals) / len(vals), 2) if vals else None
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_normalize.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/ tests/agents/couple/
git commit -m "feat(couple): normalize 归一化 + 维度聚合"
```

---

### Task 4: triplet（三件套 + anchor 标签）

**Files:**
- Create: `app/agents/couple_scoring/triplet.py`
- Test: `tests/agents/couple/test_triplet.py`

**Interfaces:**
- Consumes: `DimensionConfig`（Task 1）
- Produces:
  - `anchor_label(score: float, dim: DimensionConfig) -> str`（无 anchors 返回 `""`；`<40` low，`>60` high，否则 `"介于两者之间"`）
  - `triplet(s_A: float, s_B: float, dim: DimensionConfig) -> dict` → `{"gap", "direction": {"higher_partner","label_a","label_b"}, "levels": {"a","b"}}`

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/couple/test_triplet.py
from app.agents.couple_scoring.triplet import anchor_label, triplet
from app.services.couple_registry import DimensionConfig

def _dim(anchors):
    return DimensionConfig(id="money", cluster="A", layer="interpretation", apply_prediction=True,
        complementary=False, level_only=False, skippable=False, anchors=anchors, items=())

def test_anchor_label_low_high_mid():
    dim = _dim({"low": "存钱", "high": "花钱"})
    assert anchor_label(20, dim) == "存钱"
    assert anchor_label(80, dim) == "花钱"
    assert anchor_label(50, dim) == "介于两者之间"

def test_anchor_label_no_anchors():
    assert anchor_label(20, _dim({})) == ""

def test_triplet_shape():
    t = triplet(18, 72, _dim({"low": "存钱", "high": "花钱"}))
    assert t["gap"] == 54.0
    assert t["direction"]["higher_partner"] == "B"
    assert t["direction"]["label_a"] == "存钱"
    assert t["direction"]["label_b"] == "花钱"
    assert t["levels"] == {"a": 18, "b": 72}
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_triplet.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/triplet.py
"""三件套：gap / direction / levels。永不只给裸差值（保留 levels 区分高-高/低-低/高-低）。"""
from __future__ import annotations
from app.services.couple_registry import DimensionConfig

_LOW, _HIGH = 40.0, 60.0


def anchor_label(score: float, dim: DimensionConfig) -> str:
    low, high = dim.anchors.get("low", ""), dim.anchors.get("high", "")
    if not low and not high:
        return ""
    if score < _LOW:
        return low
    if score > _HIGH:
        return high
    return "介于两者之间"


def triplet(s_A: float, s_B: float, dim: DimensionConfig) -> dict:
    return {
        "gap": round(abs(s_A - s_B), 2),
        "direction": {
            "higher_partner": "A" if s_A > s_B else "B",
            "label_a": anchor_label(s_A, dim),
            "label_b": anchor_label(s_B, dim),
        },
        "levels": {"a": s_A, "b": s_B},
    }
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_triplet.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/triplet.py tests/agents/couple/test_triplet.py
git commit -m "feat(couple): triplet 三件套 + anchor 标签"
```

---

### Task 5: blindspot（Cluster F 盲区 + narrative_fact）

**Files:**
- Create: `app/agents/couple_scoring/blindspot.py`
- Test: `tests/agents/couple/test_blindspot.py`

**Interfaces:**
- Consumes: `DimensionConfig`（Task 1）、`anchor_label`（Task 4）
- Produces:
  - `severity_bucket(err: float) -> str`（`<8` none，`<15` low，`<35` moderate，否则 high）
  - `blindspot(s_A, s_B, p_A2B, p_B2A, dim) -> dict` → `{"exists","severity","who_misjudged","assumed_close","accuracy_error","narrative_fact"}`

> 说明：`<8` 判 none 是对技术文档（注释仅给 low/moderate/high）的合理细化——`accuracy_error` 极小说明猜得准、无盲区，让 `exists` 有判别力。

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/couple/test_blindspot.py
from app.agents.couple_scoring.blindspot import blindspot, severity_bucket
from app.services.couple_registry import DimensionConfig

def _dim():
    return DimensionConfig(id="money", cluster="A", layer="interpretation", apply_prediction=True,
        complementary=False, level_only=False, skippable=False,
        anchors={"low": "存钱", "high": "花钱"}, items=())

def test_severity_bucket():
    assert severity_bucket(5) == "none"
    assert severity_bucket(12) == "low"
    assert severity_bucket(25) == "moderate"
    assert severity_bucket(40) == "high"

def test_blindspot_high_error_picks_worse_guesser():
    # s_A=18,s_B=72; A 猜 B=35→err 37; B 猜 A=60→err 42 ⇒ who=B, err=42 high
    bs = blindspot(18, 72, 35, 60, _dim())
    assert bs["who_misjudged"] == "B"
    assert bs["accuracy_error"] == 42.0
    assert bs["severity"] == "high" and bs["exists"] is True
    assert "「存钱」" in bs["narrative_fact"]      # 关于 A 的真实方向

def test_blindspot_assumed_close():
    # A 猜 B=20（以为与自己 18 接近），实际 gap 54 ⇒ assumed_close True
    bs = blindspot(18, 72, 20, 18, _dim())
    assert bs["who_misjudged"] == "A"
    assert bs["assumed_close"] is True

def test_blindspot_none_when_accurate():
    bs = blindspot(50, 52, 52, 50, _dim())   # 双方都猜得很准
    assert bs["exists"] is False
    assert bs["narrative_fact"] == ""
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_blindspot.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/blindspot.py
"""Cluster F 盲区计算 + narrative_fact 生成（引擎产出中性事实，不交给 LLM）。"""
from __future__ import annotations
from app.services.couple_registry import DimensionConfig
from app.agents.couple_scoring.triplet import anchor_label

THRESH_BLINDSPOT = {"low": 15.0, "moderate": 35.0}
_NONE_MAX = 8.0


def severity_bucket(err: float) -> str:
    if err < _NONE_MAX: return "none"
    if err < THRESH_BLINDSPOT["low"]: return "low"
    if err < THRESH_BLINDSPOT["moderate"]: return "moderate"
    return "high"


def build_narrative_fact(who: str, dim: DimensionConfig, s_A: float, s_B: float) -> str:
    other = "B" if who == "A" else "A"
    label = anchor_label(s_B if other == "B" else s_A, dim)
    if not label or label == "介于两者之间":
        return f"{other} 的真实态度与 {who} 的预想存在明显落差"
    return f"{other} 比 {who} 预想的更倾向「{label}」"


def blindspot(s_A: float, s_B: float, p_A2B: float, p_B2A: float, dim: DimensionConfig) -> dict:
    actual_gap = abs(s_A - s_B)
    accuracy_A, accuracy_B = abs(p_A2B - s_B), abs(p_B2A - s_A)
    who = "A" if accuracy_A >= accuracy_B else "B"
    err = max(accuracy_A, accuracy_B)
    assumed = abs(s_A - p_A2B) if who == "A" else abs(s_B - p_B2A)
    sev = severity_bucket(err)
    return {
        "exists": sev != "none",
        "severity": sev,
        "who_misjudged": who,
        "assumed_close": assumed < actual_gap,
        "accuracy_error": round(err, 2),
        "narrative_fact": build_narrative_fact(who, dim, s_A, s_B) if sev != "none" else "",
    }
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_blindspot.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/blindspot.py tests/agents/couple/test_blindspot.py
git commit -m "feat(couple): blindspot 盲区计算 + narrative_fact"
```

---

### Task 6: pairings（组合配对规则）

**Files:**
- Create: `app/agents/couple_scoring/pairings.py`
- Test: `tests/agents/couple/test_pairings.py`

**Interfaces:**
- Produces: `pairings(scores: dict) -> list[str]`
  - `scores = {"A": {dim_id: score}, "B": {dim_id: score}}`；返回命中的 flag 列表（`demand_withdraw` / `anxious_avoidant`）

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/couple/test_pairings.py
from app.agents.couple_scoring.pairings import pairings

def test_demand_withdraw_flag():
    scores = {"A": {"confront": 70, "withdraw": 10}, "B": {"confront": 10, "withdraw": 80}}
    assert "demand_withdraw" in pairings(scores)

def test_anxious_avoidant_reverse_direction():
    scores = {"A": {"attach_anxiety": 10, "attach_avoid": 75},
              "B": {"attach_anxiety": 70, "attach_avoid": 10}}
    assert "anxious_avoidant" in pairings(scores)

def test_no_flag_below_threshold():
    assert pairings({"A": {"confront": 50, "withdraw": 50},
                     "B": {"confront": 50, "withdraw": 50}}) == []
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_pairings.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/pairings.py
"""组合配对规则（维度无关全局信号）。高摩擦来自组合而非差距大小。"""
from __future__ import annotations

HIGH = 60.0
_RULES = [("demand_withdraw", "confront", "withdraw"),
          ("anxious_avoidant", "attach_anxiety", "attach_avoid")]


def _cross(scores: dict, x: str, y: str) -> bool:
    a, b = scores.get("A", {}), scores.get("B", {})
    return (a.get(x, 0) > HIGH and b.get(y, 0) > HIGH) or \
           (b.get(x, 0) > HIGH and a.get(y, 0) > HIGH)


def pairings(scores: dict) -> list[str]:
    return [flag for flag, x, y in _RULES if _cross(scores, x, y)]
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_pairings.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/pairings.py tests/agents/couple/test_pairings.py
git commit -m "feat(couple): pairings 组合配对规则"
```

---

### Task 7: salience（分档 + 排序）

**Files:**
- Create: `app/agents/couple_scoring/salience.py`
- Test: `tests/agents/couple/test_salience.py`

**Interfaces:**
- Produces:
  - `gap_level(gap: float, thresholds: dict) -> str`（`<8` none / `<small` small / `<moderate` moderate / 否则 large）
  - `salience(gap: float, blindspot: dict | None, calib: dict) -> float`（未校准→`-1.0`）
  - `assign_salience_ranks(dims: list[dict]) -> None`（原地写 `salience_rank`；读各 dim 的 `"salience"` 键）

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/couple/test_salience.py
from app.agents.couple_scoring.salience import gap_level, salience, assign_salience_ranks

def test_gap_level():
    th = {"small": 18, "moderate": 40}
    assert gap_level(5, th) == "none"
    assert gap_level(12, th) == "small"
    assert gap_level(30, th) == "moderate"
    assert gap_level(54, th) == "large"

def test_salience_uncalibrated():
    assert salience(54, {"exists": True, "accuracy_error": 40},
                    {"calibrated_relevant": False, "effect_size": 0.0}) == -1.0

def test_salience_calibrated():
    # g=0.54,b=0.4 → 0.3*(0.6*0.54+0.4*0.4)=0.1452
    assert salience(54, {"exists": True, "accuracy_error": 40},
                    {"calibrated_relevant": True, "effect_size": 0.3}) == 0.1452

def test_assign_ranks():
    dims = [{"salience": 0.1}, {"salience": -1.0}, {"salience": 0.3}]
    assign_salience_ranks(dims)
    assert dims[2]["salience_rank"] == 1
    assert dims[0]["salience_rank"] == 2
    assert dims[1]["salience_rank"] == -1
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_salience.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/salience.py
"""分档 gap_level + 判决轨道 salience 排序。校准闸门在此。"""
from __future__ import annotations

_NONE_MAX = 8.0


def gap_level(gap: float, thresholds: dict) -> str:
    if gap < _NONE_MAX: return "none"
    if gap < thresholds["small"]: return "small"
    if gap < thresholds["moderate"]: return "moderate"
    return "large"


def salience(gap: float, blindspot: dict | None, calib: dict) -> float:
    if not calib["calibrated_relevant"]:
        return -1.0
    g = gap / 100.0
    b = (blindspot["accuracy_error"] / 100.0) if (blindspot and blindspot.get("exists")) else 0.0
    return round(calib["effect_size"] * (0.6 * g + 0.4 * b), 4)


def assign_salience_ranks(dims: list[dict]) -> None:
    ranked = sorted((d for d in dims if d["salience"] >= 0),
                    key=lambda d: d["salience"], reverse=True)
    for i, d in enumerate(ranked, 1):
        d["salience_rank"] = i
    for d in dims:
        if d["salience"] < 0:
            d["salience_rank"] = -1
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_salience.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/salience.py tests/agents/couple/test_salience.py
git commit -m "feat(couple): salience 分档 + 判决轨道排序"
```

---

### Task 8: supercluster（4 超类聚合）

**Files:**
- Create: `app/agents/couple_scoring/supercluster.py`
- Test: `tests/agents/couple/test_supercluster.py`

**Interfaces:**
- Produces: `supercluster_scores(dims: list[dict]) -> dict[str, float | None]`
  - 每个 dim 需含：`dimension_id, cluster, gap, calibrated_relevant, effect_size, apply_prediction, level_only, levels, blindspot`
  - 仅 `calibrated_relevant=True` 维度参与；`perceptual_blindspot` 用 `blindspot.accuracy_error`，`level_only` 维度用 `levels` 均值，其余用 `gap`；无参与维度→`None`

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/couple/test_supercluster.py
from app.agents.couple_scoring.supercluster import supercluster_scores

def _d(dim_id, cluster, gap, relevant, eff=0.0, **extra):
    base = {"dimension_id": dim_id, "cluster": cluster, "gap": gap,
            "calibrated_relevant": relevant, "effect_size": eff,
            "apply_prediction": False, "level_only": False,
            "levels": {"a": 0, "b": 0}, "blindspot": None}
    base.update(extra); return base

def test_all_none_when_uncalibrated():
    scores = supercluster_scores([_d("money", "A", 54, False), _d("confront", "B", 30, False)])
    assert scores == {"life_expectations": None, "conflict_process": None,
                      "values_attachment": None, "perceptual_blindspot": None}

def test_life_expectations_weighted():
    dims = [_d("money", "A", 60, True, eff=0.3), _d("chores", "A", 40, True, eff=0.1)]
    # (0.3*60+0.1*40)/0.4 = 55.0
    assert supercluster_scores(dims)["life_expectations"] == 55.0

def test_perceptual_blindspot_uses_accuracy_error():
    dims = [_d("money", "A", 54, True, eff=0.3, apply_prediction=True,
               blindspot={"accuracy_error": 40, "exists": True})]
    scores = supercluster_scores(dims)
    assert scores["life_expectations"] == 54.0      # 用 gap
    assert scores["perceptual_blindspot"] == 40.0   # 用 accuracy_error
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/couple/test_supercluster.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring/supercluster.py
"""4 超类聚合（仅 calibrated_relevant 维度按 effect_size 加权）。MVP 全 None。"""
from __future__ import annotations

SUPERCLUSTERS = {
    "life_expectations":    {"clusters": ("A",)},
    "conflict_process":     {"clusters": ("B",), "extra": ("emotional_stability",)},
    "values_attachment":    {"clusters": ("C", "D")},
    "perceptual_blindspot": {"prediction": True},
}


def _selected(d: dict, spec: dict) -> bool:
    if not d.get("calibrated_relevant"):
        return False
    if spec.get("prediction"):
        return bool(d.get("apply_prediction"))
    return d["cluster"] in spec.get("clusters", ()) or d["dimension_id"] in spec.get("extra", ())


def _value(d: dict, spec: dict) -> float:
    if spec.get("prediction"):
        return (d.get("blindspot") or {}).get("accuracy_error", 0.0)
    if d.get("level_only"):                       # 守 level_only 铁律：取水平均值不计 gap
        lv = d["levels"]; return (lv["a"] + lv["b"]) / 2
    return d["gap"]


def supercluster_scores(dims: list[dict]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name, spec in SUPERCLUSTERS.items():
        chosen = [d for d in dims if _selected(d, spec)]
        den = sum(d["effect_size"] for d in chosen)
        out[name] = round(sum(d["effect_size"] * _value(d, spec) for d in chosen) / den, 1) if den else None
    return out
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/couple/test_supercluster.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/agents/couple_scoring/supercluster.py tests/agents/couple/test_supercluster.py
git commit -m "feat(couple): supercluster 4 超类聚合"
```

---

### Task 9: couple_briefing 契约 schema + 自检

**Files:**
- Create: `app/schemas/couple_briefing.py`
- Test: `tests/schemas/test_couple_briefing.py`

**Interfaces:**
- Produces: `CoupleBlindspot`, `CoupleDimensionResult`, `CoupleOverview`, `CoupleBriefing`（pydantic）
- 自检：①blindspot.exists→narrative_fact 非空；②interpretation 维度必须 calibrated_relevant；③complementary 方向禁负面词；④salience_rank 在 relevant 维度连续唯一从 1

- [ ] **Step 1: 写失败测试**

```python
# tests/schemas/test_couple_briefing.py
import pytest
from pydantic import ValidationError
from app.schemas.couple_briefing import CoupleBriefing, CoupleDimensionResult

def _dim(**over):
    base = dict(dimension_id="money", cluster="A", layer="topic_only", calibrated_relevant=False,
                complementary=False, level_only=False, gap=54.0, gap_level="large",
                direction={"higher_partner": "B", "label_a": "存钱", "label_b": "花钱"},
                levels={"a": 18, "b": 72}, blindspot=None, salience_rank=-1)
    base.update(over); return base

def _ov(**over):
    base = dict(top_blindspots=[], supercluster_scores={}, high_friction_pairings=[],
                complementary_strengths=[])
    base.update(over); return base

def test_valid_mvp_briefing():
    b = CoupleBriefing(session_id="s", question_set_version="v1", overview=_ov(top_blindspots=["money"]),
        dimensions=[_dim(blindspot={"exists": True, "severity": "high", "who_misjudged": "B",
            "assumed_close": True, "accuracy_error": 42.0, "narrative_fact": "A 比 B 预想的更倾向「存钱」"})])
    assert b.dimensions[0].blindspot.severity == "high"

def test_blindspot_exists_requires_fact():
    with pytest.raises(ValidationError):
        CoupleDimensionResult(**_dim(blindspot={"exists": True, "severity": "high", "who_misjudged": "B",
            "assumed_close": True, "accuracy_error": 42.0, "narrative_fact": ""}))

def test_interpretation_must_be_calibrated():
    with pytest.raises(ValidationError):
        CoupleDimensionResult(**_dim(layer="interpretation", calibrated_relevant=False))

def test_complementary_rejects_negative():
    with pytest.raises(ValidationError):
        CoupleDimensionResult(**_dim(complementary=True,
            direction={"higher_partner": "B", "label_a": "稳定", "label_b": "有问题"}))

def test_salience_must_be_contiguous():
    with pytest.raises(ValidationError):
        CoupleBriefing(session_id="s", overview=_ov(),
            dimensions=[_dim(layer="interpretation", calibrated_relevant=True, salience_rank=2)])
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/schemas/test_couple_briefing.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/schemas/couple_briefing.py
"""Couple briefing 契约层 schema（引擎↔Agent 接口）+ 产出前自检。"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, model_validator

_NEGATIVE_WORDS = ("缺陷", "问题", "不足", "糟", "失败", "病态")


class CoupleBlindspot(BaseModel):
    model_config = ConfigDict(extra="allow")
    exists: bool; severity: str; who_misjudged: str
    assumed_close: bool; accuracy_error: float; narrative_fact: str = ""


class CoupleDimensionResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    dimension_id: str; cluster: str; layer: str
    calibrated_relevant: bool; complementary: bool; level_only: bool
    gap: float; gap_level: str; direction: dict; levels: dict
    blindspot: CoupleBlindspot | None = None
    salience_rank: int

    @model_validator(mode="after")
    def _check(self):
        if self.blindspot and self.blindspot.exists and not self.blindspot.narrative_fact.strip():
            raise ValueError(f"{self.dimension_id}: exists 但 narrative_fact 为空")
        if self.layer == "interpretation" and not self.calibrated_relevant:
            raise ValueError(f"{self.dimension_id}: interpretation 未校准应降级 topic_only")
        if self.complementary:
            text = f"{self.direction.get('label_a','')}{self.direction.get('label_b','')}"
            if (hit := [w for w in _NEGATIVE_WORDS if w in text]):
                raise ValueError(f"{self.dimension_id}: complementary 方向含负面词 {hit}")
        return self


class CoupleOverview(BaseModel):
    model_config = ConfigDict(extra="allow")
    top_blindspots: list[str]; supercluster_scores: dict[str, float | None]
    high_friction_pairings: list[str]; complementary_strengths: list[str]


class CoupleBriefing(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str; overview: CoupleOverview
    dimensions: list[CoupleDimensionResult]; question_set_version: str = ""

    @model_validator(mode="after")
    def _check_salience(self):
        ranks = sorted(d.salience_rank for d in self.dimensions if d.calibrated_relevant)
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"salience_rank 必须连续唯一从 1：{ranks}")
        return self
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/schemas/test_couple_briefing.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/couple_briefing.py tests/schemas/test_couple_briefing.py
git commit -m "feat(couple): 契约层 schema + 产出前自检"
```

---

### Task 10: couple_scoring_engine 入口编排（端到端）

**Files:**
- Create: `app/agents/couple_scoring_engine.py`
- Test: `tests/agents/test_couple_scoring_engine.py`

**Interfaces:**
- Consumes: 全部 Task 1–9（registry、normalize、triplet、blindspot、pairings、salience、supercluster、CoupleBriefing）
- Produces:
  - `CoupleScoringError(Exception)`
  - `async run(answer_pkg: dict, session_id=None, question_set_version="v1") -> dict`（返回经 `CoupleBriefing` 校验的契约 dict）

> 测试用 `asyncio.run()` 驱动 async（不依赖 pytest-asyncio）。

- [ ] **Step 1: 写失败测试**

```python
# tests/agents/test_couple_scoring_engine.py
import asyncio
import pytest
from app.agents.couple_scoring_engine import run, CoupleScoringError
from app.services.couple_answer_package_builder import build_couple_answer_package

def test_run_produces_blindspot_briefing():
    a = {"self": [{"question_id": "A1-1", "value": 18}, {"question_id": "A1-2", "value": 20}],
         "predicted": [{"question_id": "A1-1", "value": 22}, {"question_id": "A1-2", "value": 20}]}
    b = {"self": [{"question_id": "A1-1", "value": 80}, {"question_id": "A1-2", "value": 75}],
         "predicted": [{"question_id": "A1-1", "value": 78}, {"question_id": "A1-2", "value": 75}]}
    briefing = asyncio.run(run(build_couple_answer_package(a, b), session_id="sess1"))
    assert briefing["session_id"] == "sess1"
    money = next(d for d in briefing["dimensions"] if d["dimension_id"] == "money")
    assert money["layer"] == "topic_only" and money["calibrated_relevant"] is False
    assert money["salience_rank"] == -1                       # 判决轨道降级
    assert money["blindspot"]["exists"] is True               # 盲区轨道仍输出
    assert "money" in briefing["overview"]["top_blindspots"]
    assert briefing["overview"]["supercluster_scores"]["life_expectations"] is None

def test_run_empty_raises():
    with pytest.raises(CoupleScoringError):
        asyncio.run(run({}))
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/agents/test_couple_scoring_engine.py -v` → FAIL

- [ ] **Step 3: 写实现**

```python
# app/agents/couple_scoring_engine.py
"""Couple scoring engine — 纯算入口。双方作答 → 契约 JSON（无 LLM/DB）。"""
from __future__ import annotations
from app.services import couple_registry as reg
from app.agents.couple_scoring.normalize import aggregate_side
from app.agents.couple_scoring.triplet import triplet
from app.agents.couple_scoring.blindspot import blindspot
from app.agents.couple_scoring.pairings import pairings
from app.agents.couple_scoring.salience import gap_level, salience, assign_salience_ranks
from app.agents.couple_scoring.supercluster import supercluster_scores
from app.schemas.couple_briefing import CoupleBriefing

_TOP_N = 3


class CoupleScoringError(Exception):
    """引擎无法完成计算时抛出。"""


def _build_dim(dim, s_A, s_B, p_A2B, p_B2A) -> dict:
    calib = reg.get_calibration(dim.id)
    t = triplet(s_A, s_B, dim)
    bs = (blindspot(s_A, s_B, p_A2B, p_B2A, dim)
          if dim.apply_prediction and p_A2B is not None and p_B2A is not None else None)
    return {
        "dimension_id": dim.id, "cluster": dim.cluster,
        "layer": "interpretation" if calib["calibrated_relevant"] else "topic_only",
        "calibrated_relevant": calib["calibrated_relevant"], "effect_size": calib["effect_size"],
        "complementary": dim.complementary, "level_only": dim.level_only,
        "apply_prediction": dim.apply_prediction,
        "gap": t["gap"], "gap_level": gap_level(t["gap"], calib["gap_thresholds"]),
        "direction": t["direction"], "levels": t["levels"],
        "blindspot": bs, "salience": salience(t["gap"], bs, calib), "salience_rank": -1,
    }


async def run(answer_pkg: dict, session_id: str | None = None, question_set_version: str = "v1") -> dict:
    if not answer_pkg or not answer_pkg.get("A") or not answer_pkg.get("B"):
        raise CoupleScoringError("empty package")
    A, B = answer_pkg["A"], answer_pkg["B"]
    sk = answer_pkg.get("skipped", {})
    skip = set(sk.get("A", [])) | set(sk.get("B", []))
    dims: list[dict] = []
    scores = {"A": {}, "B": {}}
    for dim in reg.all_dimensions():
        if dim.id in skip:
            continue
        s_A, s_B = aggregate_side(dim, A["self"]), aggregate_side(dim, B["self"])
        if s_A is None or s_B is None:
            continue
        scores["A"][dim.id], scores["B"][dim.id] = s_A, s_B
        p_A2B = aggregate_side(dim, A["predicted"]) if dim.apply_prediction else None
        p_B2A = aggregate_side(dim, B["predicted"]) if dim.apply_prediction else None
        dims.append(_build_dim(dim, s_A, s_B, p_A2B, p_B2A))
    assign_salience_ranks(dims)
    top = sorted((d for d in dims if d["blindspot"] and d["blindspot"]["exists"]),
                 key=lambda d: d["blindspot"]["accuracy_error"], reverse=True)
    briefing = {
        "session_id": session_id or "",
        "overview": {
            "top_blindspots": [d["dimension_id"] for d in top[:_TOP_N]],
            "supercluster_scores": supercluster_scores(dims),
            "high_friction_pairings": pairings(scores),
            "complementary_strengths": [d["dimension_id"] for d in dims
                                        if d["complementary"] and d["gap_level"] == "large"],
        },
        "dimensions": dims, "question_set_version": question_set_version,
    }
    CoupleBriefing.model_validate(briefing)
    return briefing
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/agents/test_couple_scoring_engine.py -v` → PASS

- [ ] **Step 5: 跑全套引擎测试 + Commit**

```bash
pytest tests/agents/couple/ tests/agents/test_couple_scoring_engine.py tests/schemas/test_couple_briefing.py tests/services/test_couple_registry.py tests/services/test_couple_answer_package_builder.py -v
git add app/agents/couple_scoring_engine.py tests/agents/test_couple_scoring_engine.py
git commit -m "feat(couple): 引擎入口编排 + 端到端契约组装"
```

---

## Self-Review（计划作者已核对）

- **Spec 覆盖**：配置层（Task 1）、builder（Task 2）、引擎 7 步（Task 3–8）、契约+自检（Task 9）、入口编排+盲区轨道解耦（Task 10）全部对应 spec 第三/五/六章。报告 Agent/API/数据层属计划 B，不在本计划。
- **盲区轨道解耦验证**：Task 10 测试显式断言 `salience_rank == -1`（判决降级）同时 `blindspot.exists is True` 且 `top_blindspots` 含该维度——MVP 主菜成立。
- **类型一致性**：`DimensionConfig` 字段、`get_calibration` 返回结构、各子函数签名在 Task 1 定义后，Task 3–10 一致引用；维度结果 dict 的键（`salience`/`effect_size`/`apply_prediction`/`blindspot`）被 salience/supercluster/schema 一致消费。
- **无占位符**：每步含可运行代码与命令；`dimensions.yaml` 全量录入指明来源（题库 v1 第二部分）并给 3 个覆盖全标志的格式锚点。

---

## Execution Handoff

计划保存于 `docs/superpowers/plans/2026-06-26-couple-engine-core.md`，共 10 个任务。计划 B（数据层 + 报告 Agent + API）依赖本计划产出的引擎与契约，将在本计划完成后单独编写。

