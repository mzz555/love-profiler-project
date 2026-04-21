"""
Tests for agent2_analysis — personality scoring and report generation.
All test data uses synthetic values only.
"""

from unittest.mock import AsyncMock, patch
import pytest

from app.agents.agent2_analysis import (
    generate_report,
    map_personality_type,
    AnalysisResult,
    PERSONALITY_TYPES,
)

# ---------------------------------------------------------------------------
# Shared fixtures — 5-dimension nested schema (synthetic values)
# ---------------------------------------------------------------------------

SECURE_SIGNALS = {
    "separation_anxiety": {"signal": "low",          "weight": "strong", "evidence": "不在意回复速度"},
    "intimacy_comfort":   {"signal": "low_avoidance", "weight": "strong", "evidence": "自然接受亲密"},
    "conflict_pattern":   {"signal": "collaborative", "weight": "strong", "evidence": "寻求解决方案"},
    "needs_expression":   {"signal": "explicit",      "weight": "strong", "evidence": "直接表达需求"},
    "attribution":        {"signal": "event",         "weight": "strong", "evidence": "归因具体事件"},
}

ANXIOUS_SIGNALS = {
    "separation_anxiety": {"signal": "high",          "weight": "strong", "evidence": "反复查看手机"},
    "intimacy_comfort":   {"signal": "low_avoidance",  "weight": "strong", "evidence": "渴望更多陪伴"},
    "conflict_pattern":   {"signal": "attack",         "weight": "strong", "evidence": "用你总是开头"},
    "needs_expression":   {"signal": "implicit",       "weight": "weak",   "evidence": "通过冷战暗示"},
    "attribution":        {"signal": "self_blame",     "weight": "strong", "evidence": "觉得是自己不够好"},
}

AVOIDANT_SIGNALS = {
    "separation_anxiety": {"signal": "low",           "weight": "strong", "evidence": "不在意对方不回复"},
    "intimacy_comfort":   {"signal": "high_avoidance", "weight": "strong", "evidence": "越近越犹豫"},
    "conflict_pattern":   {"signal": "withdraw",       "weight": "strong", "evidence": "沉默关机离开"},
    "needs_expression":   {"signal": "implicit",       "weight": "weak",   "evidence": "期待对方应该知道"},
    "attribution":        {"signal": "external",       "weight": "strong", "evidence": "归因对方有问题"},
}

UNKNOWN_SIGNALS = {
    "separation_anxiety": {"signal": "unknown", "weight": "weak", "evidence": "x"},
    "intimacy_comfort":   {"signal": "unknown", "weight": "weak", "evidence": "x"},
    "conflict_pattern":   {"signal": "unknown", "weight": "weak", "evidence": "x"},
    "needs_expression":   {"signal": "unknown", "weight": "weak", "evidence": "x"},
    "attribution":        {"signal": "unknown", "weight": "weak", "evidence": "x"},
}

MOCK_REPORT_TEXT = "你是一个情感稳定、善于沟通的伴侣..."


# ---------------------------------------------------------------------------
# map_personality_type
# ---------------------------------------------------------------------------

def test_map_personality_type_returns_string():
    result = map_personality_type(SECURE_SIGNALS)
    assert isinstance(result, str)


def test_map_personality_type_returns_known_type():
    result = map_personality_type(SECURE_SIGNALS)
    assert result in PERSONALITY_TYPES


def test_map_personality_type_secure_signals_give_secure_type():
    result = map_personality_type(SECURE_SIGNALS)
    assert result == "安全型"


def test_map_personality_type_anxious_signals_give_anxious_type():
    result = map_personality_type(ANXIOUS_SIGNALS)
    assert result == "焦虑型"


def test_map_personality_type_avoidant_signals_give_avoidant_type():
    result = map_personality_type(AVOIDANT_SIGNALS)
    assert result == "回避型"


def test_map_personality_type_disorganized_when_both_axes_high():
    signals = {
        "separation_anxiety": {"signal": "high",          "weight": "strong", "evidence": "x"},
        "intimacy_comfort":   {"signal": "high_avoidance", "weight": "strong", "evidence": "x"},
        "conflict_pattern":   {"signal": "attack",         "weight": "strong", "evidence": "x"},
        "needs_expression":   {"signal": "implicit",       "weight": "weak",   "evidence": "x"},
        "attribution":        {"signal": "self_blame",     "weight": "strong", "evidence": "x"},
    }
    result = map_personality_type(signals)
    assert result == "混乱型"


def test_map_personality_type_handles_unknown_signals():
    result = map_personality_type(UNKNOWN_SIGNALS)
    assert result in PERSONALITY_TYPES


def test_map_personality_type_handles_empty_dict():
    result = map_personality_type({})
    assert result in PERSONALITY_TYPES


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_report_returns_analysis_result():
    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT_TEXT),
    ):
        result = await generate_report(SECURE_SIGNALS)

    assert isinstance(result, AnalysisResult)


@pytest.mark.asyncio
async def test_generate_report_includes_personality_type():
    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT_TEXT),
    ):
        result = await generate_report(SECURE_SIGNALS)

    assert result.personality_type in PERSONALITY_TYPES


@pytest.mark.asyncio
async def test_generate_report_includes_report_text():
    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT_TEXT),
    ):
        result = await generate_report(SECURE_SIGNALS)

    assert result.report_text == MOCK_REPORT_TEXT


@pytest.mark.asyncio
async def test_generate_report_passes_signals_to_llm():
    captured = {}

    async def capture(system_prompt, messages):
        captured["system_prompt"] = system_prompt
        captured["messages"] = messages
        return MOCK_REPORT_TEXT

    with patch("app.agents.agent2_analysis.chat_completion", new=AsyncMock(side_effect=capture)):
        await generate_report(SECURE_SIGNALS)

    prompt_content = captured["system_prompt"] + str(captured["messages"])
    assert "separation_anxiety" in prompt_content or "安全型" in prompt_content


@pytest.mark.asyncio
async def test_generate_report_summary_field_is_non_empty():
    with patch(
        "app.agents.agent2_analysis.chat_completion",
        new=AsyncMock(return_value=MOCK_REPORT_TEXT),
    ):
        result = await generate_report(SECURE_SIGNALS)

    assert isinstance(result.summary, str) and len(result.summary) > 0


# ---------------------------------------------------------------------------
# AnalysisResult fields
# ---------------------------------------------------------------------------

def test_analysis_result_has_required_fields():
    result = AnalysisResult(
        personality_type="安全型",
        report_text=MOCK_REPORT_TEXT,
        summary="稳定安全的依恋风格。",
    )
    assert result.personality_type == "安全型"
    assert result.report_text == MOCK_REPORT_TEXT
    assert result.summary == "稳定安全的依恋风格。"
