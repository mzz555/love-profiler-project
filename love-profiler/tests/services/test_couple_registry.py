from app.services import couple_registry as reg


def test_get_dimension_money():
    d = reg.get_dimension("money")
    assert d is not None and d.cluster == "A"
    assert d.name_cn == "金钱观"
    assert d.apply_prediction is True
    assert d.anchors["low"] and d.anchors["high"]
    assert len(d.items) >= 2


def test_level_only_and_skippable_flags():
    assert reg.get_dimension("emotional_stability").level_only is True
    assert reg.get_dimension("religiosity").skippable is True


def test_pairing_role():
    assert reg.get_dimension("attach_anxiety").pairing_role == "anxiety"
    assert reg.get_dimension("attach_avoid").pairing_role == "avoidance"
    assert reg.get_dimension("money").pairing_role is None


def test_get_calibration_missing_falls_back_to_defaults():
    c = reg.get_calibration("money")
    assert c["calibrated_relevant"] is False
    assert c["gap_thresholds"]["small"] == 18
    assert c["effect_size"] == 0.0


def test_unknown_dimension_returns_none():
    assert reg.get_dimension("not_a_dim") is None
