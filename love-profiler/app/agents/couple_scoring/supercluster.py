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
        lv = d["levels"]
        return (lv["a"] + lv["b"]) / 2
    return d["gap"]


def supercluster_scores(dims: list[dict]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name, spec in SUPERCLUSTERS.items():
        chosen = [d for d in dims if _selected(d, spec)]
        den = sum(d["effect_size"] for d in chosen)
        out[name] = round(sum(d["effect_size"] * _value(d, spec) for d in chosen) / den, 1) if den else None
    return out
