from app.agents.couple_scoring.triplet import anchor_label, triplet
from app.services.couple_registry import DimensionConfig


def _dim(anchors):
    return DimensionConfig(id="money", cluster="A", layer="interpretation", apply_prediction=True,
        complementary=False, level_only=False, skippable=False, anchors=anchors, items=())


def test_anchor_label_low_high_mid():
    dim = _dim({"low": "存钱", "high": "花钱"})
    assert anchor_label(20, dim) == "存钱"
    assert anchor_label(80, dim) == "花钱"
    assert anchor_label(50, dim) == "介于两者之间"


def test_anchor_label_no_anchors():
    assert anchor_label(20, _dim({})) == ""


def test_triplet_shape():
    t = triplet(18, 72, _dim({"low": "存钱", "high": "花钱"}))
    assert t["gap"] == 54.0
    assert t["direction"]["higher_partner"] == "B"
    assert t["direction"]["label_a"] == "存钱"
    assert t["direction"]["label_b"] == "花钱"
    assert t["levels"] == {"a": 18, "b": 72}
