"""Agent B tests — plain-text output (v2.0 prompt-injection edition).

run() returns the LLM's raw report text; build_user_message() renders the
diagnosis dict as natural-language input that's sent in the user message.
"""

import httpx
import pytest
import respx

from app.agents.agent_b import AgentBError, build_user_message, run

DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

DIAGNOSIS = {
    "type_code":    "S-CL-H",
    "type_name":    "稳重的航标",
    "type_tagline": "你不需要完美，就值得被爱",
    "type_anchor":  "你的稳不需要被看见。危机出现时，你已经在想怎么解决了。",
    "dimensions": {
        "D1": {"interp": "secure"},
        "D2": {"interp": "clear"},
        "D3": {"interp": "moderate_healthy", "pursue_avoid": "stable"},
        "D4": {"top2": ["T1", "T2"], "aligned": True, "declared": "T1"},
        "D5": {"quadrant": "中直接×中分享", "style": "默认型"},
    },
    "D4_details": [
        {"code": "T1", "name": "言语肯定", "detail": "被具体说出来的夸奖、认可"},
        {"code": "T2", "name": "精心时刻", "detail": "专注陪伴，放下手机"},
    ],
    "D5_guide": "不会让对方读不懂，也不会让对方读太透；表达平衡居中。写法示范：「你的表达不会让人困惑，也没有特别暴露。」",
    "highlights": [],
}

REPORT_TEXT = (
    "**《稳重的航标》**\n\n"
    "你的稳不需要被看见。危机出现时，你已经在想怎么解决了，情绪是后来才处理的事。\n\n"
    "## 依恋\n你能稳稳地在场，不需要时刻确认对方在不在。\n\n"
    "## 收尾建议\n明天起，试着在一件小事上直接说出你的感受。"
)


def _ok_response(content: str = REPORT_TEXT) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 800, "completion_tokens": 500, "total_tokens": 1300},
        },
    )


@pytest.mark.asyncio
@respx.mock
async def test_run_returns_plain_text():
    respx.post(DOUBAO_URL).mock(return_value=_ok_response())
    result = await run(DIAGNOSIS)
    assert isinstance(result, str)
    assert "稳重的航标" in result


@pytest.mark.asyncio
@respx.mock
async def test_run_retries_on_empty_then_succeeds():
    responses = [_ok_response(""), _ok_response()]
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    respx.post(DOUBAO_URL).mock(side_effect=side_effect)
    result = await run(DIAGNOSIS)
    assert call_count == 2
    assert result.strip()


@pytest.mark.asyncio
@respx.mock
async def test_run_raises_when_all_attempts_empty():
    respx.post(DOUBAO_URL).mock(return_value=_ok_response(""))
    with pytest.raises(AgentBError):
        await run(DIAGNOSIS)


def test_build_user_message_includes_type_anchor():
    msg = build_user_message(DIAGNOSIS)
    assert DIAGNOSIS["type_anchor"] in msg
    assert DIAGNOSIS["type_name"] in msg


def test_build_user_message_includes_d4_details():
    msg = build_user_message(DIAGNOSIS)
    assert "言语肯定" in msg
    assert "精心时刻" in msg


def test_build_user_message_d5_injects_guide_from_diagnosis():
    """D5_guide is now sourced from diagnosis (enriched by /quiz/submit), not a local dict."""
    msg = build_user_message(DIAGNOSIS)
    assert "默认型" in msg
    assert "中直接×中分享" in msg
    # D5_guide 内容必须出现
    assert "表达平衡居中" in msg
    assert "该象限写作方向" in msg


def test_build_user_message_d5_omits_guide_line_when_missing():
    """When diagnosis lacks D5_guide (legacy data, DB miss), the guide line is skipped."""
    diag = {**DIAGNOSIS}
    diag.pop("D5_guide", None)
    msg = build_user_message(diag)
    # quadrant + style 仍然显示
    assert "默认型" in msg
    # 但写作方向那一行不再出现
    assert "该象限写作方向" not in msg


def test_build_user_message_aligned_false_emits_blind_spot_note():
    diag = {**DIAGNOSIS, "dimensions": {**DIAGNOSIS["dimensions"], "D4": {
        "top2": ["T1", "T2"], "aligned": False, "declared": "T3",
    }}}
    msg = build_user_message(diag)
    assert "aligned=false" in msg
    assert "自我认知盲区" in msg


def test_build_user_message_pursue_avoid_role_emitted():
    diag = {**DIAGNOSIS, "dimensions": {**DIAGNOSIS["dimensions"], "D3": {
        "interp": "mixed", "pursue_avoid": "pursue",
    }}}
    msg = build_user_message(diag)
    assert "追逃角色 = pursue" in msg


def test_build_user_message_omits_pursue_avoid_when_stable():
    msg = build_user_message(DIAGNOSIS)
    assert "追逃角色" not in msg


def test_build_user_message_empty_highlights_marks_skip():
    msg = build_user_message(DIAGNOSIS)
    assert "highlights 为空" in msg


def test_build_user_message_highlights_render_seed_and_path():
    diag = {**DIAGNOSIS, "highlights": [
        {
            "code": "add-cv1-pressure-collapse",
            "name_cn": "压力表达崩塌",
            "severity": "moderate",
            "is_positive": False,
            "report_seed": "在压力下你倾向于沉默而非开口",
            "interp_path": "由 D3.S1 + D5 共同推得",
        },
    ]}
    msg = build_user_message(diag)
    assert "压力表达崩塌" in msg
    assert "在压力下你倾向于沉默而非开口" in msg
    assert "由 D3.S1 + D5 共同推得" in msg
