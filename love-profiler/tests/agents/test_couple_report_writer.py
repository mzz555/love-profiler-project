import asyncio
import json

import pytest

from app.agents import couple_report_writer as crw


def _briefing():
    return {"session_id": "s",
        "overview": {"top_blindspots": ["money"], "high_friction_pairings": [],
                     "complementary_strengths": [], "supercluster_scores": {"life_expectations": None}},
        "dimensions": [{"dimension_id": "money", "cluster": "A", "complementary": False,
            "gap_level": "large", "direction": {"higher_partner": "B", "label_a": "存钱", "label_b": "花钱"},
            "blindspot": {"narrative_fact": "A 比 B 预想的更倾向「存钱」", "exists": True, "who_misjudged": "A"}}]}


def test_run_generates_7_sections(monkeypatch):
    async def fake_chat(**kw):
        return json.dumps({"title": "金钱观盲区",
            "body": "A 比 B 预想的更倾向存钱，这值得聊聊", "talk_prompt": "多出一笔钱你会怎么花？"})
    monkeypatch.setattr(crw, "chat_completion", fake_chat)
    report = asyncio.run(crw.run(_briefing(), session_id="s"))
    assert report["opening"]["headline"] and report["opening"]["body"]
    assert report["how_to_read"]["body"]
    assert report["blindspot_cards"][0]["dimension_id"] == "money"
    assert isinstance(report["landscape"], list)
    assert isinstance(report["next_steps"]["invitations"], list)
    assert report["closing"]["body"] and report["quality_warnings"] == []


def test_run_no_blindspots_raises(monkeypatch):
    monkeypatch.setattr(crw, "chat_completion", lambda **kw: _aret("{}"))
    b = _briefing()
    b["overview"]["top_blindspots"] = []
    with pytest.raises(crw.CoupleReportWriterError):
        asyncio.run(crw.run(b, session_id="s"))


async def _aret(v):
    return v
