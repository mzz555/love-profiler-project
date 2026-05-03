"""
Tests for POST /result — personality report generation endpoint.

Architecture note: /result now returns {status:"generating"} immediately and runs Agent B
as an asyncio background task. Tests verify the synchronous API behavior only; the background
task itself uses SessionLocal (bound to the global engine) and cannot reliably complete within
the per-test StaticPool engine context.
"""

import json

import pytest

from app.models.assessment import Assessment
from app.models.user import User

DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

MOCK_DIAGNOSIS = {
    "dimension_scores": {
        "attachment": {"raw_total": 8, "interpretation": "secure"},
        "boundary": {"raw_total": 6, "interpretation": "clear"},
        "conflict": {"raw_total": 4, "interpretation": "moderate_healthy", "pursue_avoid_subtype": None},
        "emotional_needs": {
            "raw_scores": {"T1": 6, "T2": 4, "T3": 2, "T4": 3, "T5": 4},
            "normalized_scores": {"T1": 0.67, "T2": 0.5, "T3": 0.33, "T4": 0.33, "T5": 0.5},
            "top2": ["T1", "T2"],
            "primary_choice": "T1",
            "alignment_with_primary": True,
        },
        "expression_style": {
            "S1_directness_total": 4, "S2_sharing_total": 3,
            "quadrant": "中直接×中分享", "interpretation": "直爽热情型偏中",
        },
    },
    "cross_validation": {
        "CV_D1_S4_consistency": "high",
        "CV_D2_S1_awareness_gap_local": False,
        "CV_D3_S1_pressure_resilience": "high",
        "CV_Cross_D2D3_S1_pattern": "normal",
        "CV_Cross_D1D5_S2_pattern": "normal",
        "CV_Cross_D2D5_S1_self_dissolution_risk": "low",
    },
    "global_markers": {
        "awareness_gap_global": False,
        "pursue_avoid_role": "stable",
        "stable_personality": True,
        "love_language_self_awareness": "aligned",
    },
    "personality_typing": {
        "primary_attachment_type": "secure",
        "boundary_clarity": "clear",
        "conflict_resilience": "moderate_healthy",
        "type_code": "S-CL-H",
        "type_axis": "安全型依恋 / 清晰边界 / 中度健康冲突",
        "type_name": "稳定温柔的航标",
        "type_tagline": "你不需要完美，就值得被爱",
    },
    "diagnostic_highlights": [],
}

MOCK_REPORT = {
    "report_text": "你是一个安全型依恋风格的人，在感情中表现出稳定的信任感。",
}


def _make_user_and_token(db_session, openid="o_result_test"):
    from app.middleware.auth import create_access_token
    user = User(openid=openid)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


def _make_analyzed_assessment(db_session, user_id: int, session_id: str = "sess-result-test") -> Assessment:
    a = Assessment(
        user_id=user_id,
        session_id=session_id,
        signals="{}",
        mode="quick",
        status="analyzed",
        diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _make_complete_assessment(db_session, user_id: int, session_id: str = "sess-complete") -> Assessment:
    """Pre-built complete assessment for testing the cache path."""
    report_json = json.dumps({"report_text": MOCK_REPORT["report_text"]})
    a = Assessment(
        user_id=user_id,
        session_id=session_id,
        signals="{}",
        mode="quick",
        status="complete",
        diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
        personality_type="S-CL-H",
        report_text=MOCK_REPORT["report_text"],
        report_json=report_json,
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# First call — analyzed → generating
# ---------------------------------------------------------------------------


def test_result_returns_generating_on_first_call(client, db_session):
    """First call with an analyzed assessment returns {status:'generating'} immediately."""
    user, headers = _make_user_and_token(db_session)
    assessment = _make_analyzed_assessment(db_session, user.id)

    response = client.post(
        "/result",
        json={"session_id": assessment.session_id},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "generating"


def test_result_status_transitions_to_generating(client, db_session):
    """After the first call, the assessment status in DB should be 'generating'."""
    user, headers = _make_user_and_token(db_session, "o_result_transition")
    assessment = _make_analyzed_assessment(db_session, user.id, "sess-transition")

    client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

    db_session.expire_all()
    updated = db_session.query(Assessment).filter(Assessment.session_id == "sess-transition").first()
    assert updated.status == "generating"


# ---------------------------------------------------------------------------
# Polling while generating
# ---------------------------------------------------------------------------


def test_result_returns_generating_when_already_generating(client, db_session):
    """If status is already 'generating', return {status:'generating'} without spawning another task."""
    user, headers = _make_user_and_token(db_session, "o_result_already_gen")
    a = Assessment(
        user_id=user.id,
        session_id="sess-already-gen",
        signals="{}",
        status="generating",
        diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
    )
    db_session.add(a)
    db_session.commit()

    response = client.post("/result", json={"session_id": a.session_id}, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "generating"


# ---------------------------------------------------------------------------
# Cached complete report
# ---------------------------------------------------------------------------


def test_result_returns_complete_from_cache(client, db_session):
    """When status='complete', return full cached report without calling LLM."""
    user, headers = _make_user_and_token(db_session, "o_result_cached")
    assessment = _make_complete_assessment(db_session, user.id, "sess-cached")

    response = client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["personality_type"] == "S-CL-H"
    assert data["report_text"] == MOCK_REPORT["report_text"]
    assert "report_json" in data


def test_result_cached_report_does_not_call_llm(client, db_session):
    """Returning a cached complete report must not make any LLM call."""
    import respx, httpx
    user, headers = _make_user_and_token(db_session, "o_result_no_llm")
    assessment = _make_complete_assessment(db_session, user.id, "sess-no-llm")

    with respx.mock:
        respx.post(DOUBAO_URL).mock(return_value=httpx.Response(500))
        response = client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

    # Must succeed (cached) even though LLM would fail
    assert response.status_code == 200
    assert response.json()["status"] == "complete"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_result_returns_404_for_unknown_session(client, db_session):
    _, headers = _make_user_and_token(db_session, "o_result_404")
    response = client.post("/result", json={"session_id": "nonexistent"}, headers=headers)
    assert response.status_code == 404


def test_result_returns_400_when_assessment_pending(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_result_pending")
    a = Assessment(
        user_id=user.id,
        session_id="sess-pending",
        signals="{}",
        status="pending",
    )
    db_session.add(a)
    db_session.commit()
    response = client.post("/result", json={"session_id": a.session_id}, headers=headers)
    assert response.status_code == 400


def test_result_returns_generating_not_502_on_agent_b_start(client, db_session):
    """Launching Agent B no longer blocks the request — always returns 200 generating."""
    user, headers = _make_user_and_token(db_session, "o_result_no502")
    assessment = _make_analyzed_assessment(db_session, user.id, "sess-no502")

    # No LLM mock needed — Agent B runs in background, first call returns immediately
    response = client.post("/result", json={"session_id": assessment.session_id}, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "generating"


def test_result_requires_auth(client):
    response = client.post("/result", json={"session_id": "any"})
    assert response.status_code in (401, 403)
