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
