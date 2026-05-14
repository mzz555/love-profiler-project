import pytest
from app.services.answer_package_builder import build_answer_package

# Minimal mock question list mirroring the real schema
MOCK_QUESTIONS = [
    {
        "question_id": "D1-Q01", "dimension": "依恋",
        "signal_code": "S1", "signal_name": "不确定性解读",
        "question_type": "强度型",
        "stem": "题目一",
        "option_a": "选A", "option_b": "选B", "option_c": "选C", "option_d": "选D", "option_e": None,
        "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None,
    },
    {
        "question_id": "D3-Q06", "dimension": "冲突",
        "signal_code": "S5", "signal_name": "追逃模式",
        "question_type": "强度型",
        "stem": "题目D3Q06",
        "option_a": "觉察打破", "option_b": "无固定模式",
        "option_c": "追的角色", "option_d": "逃的角色", "option_e": None,
        "score_a": "+2", "score_b": "+1", "score_c": "-2", "score_d": "-2", "score_e": None,
    },
    {
        "question_id": "D4-Q01", "dimension": "情感",
        "signal_code": "ALL", "signal_name": "五语均测",
        "question_type": "爱的语言型",
        "stem": "题目D4Q01",
        "option_a": "A", "option_b": "B", "option_c": "C", "option_d": "D", "option_e": "E",
        "score_a": "T1+2", "score_b": "T2+2", "score_c": "T3+2", "score_d": "T4+2", "score_e": "T5+2",
    },
]

MOCK_ANSWERS = [
    {"question_id": "D1-Q01", "chosen_option": "a"},
    {"question_id": "D3-Q06", "chosen_option": "c"},
    {"question_id": "D4-Q01", "chosen_option": "b"},
]


def test_package_length_matches_answers():
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    assert len(pkg) == 3


def test_package_item_has_required_fields():
    """Builder 返回精简包，只含 agent_a 直接消费的 4 个字段——
    dimension/signal/question_type 这些由题号前缀和 score_meta 蕴含，无需冗余携带。"""
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    item = pkg[0]
    for field in ("question_id", "selected_option", "score_value", "score_meta"):
        assert field in item, f"missing field: {field}"


def test_regular_question_score():
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    d1 = next(p for p in pkg if p["question_id"] == "D1-Q01")
    assert d1["score_value"] == 2
    assert d1["score_meta"] == {}


def test_d3_q06_pursue_marked():
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    d3 = next(p for p in pkg if p["question_id"] == "D3-Q06")
    assert d3["score_value"] == -2
    assert d3["score_meta"] == {"pursue_avoid": "pursue"}


def test_d3_q06_avoid_marked():
    answers = [{"question_id": "D3-Q06", "chosen_option": "d"}]
    pkg = build_answer_package(answers, MOCK_QUESTIONS)
    d3 = pkg[0]
    assert d3["score_value"] == -2
    assert d3["score_meta"] == {"pursue_avoid": "avoid"}


def test_d3_q06_option_a_no_meta():
    answers = [{"question_id": "D3-Q06", "chosen_option": "a"}]
    pkg = build_answer_package(answers, MOCK_QUESTIONS)
    assert pkg[0]["score_meta"] == {}


def test_love_language_score_parsed():
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    d4 = next(p for p in pkg if p["question_id"] == "D4-Q01")
    assert d4["score_value"] == 2
    assert d4["score_meta"] == {"love_language": "T2"}


def test_unknown_question_id_skipped():
    answers = [{"question_id": "FAKE-Q99", "chosen_option": "a"}]
    pkg = build_answer_package(answers, MOCK_QUESTIONS)
    assert pkg == []


def test_selected_option_stored():
    pkg = build_answer_package(MOCK_ANSWERS, MOCK_QUESTIONS)
    d1 = next(p for p in pkg if p["question_id"] == "D1-Q01")
    assert d1["selected_option"] == "a"
