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
