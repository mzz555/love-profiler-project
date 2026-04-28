import pytest
from app.services.quiz_scorer import compute_scores


MOCK_QUESTIONS = [
    # D1 依恋
    {"question_id": "D1-Q01", "dimension": "依恋", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D1-Q02", "dimension": "依恋", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D1-Q03", "dimension": "依恋", "signal_code": "S3",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D1-Q04", "dimension": "依恋", "signal_code": "S4",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D1-Q05", "dimension": "依恋", "signal_code": "S4",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D1-Q06", "dimension": "依恋", "signal_code": "S5",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    # D2 边界
    {"question_id": "D2-Q01", "dimension": "边界", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D2-Q02", "dimension": "边界", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D2-Q03", "dimension": "边界", "signal_code": "S3",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D2-Q04", "dimension": "边界", "signal_code": "S4",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D2-Q05", "dimension": "边界", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D2-Q06", "dimension": "边界", "signal_code": "S5",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    # D3 冲突
    {"question_id": "D3-Q01", "dimension": "冲突", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D3-Q02", "dimension": "冲突", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D3-Q03", "dimension": "冲突", "signal_code": "S3",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D3-Q04", "dimension": "冲突", "signal_code": "S4",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D3-Q05", "dimension": "冲突", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D3-Q06", "dimension": "冲突", "signal_code": "S5",
     "score_a": "+2", "score_b": "+1", "score_c": "-2", "score_d": "-2", "score_e": None},
    # D4 情感（爱的语言）
    {"question_id": "D4-Q01", "dimension": "情感", "signal_code": "T1-T5",
     "score_a": "T1+2", "score_b": "T2+2", "score_c": "T3+2", "score_d": "T4+2", "score_e": "T5+2"},
    {"question_id": "D4-Q02", "dimension": "情感", "signal_code": "T1/T4",
     "score_a": "T1+2", "score_b": "T4+2", "score_c": "T5+1", "score_d": "T2+1", "score_e": None},
    {"question_id": "D4-Q03", "dimension": "情感", "signal_code": "T2/T5",
     "score_a": "T2+2", "score_b": "T5+2", "score_c": "T1+1", "score_d": "T4+1", "score_e": None},
    {"question_id": "D4-Q04", "dimension": "情感", "signal_code": "T3/T4",
     "score_a": "T3+2", "score_b": "T4+2", "score_c": "T1+1", "score_d": "T2+1", "score_e": None},
    {"question_id": "D4-Q05", "dimension": "情感", "signal_code": "T1/T2",
     "score_a": "T1+2", "score_b": "T2+2", "score_c": "T5+1", "score_d": "T4+1", "score_e": None},
    {"question_id": "D4-Q06", "dimension": "情感", "signal_code": "T3/T5",
     "score_a": "T3+2", "score_b": "T5+2", "score_c": "T1+1", "score_d": "T4+1", "score_e": None},
    # D5 风格
    {"question_id": "D5-Q01", "dimension": "风格", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D5-Q02", "dimension": "风格", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D5-Q03", "dimension": "风格", "signal_code": "S1",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D5-Q04", "dimension": "风格", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D5-Q05", "dimension": "风格", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
    {"question_id": "D5-Q06", "dimension": "风格", "signal_code": "S2",
     "score_a": "+2", "score_b": "+1", "score_c": "-1", "score_d": "-2", "score_e": None},
]


def _all_a_answers():
    return [{"question_id": q["question_id"], "chosen_option": "a"} for q in MOCK_QUESTIONS]


def test_all_a_gives_max_attachment():
    scores = compute_scores(_all_a_answers(), MOCK_QUESTIONS)
    assert scores["attachment"] == 12


def test_all_d_gives_min_attachment():
    answers = [{"question_id": q["question_id"], "chosen_option": "d"} for q in MOCK_QUESTIONS]
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["attachment"] == -12


def test_boundary_score():
    answers = _all_a_answers()
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["boundary"] == 12


def test_conflict_score():
    answers = _all_a_answers()
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["conflict"] == 12


def test_love_language_primary_is_t1_when_all_a():
    answers = _all_a_answers()
    scores = compute_scores(answers, MOCK_QUESTIONS)
    ll = scores["love_language"]
    assert ll["primary"] == "T1"
    assert ll["T1"] > 0


def test_style_directness():
    answers = _all_a_answers()
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["style"]["directness"] == 6  # 3 questions * +2


def test_style_sharing():
    answers = _all_a_answers()
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["style"]["sharing"] == 6


def test_unknown_question_id_ignored():
    answers = [{"question_id": "FAKE-Q99", "chosen_option": "a"}]
    scores = compute_scores(answers, MOCK_QUESTIONS)
    assert scores["attachment"] == 0


def test_returns_all_required_keys():
    scores = compute_scores(_all_a_answers(), MOCK_QUESTIONS)
    assert set(scores.keys()) == {"attachment", "boundary", "conflict", "love_language", "style"}
    assert set(scores["love_language"].keys()) == {"T1", "T2", "T3", "T4", "T5", "primary"}
    assert set(scores["style"].keys()) == {"directness", "sharing"}
