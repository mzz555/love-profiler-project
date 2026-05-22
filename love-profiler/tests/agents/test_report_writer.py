"""Agent B tests — plain-text output (v2.0 prompt-injection edition).

run() returns the LLM's raw report text; build_user_message() renders the
diagnosis dict as natural-language input that's sent in the user message.
"""

import httpx
import pytest
import respx

from app.agents.report_writer import (
    ReportWriterError as AgentBError,  # alias for minimal test diff
    build_user_message,
    run,
)

DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

DIAGNOSIS = {
    "type_code":    "S-CL-H",
    "type_name":    "稳重的航标",
    "type_tagline": "你不需要完美，就值得被爱",
    "type_detail":  "你的稳不需要被看见。危机出现时，你已经在想怎么解决了。",
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
    "segment_decode": [
        {"dimension": "D1", "code": "S",  "label_cn": "安全型依恋",   "is_healthy": True},
        {"dimension": "D2", "code": "CL", "label_cn": "清晰边界",     "is_healthy": True},
        {"dimension": "D3", "code": "MH", "label_cn": "中度健康冲突", "is_healthy": True},
    ],
    "dimension_meta": {
        "D1": {"code": "D1", "name_cn": "依恋类型", "description": "遭遇关系不确定性时依恋系统的激活模式"},
        "D2": {"code": "D2", "name_cn": "边界意识", "description": "关系中保持独立自我、识别越界行为的能力"},
        "D3": {"code": "D3", "name_cn": "冲突处理", "description": "关系摩擦时的表达方式与修复主动性"},
        "D4": {"code": "D4", "name_cn": "情感需求", "description": "五种爱的语言的相对偏好排序"},
        "D5": {"code": "D5", "name_cn": "亲密风格", "description": "直接性与分享欲两个独立子面"},
    },
    "highlights": [],
}

def _compliant_section(name: str, body: str, min_len: int) -> str:
    pad = max(0, min_len - len(body))
    return f"--{name}--\n{body}{'·' * pad}\n"


