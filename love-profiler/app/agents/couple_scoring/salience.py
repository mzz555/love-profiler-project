"""分档 gap_level + 判决轨道 salience 排序。校准闸门在此。"""
from __future__ import annotations

_NONE_MAX = 8.0


def gap_level(gap: float, thresholds: dict) -> str:
    if gap < _NONE_MAX:
        return "none"
    if gap < thresholds["small"]:
        return "small"
    if gap < thresholds["moderate"]:
        return "moderate"
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
