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
