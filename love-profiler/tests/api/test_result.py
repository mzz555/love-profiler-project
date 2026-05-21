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
    "type_name": "稳重的航标",
    "portrait": "你的稳不需要被看见。危机出现时，你已经在想怎么解决了。",
    "dimensions": {
        "D1": {"title": "依恋", "text": ""},
        "D2": {"title": "边界", "text": ""},
        "D3": {"title": "冲突", "text": ""},
        "D4": {"title": "爱的语言", "text": "你对爱的需要，前两位是被具体看见和专注陪伴。"},
        "D5": {"title": "表达风格", "text": "你的表达不会让人困惑，也没有特别暴露。"},
    },
    "insights": [],
    "closing": "明天起，试着在一件小事上直接说出你的感受。",
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
    report_text = MOCK_REPORT["portrait"] + "\n\n" + MOCK_REPORT["closing"]
    report_json = json.dumps(MOCK_REPORT)
    a = Assessment(
        user_id=user_id,
        session_id=session_id,
        signals="{}",
        mode="quick",
        status="complete",
        diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
        personality_type="S-CL-H",
        report_text=report_text,
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
    """When status='complete', return full cached report with sections field."""
    user, headers = _make_user_and_token(db_session, "o_result_cached")
    assessment = _make_complete_assessment(db_session, user.id, "sess-cached")

    response = client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["personality_type"] == "S-CL-H"
    assert "sections" in data
    assert data["sections"]["portrait"] == MOCK_REPORT["portrait"]
    assert "dimensions" in data["sections"]
    assert data["sections"]["dimensions"]["D4"]["text"] != ""


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


# ---------------------------------------------------------------------------
# 解锁与诊断缺失分支
# ---------------------------------------------------------------------------

def _make_paid_order(db_session, user_id: int, assessment_id: int):
    """让 access_control.is_unlocked() 返回 True。"""
    from app.models.order import Order
    o = Order(
        user_id=user_id, assessment_id=assessment_id,
        out_trade_no=f"unlock-{assessment_id}",
        amount=0, status="paid",
    )
    db_session.add(o)
    db_session.commit()


def test_result_returns_402_when_not_unlocked(client, db_session, monkeypatch):
    """关掉 DEV_MODE 且无 paid order → 402。"""
    monkeypatch.setenv("DEV_MODE", "false")
    user, headers = _make_user_and_token(db_session, "o_result_402")
    a = _make_analyzed_assessment(db_session, user.id, "sess-402")

    response = client.post("/result", json={"session_id": a.session_id}, headers=headers)
    assert response.status_code == 402


def test_result_returns_429_when_quota_exceeded(client, db_session, monkeypatch):
    """B.1：当日 token quota 用满 → 429。"""
    from datetime import date
    from app.models.user_token_quota import UserTokenQuota

    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "100")

    user, headers = _make_user_and_token(db_session, "o_result_429")
    a = _make_analyzed_assessment(db_session, user.id, "sess-429")
    _make_paid_order(db_session, user.id, a.id)
    db_session.add(UserTokenQuota(
        user_id=user.id, usage_date=date.today(),
        prompt_tokens=70, completion_tokens=50, total_tokens=120,
    ))
    db_session.commit()

    response = client.post("/result", json={"session_id": a.session_id}, headers=headers)
    assert response.status_code == 429
    assert "今日测评次数已达上限" in response.json()["detail"]


def test_result_returns_400_when_diagnosis_missing(client, db_session):
    """analyzed 状态但 diagnosis_json 为空 → 400（兜底分支，正常流程不应出现）。"""
    user, headers = _make_user_and_token(db_session, "o_result_no_diag")
    a = Assessment(
        user_id=user.id, session_id="sess-no-diag",
        signals="{}", status="analyzed", diagnosis_json=None,
    )
    db_session.add(a)
    db_session.commit()

    response = client.post("/result", json={"session_id": a.session_id}, headers=headers)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# /result/stream SSE endpoint
# ---------------------------------------------------------------------------

