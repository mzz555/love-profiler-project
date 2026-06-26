import asyncio

import pytest

from app.agents.couple_scoring_engine import run, CoupleScoringError
from app.services.couple_answer_package_builder import build_couple_answer_package


def test_run_produces_blindspot_briefing():
    a = {"self": [{"question_id": "A1-1", "value": 18}, {"question_id": "A1-2", "value": 20}],
         "predicted": [{"question_id": "A1-1", "value": 22}, {"question_id": "A1-2", "value": 20}]}
    b = {"self": [{"question_id": "A1-1", "value": 80}, {"question_id": "A1-2", "value": 75}],
         "predicted": [{"question_id": "A1-1", "value": 78}, {"question_id": "A1-2", "value": 75}]}
    briefing = asyncio.run(run(build_couple_answer_package(a, b), session_id="sess1"))
    assert briefing["session_id"] == "sess1"
    money = next(d for d in briefing["dimensions"] if d["dimension_id"] == "money")
    assert money["layer"] == "topic_only" and money["calibrated_relevant"] is False
    assert money["salience_rank"] == -1                       # 判决轨道降级
    assert money["blindspot"]["exists"] is True               # 盲区轨道仍输出
    assert "money" in briefing["overview"]["top_blindspots"]
    assert briefing["overview"]["supercluster_scores"]["life_expectations"] is None


def test_run_empty_raises():
    with pytest.raises(CoupleScoringError):
        asyncio.run(run({}))
