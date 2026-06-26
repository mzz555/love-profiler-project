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
