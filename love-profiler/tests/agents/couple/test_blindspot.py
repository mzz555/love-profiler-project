from app.agents.couple_scoring.blindspot import blindspot, severity_bucket
from app.services.couple_registry import DimensionConfig


def _dim():
    return DimensionConfig(id="money", cluster="A", layer="interpretation", apply_prediction=True,
        complementary=False, level_only=False, skippable=False,
        anchors={"low": "存钱", "high": "花钱"}, items=())


def test_severity_bucket():
    assert severity_bucket(5) == "none"
    assert severity_bucket(12) == "low"
    assert severity_bucket(25) == "moderate"
    assert severity_bucket(40) == "high"


def test_blindspot_high_error_picks_worse_guesser():
    # s_A=18,s_B=72; A 猜 B=35→err 37; B 猜 A=60→err 42 ⇒ who=B, err=42 high
    bs = blindspot(18, 72, 35, 60, _dim())
    assert bs["who_misjudged"] == "B"
    assert bs["accuracy_error"] == 42.0
    assert bs["severity"] == "high" and bs["exists"] is True
    assert "「存钱」" in bs["narrative_fact"]      # 关于 A 的真实方向


def test_blindspot_assumed_close():
    # A 猜 B=20（以为与自己 18 接近），实际 gap 54 ⇒ assumed_close True
    bs = blindspot(18, 72, 20, 18, _dim())
    assert bs["who_misjudged"] == "A"
    assert bs["assumed_close"] is True


def test_blindspot_none_when_accurate():
    bs = blindspot(50, 52, 52, 50, _dim())   # 双方都猜得很准
    assert bs["exists"] is False
    assert bs["narrative_fact"] == ""