# 一份满足 report_quality_gate 硬约束的报告文本，供 mock LLM 输出复用。
REPORT_TEXT = (
    "--Title--\n《稳重的航标》\n"
    + _compliant_section(
        "Opening",
        "你的稳不需要被看见。危机出现时，你已经在想怎么解决，情绪是后来才处理的事。",
        80,
    )
    + _compliant_section("Attachment", "你能稳稳地在场，不需要时刻确认对方在不在身边。",     100)
    + _compliant_section("Boundary",   "你清楚自己的边界，也尊重对方的，不会去越界。",       100)
    + _compliant_section("Conflict",   "面对摩擦你倾向于建设性表达，修复关系是你的本能。",   100)
    + _compliant_section("Language",   "你最被打动的是言语肯定与精心时刻，被夸奖会很安心。", 80)
    + _compliant_section("Style",      "你的表达平衡居中，不让对方读不懂，也不会读太透。",   80)
    + _compliant_section("Suggestion", "明天起，试着在一件小事上直接说出你的感受。",         60)
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


def test_build_user_message_includes_type_detail():
    msg = build_user_message(DIAGNOSIS)
    assert DIAGNOSIS["type_detail"] in msg
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


# ── stream 韧性：重试 + 降级 测试 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_stream_retries_then_falls_back_to_non_stream(monkeypatch, caplog):
    """stream 重试 1 次仍失败 + 未 yield 任何 chunk → 降级到 chat_completion 成功。

    验证：
    1) stream 被调用 2 次（原 + 1 次重试）
    2) chat_completion fallback 被调用 1 次
    3) 完整文本通过 yield 传给客户端
    4) 日志里能看到「降级」关键字
    """
    import logging
    from app.agents import report_writer
    from app.services.llm_client import TransientLLMError

    stream_attempts: list[int] = []

    async def fake_stream_fail(**kwargs):
        stream_attempts.append(len(stream_attempts))
        raise TransientLLMError("Network error (RemoteProtocolError): mock disconnect")
        yield  # makes this an async generator; unreachable

    chat_calls: list[dict] = []

    async def fake_chat(**kwargs):
        chat_calls.append(kwargs)
        usage_sink = kwargs.get("usage_sink")
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 800
            usage_sink["completion_tokens"] = 500
        return REPORT_TEXT

    # 跳过真实 sleep，避免测试等待 1s 重试间隔
    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(report_writer, "stream_chat_completion", fake_stream_fail)
    monkeypatch.setattr(report_writer, "chat_completion", fake_chat)
    monkeypatch.setattr(report_writer.asyncio, "sleep", fake_sleep)

    chunks: list[str] = []
    final = None
    with caplog.at_level(logging.WARNING, logger="app.agents.report_writer"):
        async for item in report_writer.run_stream(DIAGNOSIS):
            if isinstance(item, str):
                chunks.append(item)
            else:
                final = item

    assert len(stream_attempts) == 2, "stream 应被原调用 + 重试共调 2 次"
    assert len(chat_calls) == 1, "fallback chat_completion 应被调 1 次"
    text = "".join(chunks)
    assert text.strip() == REPORT_TEXT.strip(), "完整 REPORT_TEXT 应通过分块 yield 传给客户端"
    assert final is not None and final["report_text"].strip() == REPORT_TEXT.strip()
    # 日志可观测
    log_text = "\n".join(r.message for r in caplog.records)
    assert "降级" in log_text


@pytest.mark.asyncio
async def test_run_stream_mid_failure_does_not_fallback(monkeypatch, caplog):
    """stream 中途已 yield 部分 chunk 后失败 → raise，不重试也不降级（前端已收到部分文本，补不回）。"""
    import logging
    from app.agents import report_writer
    from app.services.llm_client import TransientLLMError

    chat_calls: list[dict] = []

    async def fake_stream_mid_fail(**kwargs):
        yield "前半段已经发出去 "
        raise TransientLLMError("Network error (ReadError): mock mid-stream")

    async def fake_chat(**kwargs):
        chat_calls.append(kwargs)
        return REPORT_TEXT

    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(report_writer, "stream_chat_completion", fake_stream_mid_fail)
    monkeypatch.setattr(report_writer, "chat_completion", fake_chat)
    monkeypatch.setattr(report_writer.asyncio, "sleep", fake_sleep)

    chunks: list[str] = []
    with caplog.at_level(logging.ERROR, logger="app.agents.report_writer"):
        with pytest.raises(TransientLLMError):
            async for item in report_writer.run_stream(DIAGNOSIS):
                if isinstance(item, str):
                    chunks.append(item)

    assert chunks == ["前半段已经发出去 "], "中途失败前已 yield 的 chunk 应保留"
    assert len(chat_calls) == 0, "中途失败不应触发 fallback"
    # 日志包含"中途失败"或"无法重试/降级"关键字
    log_text = "\n".join(r.message for r in caplog.records)
    assert "中途失败" in log_text or "无法" in log_text


@pytest.mark.asyncio
async def test_run_stream_succeeds_first_try_no_retry_no_fallback(monkeypatch):
    """正常路径：stream 第一次就成功，不触发重试也不调 fallback。"""
    from app.agents import report_writer

    stream_calls: list[int] = []
    chat_calls: list[dict] = []

    async def fake_stream_ok(**kwargs):
        stream_calls.append(1)
        usage_sink = kwargs.get("usage_sink")
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 800
            usage_sink["completion_tokens"] = 500
        for piece in (REPORT_TEXT[i:i+50] for i in range(0, len(REPORT_TEXT), 50)):
            yield piece

    async def fake_chat(**kwargs):
        chat_calls.append(kwargs)
        return REPORT_TEXT

    monkeypatch.setattr(report_writer, "stream_chat_completion", fake_stream_ok)
    monkeypatch.setattr(report_writer, "chat_completion", fake_chat)

    chunks: list[str] = []
    final = None
    async for item in report_writer.run_stream(DIAGNOSIS):
        if isinstance(item, str):
            chunks.append(item)
        else:
            final = item

    assert len(stream_calls) == 1
    assert len(chat_calls) == 0, "成功路径不应触发 fallback"
    assert "".join(chunks).strip() == REPORT_TEXT.strip()
    assert final is not None


def test_build_user_message_aligned_false_emits_blind_spot_note():
    diag = {**DIAGNOSIS, "dimensions": {**DIAGNOSIS["dimensions"], "D4": {
        "top2": ["T1", "T2"], "aligned": False, "declared": "T2",
    }}}
    msg = build_user_message(diag)
    assert "自我认知盲区" in msg
    # declared T2 → 中文名「精心时刻」必须出现
    assert "精心时刻" in msg


def test_build_user_message_declared_outside_top2_uses_fallback_name():
    """盲区典型场景：declared ∉ top2，D4_details 不含 declared 详情，
    必须靠 _D4_FALLBACK_NAMES 兜底，绝不能把内部代码 T1 塞进 prompt。

    历史 bug：兜底缺失时 LLM 收到「用户主动选择的是「T1」」，
    导致它把 prompt 模板里的 [用户主观选择的类型中文名] 占位符原样输出。
    """
    diag = {**DIAGNOSIS, "dimensions": {**DIAGNOSIS["dimensions"], "D4": {
        "top2": ["T4", "T5"], "aligned": False, "declared": "T1",
    }}, "D4_details": [
        {"code": "T4", "name": "服务行动", "detail": "希望对方用实际行动..."},
        {"code": "T5", "name": "身体接触", "detail": "希望通过拥抱..."},
    ]}
    msg = build_user_message(diag)
    assert "自我认知盲区" in msg
    # declared T1 → 静态兜底翻译为「言语肯定」
    assert "言语肯定" in msg
    # top2[0] T4 → DB 注入翻译为「服务行动」
    assert "服务行动" in msg
    # 绝不能出现裸 T1 / T4 这种内部代码（盲区句子里）
    assert "「T1」" not in msg
    assert "「T4」" not in msg


def test_build_user_message_pursue_avoid_role_emitted():
    diag = {**DIAGNOSIS, "dimensions": {**DIAGNOSIS["dimensions"], "D3": {
        "interp": "mixed", "pursue_avoid": "pursue",
    }}}
    msg = build_user_message(diag)
    assert "追逃角色：pursue" in msg


def test_build_user_message_omits_pursue_avoid_when_stable():
    msg = build_user_message(DIAGNOSIS)
    assert "追逃角色" not in msg


def test_build_user_message_empty_highlights_marks_skip():
    msg = build_user_message(DIAGNOSIS)
    assert "highlights 为空" in msg


# ── run_stream（异步流式） ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_stream_yields_chunks_then_final_dict():
    """run_stream 应实时 yield 文本片段，最后 yield 一次 {report_text: 全文, quality_warnings: [...]}"""
    from unittest.mock import patch
    from app.agents.report_writer import run_stream

    # 把合规 REPORT_TEXT 切成 4 段，保留原序作为 chunk
    n = len(REPORT_TEXT)
    boundaries = [0, n // 4, n // 2, 3 * n // 4, n]
    pieces = [REPORT_TEXT[boundaries[i]:boundaries[i + 1]] for i in range(4)]

    async def fake_stream(**kwargs):
        for p in pieces:
            yield p

    with patch("app.agents.report_writer.stream_chat_completion", new=fake_stream):
        out = []
        async for item in run_stream(DIAGNOSIS, session_id="abcdefgh"):
            out.append(item)

    assert [x for x in out[:-1]] == pieces
    final = out[-1]
    assert isinstance(final, dict)
    assert final["report_text"] == "".join(pieces) == REPORT_TEXT
    assert "quality_warnings" in final


@pytest.mark.asyncio
async def test_run_stream_raises_on_quality_gate_failure():
    """LLM 输出缺 --Attachment-- → AgentBError(quality_gate_failed)，不发 final dict。"""
    from unittest.mock import patch
    from app.agents.report_writer import run_stream

    broken = REPORT_TEXT.replace("--Attachment--", "--ZZZSkip--")

    async def fake_stream(**kwargs):
        yield broken

    with patch("app.agents.report_writer.stream_chat_completion", new=fake_stream):
        with pytest.raises(AgentBError, match="quality_gate_failed"):
            async for _ in run_stream(DIAGNOSIS):
                pass


@pytest.mark.asyncio
@respx.mock
async def test_run_retries_on_quality_gate_failure_then_succeeds():
    """run() 在质量门失败时应自动重试一次。"""
    bad = REPORT_TEXT.replace("--Attachment--", "--ZZZSkip--")
    responses = [_ok_response(bad), _ok_response(REPORT_TEXT)]
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    respx.post(DOUBAO_URL).mock(side_effect=side_effect)
    result = await run(DIAGNOSIS)
    assert call_count == 2
    assert "--Attachment--" in result


@pytest.mark.asyncio
@respx.mock
async def test_run_raises_when_all_quality_gate_failures():
    bad = REPORT_TEXT.replace("--Attachment--", "--ZZZSkip--")
    respx.post(DOUBAO_URL).mock(return_value=_ok_response(bad))
    with pytest.raises(AgentBError, match="quality_gate_failed"):
        await run(DIAGNOSIS)


@pytest.mark.asyncio
async def test_run_stream_raises_on_empty_response():
    """流式 LLM 全程返回空白（仅空格/换行）应抛 AgentBError，不发 final dict。"""
    from unittest.mock import patch
    from app.agents.report_writer import run_stream

    async def fake_empty(**kwargs):
        for _ in range(3):
            yield "   "  # 全空白

    with patch("app.agents.report_writer.stream_chat_completion", new=fake_empty):
        with pytest.raises(AgentBError):
            async for _ in run_stream(DIAGNOSIS):
                pass


# ── Phase C.1 · resumed_sections + append_resume_directive ─────────────────

def test_append_resume_directive_no_op_when_resumed_empty():
    from app.agents.report_writer import append_resume_directive
    msg = "原始 user msg"
    assert append_resume_directive(msg, None) == msg
    assert append_resume_directive(msg, {}) == msg


def test_append_resume_directive_lists_completed_and_next():
    from app.agents.report_writer import append_resume_directive
    msg = "原始 user msg"
    out = append_resume_directive(msg, {
        "Title": "《稳重的航标》",
        "Opening": "你的稳不需要被看见。" * 5,
    })
    assert "接续生成" in out
    assert "Title" in out
    assert "Opening" in out
    # Title 之后的下一个未完成段是 Attachment
    assert "--Attachment--" in out


def test_append_resume_directive_truncates_long_snippets():
    from app.agents.report_writer import append_resume_directive
    very_long = "x" * 1000
    out = append_resume_directive("msg", {"Title": very_long})
    # 摘要应有省略号，且不会把整段塞进去
    assert "…" in out
    assert out.count("x") < 200


def test_append_resume_directive_all_done_returns_msg_unchanged():
    """所有 9 个 sections 都在 resumed 里时不应再要求接续。"""
    from app.agents.report_writer import SECTION_ORDER, append_resume_directive
    resumed = {name: "已完成" for name in SECTION_ORDER}
    msg = "原始"
    assert append_resume_directive(msg, resumed) == msg


def test_append_resume_directive_skips_gaps_and_picks_first_missing():
    """resumed 中段不连续时，取第一个 SECTION_ORDER 缺的作为接续起点。"""
    from app.agents.report_writer import append_resume_directive
    out = append_resume_directive(
        "msg",
        {"Title": "T", "Opening": "O", "Conflict": "C"},  # 缺 Attachment / Boundary
    )
    assert "--Attachment--" in out


@pytest.mark.asyncio
async def test_run_stream_resumed_prepends_completed_sections_to_final_text():
    """run_stream 在 resumed 模式下，最终 yield 的 report_text 应包含已完成段。"""
    from unittest.mock import patch
    from app.agents.report_writer import run_stream

    # 所有段都给足字数以通过 quality gate（Attachment/Boundary/Conflict/Language/Style ≥80）
    resumed = {
        "Title":      "《稳重的航标》",
        "Opening":    "你的稳不需要被看见，危机出现时你已经在想怎么解决。" + ("·" * 120),
        "Attachment": "你能稳稳地在场，不需要时刻确认对方是否在身边。" + ("·" * 120),
        "Boundary":   "你清楚自己的边界，也尊重对方，不会去越界。" + ("·" * 120),
        "Conflict":   "面对摩擦你倾向于建设性表达，修复关系是你的本能。" + ("·" * 120),
        "Language":   "你最被打动的是言语肯定与精心时刻，被夸奖会很安心。" + ("·" * 100),
        "Style":      "你的表达平衡居中，不让对方读不懂，也不会读太透。" + ("·" * 100),
    }
    # LLM 只补 Highlight + Suggestion 两段（resumed 缺这两段；highlights=[] 故 Highlight 可省）
    new_segment = "--Suggestion--\n明天起，试着在一件小事上直接说出你的感受。" + ("·" * 70)

    async def fake_stream(**kwargs):
        for c in (new_segment[:30], new_segment[30:]):
            yield c

    with patch("app.agents.report_writer.stream_chat_completion", new=fake_stream):
        out = []
        async for item in run_stream(DIAGNOSIS, resumed_sections=resumed):
            out.append(item)

    final = out[-1]
    assert isinstance(final, dict)
    text = final["report_text"]
    # resumed 段在前
    assert text.startswith("--Title--")
    # 已完成段都出现
    assert "Opening" in text
    assert "Suggestion" in text


def test_build_user_message_highlights_render_seed():
    diag = {**DIAGNOSIS, "highlights": [
        {
            "code": "add-cv1-pressure-collapse",
            "name_cn": "压力表达崩塌",
            "is_positive": False,
            "report_seed": "在压力下你倾向于沉默而非开口",
        },
    ]}
    msg = build_user_message(diag)
    assert "压力表达崩塌" in msg
    assert "在压力下你倾向于沉默而非开口" in msg
