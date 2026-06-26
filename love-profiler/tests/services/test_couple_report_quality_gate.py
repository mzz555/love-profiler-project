import pytest

from app.services.couple_report_quality_gate import check_cards, CoupleQualityGateError


def _briefing(comp=False):
    return {"dimensions": [{"dimension_id": "money", "complementary": comp,
            "blindspot": {"narrative_fact": "A 比 B 预想的更倾向「存钱」"}}]}


def _cards(body):
    return {"opening": {"headline": "", "body": ""}, "how_to_read": {"body": ""},
            "blindspot_cards": [{"dimension_id": "money", "title": "t", "body": body, "talk_prompt": ""}],
            "landscape": [], "strengths": {"body": ""},
            "next_steps": {"body": "", "invitations": []}, "closing": {"body": ""}}


def test_banned_word_rejected():
    with pytest.raises(CoupleQualityGateError):
        check_cards(_cards("你们的匹配度很高"), _briefing())


def test_complementary_negative_rejected():
    with pytest.raises(CoupleQualityGateError):
        check_cards(_cards("这是你们关系的缺陷"), _briefing(comp=True))


def test_fact_reference_soft_warning():
    assert any("fact_not_referenced" in w for w in check_cards(_cards("完全无关的内容"), _briefing()))


def test_clean_card_passes():
    assert check_cards(_cards("A 比 B 预想的更倾向存钱，这值得聊聊"), _briefing()) == []
