import json

import httpx
import pytest
import respx

MOCK_QUESTIONS = [
    {
        "question_id": f"D1-Q{i:02d}", "dimension": "依恋", "signal_code": "S1",
        "stem": f"题干{i}", "sort_order": i,
        "option_a": "选项A", "score_a": "+2",
        "option_b": "选项B", "score_b": "+1",
        "option_c": "选项C", "score_c": "-1",
        "option_d": "选项D", "score_d": "-2",
        "option_e": None, "score_e": None,
    }
    for i in range(1, 31)
]

SUPABASE_URL = "https://mkoonxulzilpucxeaoeu.supabase.co"


def test_quiz_start_returns_questions(client, auth_headers):
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
            return_value=httpx.Response(200, json=MOCK_QUESTIONS)
        )
        resp = client.post("/quiz/start", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "assessment_id" in data
    assert len(data["questions"]) == 30


def test_quiz_submit_computes_scores(client, auth_headers, db_session):
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
            return_value=httpx.Response(200, json=MOCK_QUESTIONS)
        )
        start = client.post("/quiz/start", headers=auth_headers)
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    answers = [
        {"question_id": f"D1-Q{i:02d}", "chosen_option": "a"}
        for i in range(1, 31)
    ]
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
            return_value=httpx.Response(200, json=MOCK_QUESTIONS)
        )
        resp = client.post(
            "/quiz/submit",
            json={"session_id": session_id, "answers": answers},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"

    from app.models.assessment import Assessment
    db_session.expire_all()
    assessment = db_session.query(Assessment).filter(
        Assessment.session_id == session_id
    ).first()
    assert assessment is not None
    assert assessment.status == "complete"
    assert assessment.mode == "quiz"
    scores = json.loads(assessment.dimension_scores)
    assert "attachment" in scores


def test_quiz_submit_wrong_session_returns_404(client, auth_headers):
    with respx.mock:
        respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
            return_value=httpx.Response(200, json=MOCK_QUESTIONS)
        )
        resp = client.post(
            "/quiz/submit",
            json={"session_id": "nonexistent-session", "answers": []},
            headers=auth_headers,
        )
    assert resp.status_code == 404
