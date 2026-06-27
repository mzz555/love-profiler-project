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


def test_anchor_referenced_via_nickname_no_warning():
    # 真实场景：body 用昵称/不同引号忠实转述了语义锚点「存钱」，但不含字母模板 "A 比 B"。
    # 旧实现只查 fact 开头模板会误报；新实现应认出锚点已被转述 → 无警告。
    body = "对方比你预想的更倾向‘存钱’，这点很值得一起聊聊"
    assert check_cards(_cards(body), _briefing()) == []


def test_anchor_missing_still_warns():
    # body 完全没提到锚点「存钱」→ 仍应告警。
    assert any("fact_not_referenced" in w
               for w in check_cards(_cards("我们随便聊聊天气吧"), _briefing()))


def test_fact_without_anchor_falls_back():
    # 无「」锚点的泛化 fact：退回宽松的开头检查。
    brief = {"dimensions": [{"dimension_id": "money", "complementary": False,
             "blindspot": {"narrative_fact": "B 的真实态度与 A 的预想存在明显落差"}}]}
    assert check_cards(_cards("B 的真实态度与你预想的有明显落差"), brief) == []
    assert any("fact_not_referenced" in w
               for w in check_cards(_cards("我们随便聊聊天气吧"), brief))
