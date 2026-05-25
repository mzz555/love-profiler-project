import copy

import pytest

from app.agents.scoring_engine import (
    ScoringError as AgentAError,  # alias for minimal test diff
    _compute_diagnosis,
    run,
)


# ── helpers to build consistent answer packages ────────────────────────────────

def _mk_answer(qid: str, score_value: int, score_meta: dict | None = None,
               option: str = "a") -> dict:
    return {
        "question_id": qid,
        "dimension_code": "",
        "signal_code": "",
        "signal_name": "",
        "question_type": "",
        "selected_option": option,
        "score_value": score_value,
        "score_meta": score_meta or {},
    }


def _all_positive() -> list[dict]:
    """All answers +2 (healthy end) — expect S-CL-H."""
    return [_mk_answer(f"D{d}-Q{q:02d}", 2) for d in range(1, 6) for q in range(1, 7)]


def _all_negative() -> list[dict]:
    """All answers -2 (problem end) — expect A-BL-P."""
    return [_mk_answer(f"D{d}-Q{q:02d}", -2) for d in range(1, 6) for q in range(1, 7)]


# ── D1-D3 intensity scoring ───────────────────────────────────────────────────

def test_d1_all_positive_yields_secure():
    d = _compute_diagnosis(_all_positive())
    assert d["dimensions"]["D1"]["interp"] == "secure"


def test_d1_all_negative_yields_anxious():
    d = _compute_diagnosis(_all_negative())
    assert d["dimensions"]["D1"]["interp"] == "anxious"


def test_d1_mixed_threshold():
    """raw_total=0 → moderate_secure (≥0 归健康侧)"""
    answers = _all_positive()
    # 3*(-2) + 3*(+2) = 0 → moderate_secure
    for a in answers:
        if a["question_id"] in ("D1-Q01", "D1-Q02", "D1-Q03"):
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D1"]["interp"] == "moderate_secure"


def test_d2_all_positive_yields_clear():
    d = _compute_diagnosis(_all_positive())
    assert d["dimensions"]["D2"]["interp"] == "clear"


def test_d2_all_negative_yields_blurred():
    d = _compute_diagnosis(_all_negative())
    assert d["dimensions"]["D2"]["interp"] == "blurred"


def test_d3_all_positive_yields_healthy():
    d = _compute_diagnosis(_all_positive())
    assert d["dimensions"]["D3"]["interp"] == "healthy"


def test_d3_all_negative_yields_problematic():
    d = _compute_diagnosis(_all_negative())
    assert d["dimensions"]["D3"]["interp"] == "problematic"


# ── D3-Q06 pursue/avoid ───────────────────────────────────────────────────────

def test_d3_q06_pursue():
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D3-Q06":
            a["selected_option"] = "c"
            a["score_meta"] = {"pursue_avoid": "pursue"}
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D3"]["pursue_avoid"] == "pursue"
    assert any(h["code"] == "add-g-pa-pursuer" for h in d["highlights"])


def test_d3_q06_avoid():
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D3-Q06":
            a["selected_option"] = "d"
            a["score_meta"] = {"pursue_avoid": "avoid"}
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D3"]["pursue_avoid"] == "avoid"
    assert any(h["code"] == "add-g-pa-avoider" for h in d["highlights"])


def test_d3_q06_aware_breaker():
    answers = _all_positive()
    # _all_positive uses option "a" → aware_breaker
    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D3"]["pursue_avoid"] == "aware_breaker"
    assert any(h["code"] == "add-g-pa-aware" for h in d["highlights"])


# ── D4 normalization ──────────────────────────────────────────────────────────

