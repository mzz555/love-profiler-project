from app.agents.couple_scoring.pairings import pairings


def test_demand_withdraw_flag():
    scores = {"A": {"confront": 70, "withdraw": 10}, "B": {"confront": 10, "withdraw": 80}}
    assert "demand_withdraw" in pairings(scores)


def test_anxious_avoidant_reverse_direction():
    scores = {"A": {"attach_anxiety": 10, "attach_avoid": 75},
              "B": {"attach_anxiety": 70, "attach_avoid": 10}}
    assert "anxious_avoidant" in pairings(scores)


def test_no_flag_below_threshold():
    assert pairings({"A": {"confront": 50, "withdraw": 50},
                     "B": {"confront": 50, "withdraw": 50}}) == []
