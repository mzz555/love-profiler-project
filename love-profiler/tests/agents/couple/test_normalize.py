from app.agents.couple_scoring.normalize import normalize_item, aggregate_side
from app.services.couple_registry import DimensionConfig


def _dim(items):
    return DimensionConfig(id="d", cluster="A", layer="interpretation", apply_prediction=False,
        complementary=False, level_only=False, skippable=False, anchors={}, items=tuple(items))


def test_normalize_slider_passthrough():
    assert normalize_item(18, "slider", False) == 18.0


def test_normalize_likert7():
    assert normalize_item(7, "likert7", False) == 100.0
    assert normalize_item(1, "likert7", False) == 0.0
    assert normalize_item(4, "likert7", False) == 50.0


def test_normalize_reverse():
    assert normalize_item(7, "likert7", True) == 0.0
    assert normalize_item(18, "slider", True) == 82.0


def test_aggregate_mean():
    dim = _dim([{"id": "A1-1", "type": "slider", "reverse": False},
                {"id": "A1-3", "type": "likert7", "reverse": True}])
    # A1-1 slider 30→30；A1-3 likert7=7 reverse→0；mean=15
    assert aggregate_side(dim, {"A1-1": 30, "A1-3": 7}) == 15.0


def test_aggregate_empty_returns_none():
    dim = _dim([{"id": "Z1", "type": "slider", "reverse": False}])
    assert aggregate_side(dim, {}) is None