def test_d4_normalization_prevents_t3_underestimation():
    """T3 max is 6 vs T1 max 9 — same raw=6 should make T3 rank higher."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"].startswith("D4"):
            a["score_value"] = 0
    for a in answers:
        if a["question_id"] == "D4-Q01":
            a["score_value"] = 6
            a["score_meta"] = {"love_language": "T1"}
        elif a["question_id"] == "D4-Q02":
            a["score_value"] = 6
            a["score_meta"] = {"love_language": "T3"}

    d = _compute_diagnosis(answers)
    norm = d["dimensions"]["D4"]["normalized"]
    top2 = d["dimensions"]["D4"]["top2"]
    assert norm["T3"] == 1.0
    assert norm["T1"] == pytest.approx(0.67, abs=0.01)
    assert top2[0] == "T3"


def test_d4_top2_sorting():
    """T2=8/8=1.0, T4=5/9=0.56 → top2=['T2','T4']"""
    answers = _all_positive()
    for a in answers:
        if a["question_id"].startswith("D4"):
            a["score_value"] = 0
    for a in answers:
        if a["question_id"] == "D4-Q01":
            a["score_value"] = 8
            a["score_meta"] = {"love_language": "T2"}
        elif a["question_id"] == "D4-Q02":
            a["score_value"] = 5
            a["score_meta"] = {"love_language": "T4"}

    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D4"]["top2"] == ["T2", "T4"]


def test_d4_alignment_with_primary():
    """primary_choice matches top1 → aligned=True"""
    answers = _all_positive()
    for a in answers:
        if a["question_id"].startswith("D4"):
            a["score_value"] = 0
    for a in answers:
        if a["question_id"] == "D4-Q01":
            a["score_value"] = 9
            a["score_meta"] = {"love_language": "T1"}
    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D4"]["aligned"] is True
    assert d["dimensions"]["D4"]["declared"] == "T1"


def test_d4_misaligned():
    """primary_choice != top1 → aligned=False, love-blind highlight fired"""
    answers = _all_positive()
    for a in answers:
        if a["question_id"].startswith("D4"):
            a["score_value"] = 0
    for a in answers:
        if a["question_id"] == "D4-Q01":
            a["score_value"] = 2
            a["score_meta"] = {"love_language": "T1"}
        elif a["question_id"] == "D4-Q02":
            a["score_value"] = 8
            a["score_meta"] = {"love_language": "T2"}

    d = _compute_diagnosis(answers)
    assert d["dimensions"]["D4"]["aligned"] is False
    assert d["dimensions"]["D4"]["declared"] == "T1"
    assert d["dimensions"]["D4"]["top2"][0] == "T2"
    assert any(h["code"] == "add-g-love-blind" for h in d["highlights"])


# ── D5 dual-facet ─────────────────────────────────────────────────────────────

def test_d5_quadrant_all_positive():
    # S1 total=6 (>3) → 高直接; S2 total=6 (>3) → 高分享 → 直爽热情型
    d = _compute_diagnosis(_all_positive())
    d5 = d["dimensions"]["D5"]
    assert d5["s1"] == "高直接"
    assert d5["s2"] == "高分享"
    assert d5["style"] == "直爽热情型"


def test_d5_border_mid():
    """S1=3 (not >3) → 中直接; S2=-3 (not <-3) → 中分享"""
    answers = _all_positive()
    for a in answers:
        if a["question_id"].startswith("D5"):
            a["score_value"] = 0
    for i in range(1, 4):
        for a in answers:
            if a["question_id"] == f"D5-Q{i:02d}":
                a["score_value"] = 1   # S1 total = 3
    for i in range(4, 7):
        for a in answers:
            if a["question_id"] == f"D5-Q{i:02d}":
                a["score_value"] = -1  # S2 total = -3
    d = _compute_diagnosis(answers)
    d5 = d["dimensions"]["D5"]
    assert d5["s1"] == "中直接"
    assert d5["s2"] == "中分享"


# ── Cross-validation Layer 1 ──────────────────────────────────────────────────

def test_cv_d1_behavior_gap_not_triggered():
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D1-Q04":
            a["score_value"] = 2
        elif a["question_id"] == "D1-Q05":
            a["score_value"] = 1  # same direction → no split
    d = _compute_diagnosis(answers)
    assert "add-cv1-behavior-gap" not in {h["code"] for h in d["highlights"]}


def test_cv_d1_behavior_gap_triggered():
    """Q04 and Q05 in opposite directions → behavior-gap fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D1-Q04":
            a["score_value"] = 2
        elif a["question_id"] == "D1-Q05":
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv1-behavior-gap" in {h["code"] for h in d["highlights"]}


