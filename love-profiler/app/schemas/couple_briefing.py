"""Couple briefing 契约层 schema（引擎↔Agent 接口）+ 产出前自检。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

_NEGATIVE_WORDS = ("缺陷", "问题", "不足", "糟", "失败", "病态")


class CoupleBlindspot(BaseModel):
    model_config = ConfigDict(extra="allow")
    exists: bool
    severity: str
    who_misjudged: str
    assumed_close: bool
    accuracy_error: float
    narrative_fact: str = ""


class CoupleDimensionResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    dimension_id: str
    cluster: str
    layer: str
    calibrated_relevant: bool
    complementary: bool
    level_only: bool
    gap: float
    gap_level: str
    direction: dict
    levels: dict
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
    top_blindspots: list[str]
    supercluster_scores: dict[str, float | None]
    high_friction_pairings: list[str]
    complementary_strengths: list[str]


class CoupleBriefing(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    overview: CoupleOverview
    dimensions: list[CoupleDimensionResult]
    question_set_version: str = ""

    @model_validator(mode="after")
    def _check_salience(self):
        ranks = sorted(d.salience_rank for d in self.dimensions if d.calibrated_relevant)
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"salience_rank 必须连续唯一从 1：{ranks}")
        return self
