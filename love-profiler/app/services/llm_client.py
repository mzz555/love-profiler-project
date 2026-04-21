"""
LLM client — async wrapper around the Doubao (豆包) chat completion API.
"""

import json
import os
from collections.abc import AsyncIterator

import httpx

DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
_TIMEOUT_SECONDS = 60

# Persistent client — reuses TCP+TLS connection across requests (saves 100–400ms per call)
_client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)


class LLMError(Exception):
    """Raised when the LLM API call fails for any reason."""


async def chat_completion(
    system_prompt: str,
    messages: list[dict],
) -> str:
    """Send a chat completion request and return the assistant reply text.

    Args:
        system_prompt: Injected as the first system message.
        messages: Conversation history (role/content dicts).

    Returns:
        The assistant's reply string.

    Raises:
        LLMError: On HTTP errors, network failures, or unexpected response shapes.
    """
    api_key = os.environ["DOUBAO_API_KEY"]
    model = os.environ["DOUBAO_MODEL"]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
    }

    try:
        response = await _client.post(
            DOUBAO_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"API error {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Network error: {exc}") from exc

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response shape: {response.text[:200]}") from exc


async def stream_chat_completion(
    system_prompt: str,
    messages: list[dict],
) -> AsyncIterator[str]:
    """Stream chat completion, yielding text chunks as the LLM generates them.

    Raises:
        LLMError: On HTTP errors or network failures.
    """
    api_key = os.environ["DOUBAO_API_KEY"]
    model = os.environ["DOUBAO_MODEL"]

    payload = {
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
    }

    try:
        async with _client.stream(
            "POST",
            DOUBAO_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"API error {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Network error: {exc}") from exc
