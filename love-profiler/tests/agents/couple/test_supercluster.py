from app.agents.couple_scoring.supercluster import supercluster_scores


def _d(dim_id, cluster, gap, relevant, eff=0.0, **extra):
    base = {"dimension_id": dim_id, "cluster": cluster, "gap": gap,
            "calibrated_relevant": relevant, "effect_size": eff,
            "apply_prediction": False, "level_only": False,
            "levels": {"a": 0, "b": 0}, "blindspot": None}
    base.update(extra)
    return base


def test_all_none_when_uncalibrated():
    scores = supercluster_scores([_d("money", "A", 54, False), _d("confront", "B", 30, False)])
    assert scores == {"life_expectations": None, "conflict_process": None,
                      "values_attachment": None, "perceptual_blindspot": None}


def test_life_expectations_weighted():
    dims = [_d("money", "A", 60, True, eff=0.3), _d("chores", "A", 40, True, eff=0.1)]
    # (0.3*60+0.1*40)/0.4 = 55.0
    assert supercluster_scores(dims)["life_expectations"] == 55.0


def test_perceptual_blindspot_uses_accuracy_error():
    dims = [_d("money", "A", 54, True, eff=0.3, apply_prediction=True,
               blindspot={"accuracy_error": 40, "exists": True})]
    scores = supercluster_scores(dims)
    assert scores["life_expectations"] == 54.0      # 用 gap
    assert scores["perceptual_blindspot"] == 40.0   # 用 accuracy_error
