"""
Tests for llm_client — async wrapper around the Doubao (豆包) chat API.
Uses respx to mock HTTP calls so no real API key is needed.
"""

import asyncio

import pytest
import respx
import httpx

from app.services.llm_client import (
    chat_completion,
    LLMError,
    TransientLLMError,
    DOUBAO_API_URL,
)


@pytest.fixture(autouse=True)
def _skip_real_sleep(monkeypatch):
    """避免 Phase B.2 内部 transient retry 在测试里真睡几秒。"""

    async def _noop(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.services.llm_client._sleep", _noop)


FAKE_API_KEY = "test-api-key-12345"
SYSTEM_PROMPT = "You are a helpful assistant."
MESSAGES = [{"role": "user", "content": "hello"}]
MOCK_REPLY = "你好！很高兴认识你。"


def _mock_success_response(reply: str = MOCK_REPLY) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": reply,
                }
            }
        ]
    }


# ---------------------------------------------------------------------------
# Successful call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_returns_reply_text(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, json=_mock_success_response())
    )

    result = await chat_completion(
        system_prompt=SYSTEM_PROMPT,
        messages=MESSAGES,
    )
    assert result == MOCK_REPLY


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_sends_system_message(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    captured = {}

    async def capture_request(request: httpx.Request):
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_mock_success_response())

    respx.post(DOUBAO_API_URL).mock(side_effect=capture_request)

    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)

    sent_messages = captured["body"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == SYSTEM_PROMPT


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_appends_user_messages_after_system(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    captured = {}

    async def capture_request(request: httpx.Request):
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_mock_success_response())

    respx.post(DOUBAO_API_URL).mock(side_effect=capture_request)

    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)

    sent_messages = captured["body"]["messages"]
    assert len(sent_messages) == 2
    assert sent_messages[1] == MESSAGES[0]


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_sends_auth_header(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    captured = {}

    async def capture_request(request: httpx.Request):
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_mock_success_response())

    respx.post(DOUBAO_API_URL).mock(side_effect=capture_request)

    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)

    auth = captured["headers"].get("authorization", "")
    assert auth == f"Bearer {FAKE_API_KEY}"


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_raises_llm_error_on_4xx(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )

    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_raises_llm_error_on_5xx(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(500, json={"error": "Internal Server Error"})
    )

    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_raises_llm_error_on_network_failure(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    respx.post(DOUBAO_API_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_raises_llm_error_on_malformed_response(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )

    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)


# ---------------------------------------------------------------------------
# Instrumentation: temperature, timing, token extraction, logging
# ---------------------------------------------------------------------------


def _mock_response_with_usage(reply: str = MOCK_REPLY) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": reply}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49},
    }


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_accepts_temperature(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    captured = {}

    async def capture_request(request: httpx.Request):
        import json as _json
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json=_mock_response_with_usage())

    respx.post(DOUBAO_API_URL).mock(side_effect=capture_request)

    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES, temperature=0.1)
    assert captured["body"]["temperature"] == pytest.approx(0.1)


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_logs_call(monkeypatch, tmp_path):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")
    log_path = str(tmp_path / "ai_calls.jsonl")
    monkeypatch.setenv("AI_LOG_PATH", log_path)

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, json=_mock_response_with_usage())
    )

    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES, agent="agent_a")

    import json as _json, os
    assert os.path.exists(log_path)
    entry = _json.loads(open(log_path, encoding="utf-8").read())
    assert entry["agent"] == "agent_a"
    assert entry["prompt_tokens"] == 42
    assert entry["completion_tokens"] == 7
    assert entry["duration_ms"] >= 0


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_skips_log_when_no_path(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")
    monkeypatch.delenv("AI_LOG_PATH", raising=False)

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, json=_mock_response_with_usage())
    )
    result = await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert result == MOCK_REPLY


# ---------------------------------------------------------------------------
# stream_chat_completion
# ---------------------------------------------------------------------------

from app.services.llm_client import stream_chat_completion


def _sse(chunks: list[str]) -> str:
    """构造一段 SSE 协议体：每段做成 data: {...} 行，末尾 [DONE]。"""
    import json as _j
    parts = []
    for c in chunks:
        parts.append('data: ' + _j.dumps({"choices": [{"delta": {"content": c}}]}) + '\n\n')
    parts.append('data: [DONE]\n\n')
    return "".join(parts)


@pytest.mark.asyncio
@respx.mock
async def test_stream_yields_content_chunks_in_order(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    body = _sse(["你好，", "我是", " Agent B"])
    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(
            200, text=body,
            headers={"Content-Type": "text/event-stream"},
        )
    )

    out: list[str] = []
    async for piece in stream_chat_completion(
        system_prompt=SYSTEM_PROMPT, messages=MESSAGES, temperature=0.6,
    ):
        out.append(piece)
    assert out == ["你好，", "我是", " Agent B"]


