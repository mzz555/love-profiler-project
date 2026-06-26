"""Cluster F 盲区计算 + narrative_fact 生成（引擎产出中性事实，不交给 LLM）。"""
from __future__ import annotations

from app.agents.couple_scoring.triplet import anchor_label
from app.services.couple_registry import DimensionConfig

THRESH_BLINDSPOT = {"low": 15.0, "moderate": 35.0}
_NONE_MAX = 8.0


def severity_bucket(err: float) -> str:
    if err < _NONE_MAX:
        return "none"
    if err < THRESH_BLINDSPOT["low"]:
        return "low"
    if err < THRESH_BLINDSPOT["moderate"]:
        return "moderate"
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