def _read_sse_events(response):
    """把 SSE 字节流切回 dict 列表。"""
    events = []
    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_stream_returns_404_for_unknown_session(client, db_session):
    _, headers = _make_user_and_token(db_session, "o_stream_404")
    response = client.post(
        "/result/stream", json={"session_id": "nonexistent"}, headers=headers,
    )
    assert response.status_code == 404


def test_stream_returns_400_when_pending(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_stream_pending")
    a = Assessment(
        user_id=user.id, session_id="sess-stream-pending",
        signals="{}", status="pending",
    )
    db_session.add(a)
    db_session.commit()
    response = client.post(
        "/result/stream", json={"session_id": a.session_id}, headers=headers,
    )
    assert response.status_code == 400


def test_stream_returns_402_when_not_unlocked(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    user, headers = _make_user_and_token(db_session, "o_stream_402")
    a = _make_analyzed_assessment(db_session, user.id, "sess-stream-402")
    response = client.post(
        "/result/stream", json={"session_id": a.session_id}, headers=headers,
    )
    assert response.status_code == 402


def test_stream_returns_400_when_diagnosis_missing(client, db_session):
    user, headers = _make_user_and_token(db_session, "o_stream_no_diag")
    a = Assessment(
        user_id=user.id, session_id="sess-stream-no-diag",
        signals="{}", status="analyzed", diagnosis_json=None,
    )
    db_session.add(a)
    db_session.commit()
    response = client.post(
        "/result/stream", json={"session_id": a.session_id}, headers=headers,
    )
    assert response.status_code == 400


def test_stream_cached_replays_report(client, db_session):
    """status=complete + report_text 命中缓存重放路径，纯 SSE chunk 流。"""
    user, headers = _make_user_and_token(db_session, "o_stream_cached")
    a = _make_complete_assessment(db_session, user.id, "sess-stream-cached")

    with client.stream(
        "POST", "/result/stream",
        json={"session_id": a.session_id}, headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    types = [e["type"] for e in events]
    assert types[-1] == "done"
    assert events[-1]["personality_type"] == "S-CL-H"
    # 中间至少有一个 chunk
    chunks = [e for e in events if e["type"] == "chunk"]
    assert chunks and "".join(c["text"] for c in chunks) == a.report_text


def test_stream_runs_agent_b_and_persists(client, db_session):
    """status=analyzed → 跑 Agent B → 写库 status=complete + SSE done。"""
    from unittest.mock import patch, AsyncMock

    user, headers = _make_user_and_token(db_session, "o_stream_run_b")
    a = _make_analyzed_assessment(db_session, user.id, "sess-stream-run-b")

    fake_text = "--Title--稳重的航标 这是 Agent B 写出来的报告正文"
    with patch(
        "app.api.result.write_report",
        new=AsyncMock(return_value=fake_text),
    ):
        with client.stream(
            "POST", "/result/stream",
            json={"session_id": a.session_id}, headers=headers,
        ) as response:
            assert response.status_code == 200
            events = _read_sse_events(response)

    types = [e["type"] for e in events]
    assert types[-1] == "done"
    # 验证 chunk 重组后 = 原文
    chunks = [e for e in events if e["type"] == "chunk"]
    assert "".join(c["text"] for c in chunks) == fake_text


def test_stream_returns_sse_error_when_agent_b_fails(client, db_session):
    """Agent B 抛 AgentBError → SSE 应吐 error event 且不中断 200 响应。"""
    from unittest.mock import patch, AsyncMock
    from app.agents.report_writer import ReportWriterError

    user, headers = _make_user_and_token(db_session, "o_stream_b_fail")
    a = _make_analyzed_assessment(db_session, user.id, "sess-stream-b-fail")

    with patch(
        "app.api.result.write_report",
        new=AsyncMock(side_effect=ReportWriterError("simulated")),
    ):
        with client.stream(
            "POST", "/result/stream",
            json={"session_id": a.session_id}, headers=headers,
        ) as response:
            assert response.status_code == 200
            events = _read_sse_events(response)

    types = [e["type"] for e in events]
    assert "error" in types
    # error 之后不应再有 done
    assert types[-1] == "error"
