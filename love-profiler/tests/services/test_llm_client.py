"""
Tests for llm_client — async wrapper around the Doubao (豆包) chat API.
Uses respx to mock HTTP calls so no real API key is needed.
"""

import pytest
import respx
import httpx

from app.services.llm_client import (
    chat_completion,
    LLMError,
    DOUBAO_API_URL,
)


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