def test_cv_d2_pattern_blind_triggered():
    """D2-Q01>=1 and D2-Q05<=-1 → pattern-blind fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D2-Q05":
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv1-pattern-blind" in {h["code"] for h in d["highlights"]}


def test_cv_d2_pattern_blind_not_triggered():
    answers = _all_positive()  # all scores positive
    d = _compute_diagnosis(answers)
    assert "add-cv1-pattern-blind" not in {h["code"] for h in d["highlights"]}


def test_cv_d3_pressure_collapse_not_triggered():
    answers = _all_positive()
    for a in answers:
        if a["question_id"] in ("D3-Q01", "D3-Q05"):
            a["score_value"] = 2  # both positive → high resilience
    d = _compute_diagnosis(answers)
    assert "add-cv1-pressure-collapse" not in {h["code"] for h in d["highlights"]}


def test_cv_d3_pressure_collapse_triggered():
    """D3-Q01>=1 but D3-Q05<0 → pressure-collapse fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D3-Q05":
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv1-pressure-collapse" in {h["code"] for h in d["highlights"]}


# ── Cross-validation Layer 2 ──────────────────────────────────────────────────

def test_cv_d2d3_aggr_passive_triggered():
    """D2-Q01==-2 and D3-Q01==-2 → aggr-passive fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] in ("D2-Q01", "D3-Q01"):
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv2-aggr-passive" in {h["code"] for h in d["highlights"]}


def test_cv_d1d5_anxious_disguise_triggered():
    """D1-Q02==-2 and D5-Q05==-2 → anxious-disguise fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] in ("D1-Q02", "D5-Q05"):
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv2-anxious-disguise" in {h["code"] for h in d["highlights"]}


def test_cv_d2d5_self_dissolve_triggered():
    """D2-Q02<=-1 and >=2 of D5-Q01/02/03 <=-1 → self-dissolve fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D2-Q02":
            a["score_value"] = -2
        elif a["question_id"] in ("D5-Q01", "D5-Q02"):
            a["score_value"] = -2
    d = _compute_diagnosis(answers)
    assert "add-cv2-self-dissolve" in {h["code"] for h in d["highlights"]}


# ── Global markers ────────────────────────────────────────────────────────────

def test_awareness_gap_global_triggered():
    """selected_option=='d' in D1-Q01, D2-Q05, D3-Q03 → self-blame fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] in ("D1-Q01", "D2-Q05", "D3-Q03"):
            a["selected_option"] = "d"
    d = _compute_diagnosis(answers)
    assert "add-g-self-blame" in {h["code"] for h in d["highlights"]}


def test_awareness_gap_global_edge_only_one():
    """Only 1 of 3 is D → self-blame not fired."""
    answers = _all_positive()
    for a in answers:
        if a["question_id"] == "D1-Q01":
            a["selected_option"] = "d"
    d = _compute_diagnosis(answers)
    assert "add-g-self-blame" not in {h["code"] for h in d["highlights"]}


def test_stable_personality_triggered():
    """All positive → >=60% positive score → stable highlight fired."""
    d = _compute_diagnosis(_all_positive())
    assert "add-g-stable" in {h["code"] for h in d["highlights"]}


def test_stable_personality_not_triggered():
    """All negative → 0% positive → stable highlight absent."""
    d = _compute_diagnosis(_all_negative())
    assert "add-g-stable" not in {h["code"] for h in d["highlights"]}


# ── 16-type classification ────────────────────────────────────────────────────

def test_type_code_all_positive():
    d = _compute_diagnosis(_all_positive())
    assert d["type_code"] == "S-CL-H"


def test_type_code_all_negative():
    d = _compute_diagnosis(_all_negative())
    assert d["type_code"] == "A-BL-P"


def test_type_name_axis_fallback_and_tagline_empty():
    """agent_a 单独跑时给出 type_name 轴名兜底（非空），type_tagline 留空待 enrich 注入。"""
    d = _compute_diagnosis(_all_positive())
    assert d["type_name"]                   # 轴名拼接，永远非空
    assert "/" in d["type_name"]            # 轴名格式 "X / Y / Z"
    assert d["type_tagline"] == ""          # tagline 由 /quiz/submit 的 enrich 阶段从 DB 注入


# ── Diagnostic highlights baseline ───────────────────────────────────────────

def test_no_high_severity_highlights_when_all_positive():
    """All positive answers should not trigger any high/moderate problem highlights."""
    d = _compute_diagnosis(_all_positive())
    codes = {h["code"] for h in d["highlights"]}
    assert "add-cv1-pressure-collapse" not in codes
    assert "add-cv1-pattern-blind" not in codes
    assert "add-g-self-blame" not in codes
    assert "add-g-love-blind" not in codes
    assert "add-g-pa-pursuer" not in codes
    assert "add-g-pa-avoider" not in codes