@pytest.mark.asyncio
@respx.mock
async def test_stream_raises_llm_error_on_4xx(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")
    respx.post(DOUBAO_API_URL).mock(return_value=httpx.Response(401, text="unauthorized"))

    with pytest.raises(LLMError):
        async for _ in stream_chat_completion(
            system_prompt=SYSTEM_PROMPT, messages=MESSAGES,
        ):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_stream_raises_llm_error_on_network_failure(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")
    respx.post(DOUBAO_API_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(LLMError):
        async for _ in stream_chat_completion(
            system_prompt=SYSTEM_PROMPT, messages=MESSAGES,
        ):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_stream_skips_malformed_data_lines(monkeypatch):
    """损坏的 JSON / 缺 choices 字段的行应被跳过，不影响其他正常 chunk。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    body = (
        'data: not-json\n\n'
        'data: {"choices":[{"delta":{"content":"good"}}]}\n\n'
        'data: {"missing": "choices"}\n\n'
        'data: [DONE]\n\n'
    )
    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, text=body,
                                    headers={"Content-Type": "text/event-stream"})
    )

    out: list[str] = []
    async for piece in stream_chat_completion(
        system_prompt=SYSTEM_PROMPT, messages=MESSAGES,
    ):
        out.append(piece)
    assert out == ["good"]


@pytest.mark.asyncio
@respx.mock
async def test_stream_writes_usage_to_sink_when_provided(monkeypatch):
    """B.1：当传入 usage_sink，最后一个 usage event 应解析后写入 sink。"""
    import json as _j
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    body = (
        'data: ' + _j.dumps({"choices": [{"delta": {"content": "你好"}}]}) + '\n\n'
        'data: ' + _j.dumps({"choices": [{"delta": {"content": "世界"}}]}) + '\n\n'
        'data: ' + _j.dumps({
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        }) + '\n\n'
        'data: [DONE]\n\n'
    )
    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, text=body,
                                    headers={"Content-Type": "text/event-stream"})
    )

    sink: dict = {}
    out: list[str] = []
    async for piece in stream_chat_completion(
        system_prompt=SYSTEM_PROMPT, messages=MESSAGES, usage_sink=sink,
    ):
        out.append(piece)
    assert out == ["你好", "世界"]
    assert sink == {"prompt_tokens": 123, "completion_tokens": 45}


@pytest.mark.asyncio
@respx.mock
async def test_stream_without_sink_ignores_usage(monkeypatch):
    """没传 usage_sink 时不出错，正常返回所有 content chunk。"""
    import json as _j
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    body = (
        'data: ' + _j.dumps({"choices": [{"delta": {"content": "a"}}]}) + '\n\n'
        'data: ' + _j.dumps({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}) + '\n\n'
        'data: [DONE]\n\n'
    )
    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, text=body,
                                    headers={"Content-Type": "text/event-stream"})
    )

    out: list[str] = []
    async for piece in stream_chat_completion(
        system_prompt=SYSTEM_PROMPT, messages=MESSAGES,
    ):
        out.append(piece)
    assert out == ["a"]


# ---------------------------------------------------------------------------
# Phase B.2 · transient 错误内部重试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_retries_5xx_then_succeeds(monkeypatch):
    """503 → 503 → 200 应最终返回 reply（默认最多 2 次 retry）。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    responses = [
        httpx.Response(503, text="upstream busy"),
        httpx.Response(503, text="upstream busy"),
        httpx.Response(200, json=_mock_success_response()),
    ]
    call_count = {"n": 0}

    def side_effect(request):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    respx.post(DOUBAO_API_URL).mock(side_effect=side_effect)
    reply = await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert reply == MOCK_REPLY
    assert call_count["n"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_gives_up_after_three_transient_failures(monkeypatch):
    """连续 3 次 5xx 应抛 LLMError（默认 1 + 2 retry = 3 次尝试）。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        return httpx.Response(502, text="bad gateway")

    respx.post(DOUBAO_API_URL).mock(side_effect=side_effect)
    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert call_count["n"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_does_not_retry_4xx(monkeypatch):
    """401 应立即抛 LLMError，不进入重试。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    respx.post(DOUBAO_API_URL).mock(side_effect=side_effect)
    with pytest.raises(LLMError):
        await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert call_count["n"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_retries_network_error(monkeypatch):
    """ConnectError → ConnectError → 200 应最终成功。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json=_mock_success_response())

    respx.post(DOUBAO_API_URL).mock(side_effect=side_effect)
    reply = await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert reply == MOCK_REPLY
    assert call_count["n"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_retries_malformed_response(monkeypatch):
    """200 但 schema 异常视为 transient，重试一次。"""
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")

    responses = [
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, json=_mock_success_response()),
    ]
    call_count = {"n": 0}

    def side_effect(request):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    respx.post(DOUBAO_API_URL).mock(side_effect=side_effect)
    reply = await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert reply == MOCK_REPLY
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_chat_completion_passes_incremented_retry_index_to_each_attempt(monkeypatch):
    """retry_index 应叠加在 caller 传入值上：第 1 次内部尝试用 caller_idx + attempt。

    通过 patch _chat_completion_once 直接断言传入参数，避开 threadpool DB log 写入。
    """
    from app.services import llm_client as _llm

    captured: list[int] = []

    async def fake_once(*, retry_index, **kwargs):
        captured.append(retry_index)
        if retry_index == 5:
            raise _llm.TransientLLMError("first attempt boom")
        return MOCK_REPLY

    monkeypatch.setattr(_llm, "_chat_completion_once", fake_once)
    reply = await chat_completion(
        system_prompt=SYSTEM_PROMPT, messages=MESSAGES, retry_index=5,
    )
    assert reply == MOCK_REPLY
    assert captured == [5, 6]


@pytest.mark.asyncio
async def test_chat_completion_default_retry_index_starts_at_zero(monkeypatch):
    """caller 不传 retry_index 时，内部 attempt 应从 0 开始递增。"""
    from app.services import llm_client as _llm

    captured: list[int] = []

    async def fake_once(*, retry_index, **kwargs):
        captured.append(retry_index)
        if retry_index < 2:
            raise _llm.TransientLLMError("transient")
        return MOCK_REPLY

    monkeypatch.setattr(_llm, "_chat_completion_once", fake_once)
    await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)
    assert captured == [0, 1, 2]


@pytest.mark.asyncio
async def test_transient_llm_error_is_llm_error_subclass():
    """TransientLLMError 必须是 LLMError 子类，保证现有 catch LLMError 的代码无需改。"""
    assert issubclass(TransientLLMError, LLMError)


# ---------------------------------------------------------------------------
# _write_db_log 边界 + JSONL 写失败兜底
# ---------------------------------------------------------------------------

def test_write_db_log_truncates_oversized_messages_json(monkeypatch):
    """messages 序列化后 > 10000 字符应触发截断分支（保留前 10000 + 省略号）。"""
    from app.services.llm_client import _write_db_log

    captured: dict = {}

    class _StubSession:
        def add(self, entry): captured["entry"] = entry
        def commit(self): pass
        def close(self): pass

    def _stub_session_local():
        return _StubSession()

    # 让 _write_db_log 内部 import 的 SessionLocal 走 stub
    import app.database
    monkeypatch.setattr(app.database, "SessionLocal", _stub_session_local)

    # 构造一个超大 messages，超过 10000 字符
    long_content = "x" * 12000
    _write_db_log(
        agent="agent_a", model="m", temperature=0.1,
        session_id=None, user_id=None,
        status="success", error_message=None, http_status_code=None,
        retry_index=0,
        system_prompt="sys", messages=[{"role": "user", "content": long_content}],
        reply="ok", duration_ms=10,
        prompt_tokens=0, completion_tokens=0,
    )
    entry = captured["entry"]
    assert entry.messages_json.endswith("…[truncated]")
    assert len(entry.messages_json) == 10_000 + len("…[truncated]")


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_logs_warning_when_jsonl_write_fails(
    monkeypatch, caplog,
):
    """AI_LOG_PATH 配置但 log_ai_call 抛错时，应记 warning 不中断响应。"""
    import logging
    monkeypatch.setenv("DOUBAO_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-pro-32k")
    monkeypatch.setenv("AI_LOG_PATH", "/some/path/should-not-matter.jsonl")

    respx.post(DOUBAO_API_URL).mock(
        return_value=httpx.Response(200, json=_mock_response_with_usage())
    )

    # 让 log_ai_call 抛异常（模拟磁盘满 / 权限拒绝）
    def boom(**kwargs):
        raise OSError("disk full simulated")
    monkeypatch.setattr("app.services.llm_client.log_ai_call", boom)

    with caplog.at_level(logging.WARNING, logger="app.services.llm_client"):
        result = await chat_completion(system_prompt=SYSTEM_PROMPT, messages=MESSAGES)

    # 主功能不应受影响
    assert result == MOCK_REPLY
    # 兜底 warning 必须打
    assert any("JSONL log write failed" in r.message for r in caplog.records)
