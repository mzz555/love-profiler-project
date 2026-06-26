from app.agents.couple_scoring.salience import gap_level, salience, assign_salience_ranks


def test_gap_level():
    th = {"small": 18, "moderate": 40}
    assert gap_level(5, th) == "none"
    assert gap_level(12, th) == "small"
    assert gap_level(30, th) == "moderate"
    assert gap_level(54, th) == "large"


def test_salience_uncalibrated():
    assert salience(54, {"exists": True, "accuracy_error": 40},
                    {"calibrated_relevant": False, "effect_size": 0.0}) == -1.0


def test_salience_calibrated():
    # g=0.54,b=0.4 → 0.3*(0.6*0.54+0.4*0.4)=0.1452
    assert salience(54, {"exists": True, "accuracy_error": 40},
                    {"calibrated_relevant": True, "effect_size": 0.3}) == 0.1452


def test_assign_ranks():
    dims = [{"salience": 0.1}, {"salience": -1.0}, {"salience": 0.3}]
    assign_salience_ranks(dims)
    assert dims[2]["salience_rank"] == 1
    assert dims[0]["salience_rank"] == 2
    assert dims[1]["salience_rank"] == -1