# ── Async wrapper ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_async_returns_diagnosis():
    d = await run(_all_positive())
    assert d["type_code"] == "S-CL-H"
    assert "dimensions" in d
    assert "highlights" in d


@pytest.mark.asyncio
async def test_run_includes_question_set_version():
    d = await run(_all_positive(), question_set_version="V2")
    assert d["question_set_version"] == "V2"


@pytest.mark.asyncio
async def test_run_question_set_version_defaults_to_v2():
    d = await run(_all_positive())
    assert d["question_set_version"] == "V2"


@pytest.mark.asyncio
async def test_run_empty_package_raises():
    with pytest.raises(AgentAError):
        await run([])


# ── Answer order stability ────────────────────────────────────────────────────

def test_diagnosis_is_deterministic():
    """Same inputs → same outputs, no randomness."""
    a1 = _all_positive()
    a2 = copy.deepcopy(a1)
    assert _compute_diagnosis(a1) == _compute_diagnosis(a2)


# ── Small-L full example from the scoring spec ─────────────────────────────────

def test_small_l_example():
    """Match the 小L example from the scoring rules doc."""
    scores = {
        # D1: -1 + -2 + -1 + 2 + -1 + 1 = -2 → moderate_anxious (MA)
        "D1-Q01": -1, "D1-Q02": -2, "D1-Q03": -1, "D1-Q04": 2, "D1-Q05": -1, "D1-Q06": 1,
        # D2: 2 + 1 + 2 + 2 + -1 + 1 = 7 → clear (CL)
        "D2-Q01": 2, "D2-Q02": 1, "D2-Q03": 2, "D2-Q04": 2, "D2-Q05": -1, "D2-Q06": 1,
        # D3: 2 + 2 + 1 + 2 + -1 + -2 = 4 → moderate_healthy (MH), pursue
        "D3-Q01": 2, "D3-Q02": 2, "D3-Q03": 1, "D3-Q04": 2, "D3-Q05": -1, "D3-Q06": -2,
    }
    answers = _all_positive()
    for a in answers:
        qid = a["question_id"]
        if qid in scores:
            a["score_value"] = scores[qid]
        if qid.startswith("D4"):
            a["score_value"] = 0
        if qid == "D3-Q06":
            a["score_meta"] = {"pursue_avoid": "pursue"}
            a["selected_option"] = "c"

    # D4: T1=7/9≈0.78, T2=2/8=0.25, T4=2/9≈0.22 → top2=[T1,T2]
    for a in answers:
        if a["question_id"] == "D4-Q01":
            a["score_value"] = 7
            a["score_meta"] = {"love_language": "T1"}
        elif a["question_id"] == "D4-Q02":
            a["score_value"] = 2
            a["score_meta"] = {"love_language": "T2"}
        elif a["question_id"] == "D4-Q03":
            a["score_value"] = 2
            a["score_meta"] = {"love_language": "T4"}

    d = _compute_diagnosis(answers)

    assert d["dimensions"]["D1"]["interp"] == "moderate_anxious"
    assert d["dimensions"]["D2"]["interp"] == "clear"
    assert d["dimensions"]["D3"]["interp"] == "moderate_healthy"
    assert d["dimensions"]["D3"]["pursue_avoid"] == "pursue"

    norm = d["dimensions"]["D4"]["normalized"]
    assert norm["T1"] == pytest.approx(0.78, abs=0.01)
    assert norm["T2"] == pytest.approx(0.25, abs=0.01)
    assert d["dimensions"]["D4"]["top2"][0] == "T1"

    # D1 raw=-2 < 0 → MA; D2 clear → CL; D3 moderate_healthy → H
    assert d["type_code"] == "MA-CL-H"

    highlights = {h["code"] for h in d["highlights"]}
    # D1-Q04=2 vs D1-Q05=-1 → opposite directions → behavior-gap
    assert "add-cv1-behavior-gap" in highlights
    # D2-Q01=2>=1 and D2-Q05=-1<=-1 → pattern-blind
    assert "add-cv1-pattern-blind" in highlights
    # D3-Q01=2>=1, D3-Q05=-1<0 → pressure-collapse
    assert "add-cv1-pressure-collapse" in highlights
    # pursue role
    assert "add-g-pa-pursuer" in highlights
