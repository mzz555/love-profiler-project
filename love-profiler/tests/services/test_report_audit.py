"""LLM-as-judge 报告审计单元测试（Phase D.2）。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.assessment import Assessment
from app.models.report_quality_audit import ReportQualityAudit
from app.models.user import User
from app.services import report_audit
from app.services.report_audit import (
    JUDGE_PROMPT_VERSION,
    _clamp_score,
    _parse_judge_output,
    _parse_judge_prompt_version,
    _truncate,
    audit_assessment,
    build_judge_user_message,
    is_enabled,
    schedule_audit,
)


# ---------------------------------------------------------------------------
# Helpers / pure functions
# ---------------------------------------------------------------------------

def test_judge_prompt_version_parses_header():
    raw = "<!-- judge-prompt-version: 2.1 -->\n## 角色\n…"
    assert _parse_judge_prompt_version(raw) == "2.1"


def test_judge_prompt_version_defaults_when_missing():
    assert _parse_judge_prompt_version("无版本注解") == "0"


def test_current_judge_prompt_version_is_1():
    """守门：当前 docs/judge-system-prompt.md 版本应为 1.0。"""
    assert JUDGE_PROMPT_VERSION == "1.0"


@pytest.mark.parametrize("v,expected", [
    (0, 1), (1, 1), (5, 5), (10, 10), (11, 10), (-3, 1),
    ("7", 7),
])
def test_clamp_score_normalises(v, expected):
    assert _clamp_score(v) == expected


def test_clamp_score_rejects_non_int():
    with pytest.raises(ValueError):
        _clamp_score("not a number")


def test_truncate_appends_ellipsis_when_over_limit():
    assert _truncate("abcdef", 4) == "abcd…"


def test_truncate_keeps_short_string():
    assert _truncate("abcd", 4) == "abcd"


def test_build_judge_user_message_includes_both_sections():
    diag = {"type_code": "S-CL-H", "type_name": "稳"}
    msg = build_judge_user_message(diag, "--Title--内容")
    assert "# 诊断数据" in msg
    assert "# 报告全文" in msg
    assert "S-CL-H" in msg
    assert "--Title--内容" in msg


# ---------------------------------------------------------------------------
# _parse_judge_output
# ---------------------------------------------------------------------------

def test_parse_judge_output_plain_json():
    raw = json.dumps({
        "coherence_score": 9, "readability_score": 8,
        "factual_score": 10, "overall_score": 9,
        "summary": "整体不错",
    })
    out = _parse_judge_output(raw)
    assert out["coherence_score"] == 9
    assert out["overall_score"] == 9
    assert out["summary"] == "整体不错"


def test_parse_judge_output_strips_markdown_fence():
    raw = (
        "```json\n"
        '{"coherence_score":8,"readability_score":7,'
        '"factual_score":9,"overall_score":8,"summary":"ok"}\n'
        "```"
    )
    out = _parse_judge_output(raw)
    assert out["coherence_score"] == 8


def test_parse_judge_output_extracts_json_when_wrapped_in_prose():
    """LLM 偶尔会在 JSON 前后写解释文字。"""
    raw = (
        "好的，我的评分如下：\n"
        '{"coherence_score":6,"readability_score":7,'
        '"factual_score":5,"overall_score":6,"summary":"凑合"}\n'
        "希望能帮到你。"
    )
    out = _parse_judge_output(raw)
    assert out["coherence_score"] == 6


def test_parse_judge_output_clamps_out_of_range_scores():
    raw = json.dumps({
        "coherence_score": 15, "readability_score": 0,
        "factual_score": -2, "overall_score": 99,
        "summary": "超界值测试",
    })
    out = _parse_judge_output(raw)
    assert out["coherence_score"] == 10
    assert out["readability_score"] == 1
    assert out["factual_score"] == 1
    assert out["overall_score"] == 10


def test_parse_judge_output_truncates_long_summary():
    long_summary = "x" * 500
    raw = json.dumps({
        "coherence_score": 5, "readability_score": 5,
        "factual_score": 5, "overall_score": 5,
        "summary": long_summary,
    })
    out = _parse_judge_output(raw)
    assert len(out["summary"]) <= 201  # 200 + …


def test_parse_judge_output_raises_when_not_json():
    with pytest.raises(ValueError):
        _parse_judge_output("纯粹的废话，没有任何 JSON")


def test_parse_judge_output_raises_when_score_missing():
    raw = json.dumps({"coherence_score": 9, "summary": "缺字段"})
    with pytest.raises(ValueError):
        _parse_judge_output(raw)


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------

def test_is_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("JUDGE_ENABLED", raising=False)
    assert is_enabled() is False


def test_is_enabled_true_when_env_true(monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    assert is_enabled() is True


def test_is_enabled_case_insensitive(monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "TRUE")
    assert is_enabled() is True


# ---------------------------------------------------------------------------
# audit_assessment (full integration with mock LLM)
# ---------------------------------------------------------------------------

@pytest.fixture
def shared_session_local(db_session, monkeypatch):
    """audit 内部用 SessionLocal()。注入 wrapper 让测试可见。"""
    class _NonClosingSession:
        def __init__(self, real): self._real = real
        def __call__(self): return self
        def __getattr__(self, name): return getattr(self._real, name)
        def close(self): pass
    wrapper = _NonClosingSession(db_session)
    monkeypatch.setattr(report_audit, "SessionLocal", wrapper)
    return db_session


def _make_complete_assessment(db, *, user_id=None):
    if user_id is None:
        u = User(openid="o_audit_test")
        db.add(u); db.commit(); db.refresh(u)
        user_id = u.id
    a = Assessment(
        user_id=user_id, session_id="audit-test", status="complete",
        diagnosis_json=json.dumps({"type_code": "S-CL-H", "type_name": "稳"}),
        report_text="--Title--《稳》--Suggestion--试试看",
        prompt_version="2.0", report_version=1,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


@pytest.mark.asyncio
async def test_audit_disabled_returns_none(shared_session_local, monkeypatch):
    monkeypatch.delenv("JUDGE_ENABLED", raising=False)
    a = _make_complete_assessment(shared_session_local)
    result = await audit_assessment(a.id)
    assert result is None


@pytest.mark.asyncio
async def test_audit_writes_row_when_enabled(shared_session_local, monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-test-pro")
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    a = _make_complete_assessment(shared_session_local)

    fake_output = json.dumps({
        "coherence_score": 9, "readability_score": 8,
        "factual_score": 9, "overall_score": 9,
        "summary": "整体表达忠于诊断，措辞自然。",
    })

    async def fake_chat(**kwargs):
        sink = kwargs.get("usage_sink")
        if sink is not None:
            sink["prompt_tokens"] = 1200
            sink["completion_tokens"] = 80
        return fake_output

    monkeypatch.setattr(report_audit, "chat_completion", fake_chat)
    audit = await audit_assessment(a.id, session_id="audit-test")
    assert audit is not None
    assert audit.overall_score == 9
    assert audit.coherence_score == 9
    assert audit.judge_model == "doubao-test-pro"
    assert audit.prompt_version == "2.0"
    assert audit.prompt_tokens == 1200
    assert audit.completion_tokens == 80

    shared_session_local.expire_all()
    saved = shared_session_local.query(ReportQualityAudit).filter_by(id=audit.id).first()
    assert saved is not None
    assert saved.overall_score == 9


@pytest.mark.asyncio
async def test_audit_uses_judge_model_override(shared_session_local, monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-default")
    monkeypatch.setenv("JUDGE_MODEL", "claude-haiku-test")
    a = _make_complete_assessment(shared_session_local)

    async def fake_chat(**kwargs):
        return json.dumps({
            "coherence_score": 7, "readability_score": 7,
            "factual_score": 7, "overall_score": 7, "summary": "中规中矩",
        })

    monkeypatch.setattr(report_audit, "chat_completion", fake_chat)
    audit = await audit_assessment(a.id)
    assert audit.judge_model == "claude-haiku-test"


@pytest.mark.asyncio
async def test_audit_skips_missing_assessment(shared_session_local, monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "x")
    result = await audit_assessment(99999)
    assert result is None


@pytest.mark.asyncio
async def test_audit_skips_when_report_missing(shared_session_local, monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "x")
    u = User(openid="o_no_report")
    shared_session_local.add(u); shared_session_local.commit(); shared_session_local.refresh(u)
    a = Assessment(
        user_id=u.id, session_id="no-rpt", status="complete",
        diagnosis_json=json.dumps({"type_code": "S"}),
        report_text=None,
    )
    shared_session_local.add(a); shared_session_local.commit(); shared_session_local.refresh(a)
    result = await audit_assessment(a.id)
    assert result is None


@pytest.mark.asyncio
async def test_audit_returns_none_when_llm_fails(shared_session_local, monkeypatch):
    from app.services.llm_client import LLMError
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "x")
    a = _make_complete_assessment(shared_session_local)

    async def boom(**kwargs):
        raise LLMError("upstream down")

    monkeypatch.setattr(report_audit, "chat_completion", boom)
    result = await audit_assessment(a.id)
    assert result is None
    assert shared_session_local.query(ReportQualityAudit).count() == 0


@pytest.mark.asyncio
async def test_audit_returns_none_when_output_unparseable(shared_session_local, monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    monkeypatch.setenv("DOUBAO_MODEL", "x")
    a = _make_complete_assessment(shared_session_local)

    async def fake(**kwargs):
        return "完全不是 JSON 也不带括号"

    monkeypatch.setattr(report_audit, "chat_completion", fake)
    result = await audit_assessment(a.id)
    assert result is None
    assert shared_session_local.query(ReportQualityAudit).count() == 0


# ---------------------------------------------------------------------------
# schedule_audit
# ---------------------------------------------------------------------------

def test_schedule_audit_no_op_when_disabled(monkeypatch):
    monkeypatch.delenv("JUDGE_ENABLED", raising=False)
    task = schedule_audit(123)
    assert task is None


@pytest.mark.asyncio
async def test_schedule_audit_returns_task_when_enabled(monkeypatch):
    monkeypatch.setenv("JUDGE_ENABLED", "true")
    called: list[int] = []

    async def fake_audit(assessment_id, *, session_id=None):
        called.append(assessment_id)
        return None

    monkeypatch.setattr(report_audit, "audit_assessment", fake_audit)
    task = schedule_audit(42, session_id="abc")
    assert task is not None
    await task
    assert called == [42]
