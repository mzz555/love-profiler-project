import pytest
from pydantic import ValidationError

from app.schemas.couple_briefing import CoupleBriefing, CoupleDimensionResult


def _dim(**over):
    base = dict(dimension_id="money", cluster="A", layer="topic_only", calibrated_relevant=False,
                complementary=False, level_only=False, gap=54.0, gap_level="large",
                direction={"higher_partner": "B", "label_a": "存钱", "label_b": "花钱"},
                levels={"a": 18, "b": 72}, blindspot=None, salience_rank=-1)
    base.update(over)
    return base


def _ov(**over):
    base = dict(top_blindspots=[], supercluster_scores={}, high_friction_pairings=[],
                complementary_strengths=[])
    base.update(over)
    return base


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
