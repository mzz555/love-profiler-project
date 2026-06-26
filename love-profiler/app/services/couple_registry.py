"""Couple dimension registry — 加载 dimensions.yaml + calibration.json（只读）。

算法参数真相源；无 DB、无 LLM。
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

import yaml

_DATA_DIR = pathlib.Path(__file__).parents[1] / "agents" / "couple_data"


@dataclass(frozen=True)
class DimensionConfig:
    id: str
    cluster: str
    name_cn: str = ""
    layer: str = "interpretation"
    apply_prediction: bool = False
    complementary: bool = False
    level_only: bool = False
    skippable: bool = False
    pairing_role: str | None = None
    anchors: dict = field(default_factory=dict)
    items: tuple = ()


def _load_dimensions() -> dict[str, DimensionConfig]:
    raw = yaml.safe_load((_DATA_DIR / "dimensions.yaml").read_text(encoding="utf-8"))
    out: dict[str, DimensionConfig] = {}
    for d in raw:
        out[d["id"]] = DimensionConfig(
            id=d["id"], cluster=d["cluster"], name_cn=d.get("name_cn", ""),
            layer=d.get("layer", "interpretation"),
            apply_prediction=bool(d.get("apply_prediction", False)),
            complementary=bool(d.get("complementary", False)),
            level_only=bool(d.get("level_only", False)),
            skippable=bool(d.get("skippable", False)),
            pairing_role=d.get("pairing_role"),
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
