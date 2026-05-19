"""
LLM client — async wrapper around the Doubao (豆包) chat completion API.
Every call (success or error) is logged to the ai_call_logs table and,
optionally, to a JSONL file when AI_LOG_PATH is set.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator

import httpx
from starlette.concurrency import run_in_threadpool

from app.services.llm_logger import log_ai_call

# Background tasks fired from request finally{} would be GC'd while still running;
# keep a strong reference until each one completes.
_background_log_tasks: set[asyncio.Task] = set()

DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
_TIMEOUT_SECONDS = 120

_client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
_logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM API call fails for any reason."""


def _write_db_log(
    *,
    agent: str,
    model: str,
    temperature: float,
    session_id: str | None,
    user_id: int | None,
    status: str,
    error_message: str | None,
    http_status_code: int | None,
    retry_index: int,
    system_prompt: str,
    messages: list[dict],
    reply: str,
    duration_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Synchronous DB write — runs in a thread pool."""
    from app.database import SessionLocal
    from app.models.ai_call_log import AiCallLog

    db = SessionLocal()
    try:
        messages_str = json.dumps(messages, ensure_ascii=False)
        # Truncate very long message lists (e.g. answer packages) to keep rows manageable
        if len(messages_str) > 10_000:
            messages_str = messages_str[:10_000] + "…[truncated]"

        entry = AiCallLog(
            agent=agent,
            model=model,
            temperature=temperature,
            session_id=session_id,
            user_id=user_id,
            status=status,
            error_message=error_message,
            http_status_code=http_status_code,
            retry_index=retry_index,
            system_prompt_len=len(system_prompt),
            messages_json=messages_str,
            response_preview=reply[:2000] if reply else None,
            response_len=len(reply),
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        _logger.warning("[llm_client] DB log write failed: %s", exc)
    finally:
        db.close()


async def chat_completion(
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
    agent: str = "unknown",
    session_id: str | None = None,
    user_id: int | None = None,
    retry_index: int = 0,
    usage_sink: dict | None = None,
) -> str:
    """Send a chat completion request and return the assistant reply text.

    Always writes one row to ai_call_logs (status=success or error).

    Args:
        system_prompt: Injected as the first system message.
        messages: Conversation history (role/content dicts).
        temperature: Sampling temperature.
        agent: Logical agent name for log filtering.
        session_id: Assessment session_id for log correlation.
        user_id: User id for log correlation.
        retry_index: Which retry attempt this is (0 = first try).

    Returns:
        The assistant's reply string.

    Raises:
        LLMError: On HTTP errors, network failures, or unexpected response shapes.
    """
    api_key = os.environ["DOUBAO_API_KEY"]
    model = os.environ["DOUBAO_MODEL"]

    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
    }

    t0 = time.monotonic()
    status = "error"
    reply = ""
    error_message: str | None = None
    http_status_code: int | None = None
    prompt_tokens = 0
    completion_tokens = 0

    try:
        try:
            response = await _client.post(
                DOUBAO_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            http_status_code = exc.response.status_code
            error_message = f"HTTP {http_status_code}: {exc.response.text[:200]}"
            raise LLMError(f"API error {http_status_code}") from exc
        except httpx.HTTPError as exc:
            error_message = f"Network error: {exc}"
            raise LLMError(error_message) from exc

        data = response.json()
        try:
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            error_message = f"Unexpected response shape: {response.text[:200]}"
            raise LLMError(error_message) from exc

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = prompt_tokens
            usage_sink["completion_tokens"] = completion_tokens
        status = "success"
        return reply

    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
        _logger.info(
            "[llm] agent=%s retry=%d status=%s duration=%dms tokens=%d+%d session=%s",
            agent, retry_index, status, duration_ms,
            prompt_tokens, completion_tokens,
            (session_id or "")[:8],
        )
        # DB write (5–20ms commit) is the costly one — fire and forget so the LLM
        # reply returns to the caller immediately. JSONL append is a few-ms file
        # write; keep it synchronous so AI_LOG_PATH consumers see entries promptly.
        db_task = asyncio.create_task(run_in_threadpool(
            _write_db_log,
            agent=agent,
            model=model,
            temperature=temperature,
            session_id=session_id,
            user_id=user_id,
            status=status,
            error_message=error_message,
            http_status_code=http_status_code,
            retry_index=retry_index,
            system_prompt=system_prompt,
            messages=messages,
            reply=reply,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ))
        _background_log_tasks.add(db_task)
        db_task.add_done_callback(_background_log_tasks.discard)

        log_path = os.environ.get("AI_LOG_PATH", "")
        if log_path:
            try:
                log_ai_call(
                    log_path=log_path,
                    agent=agent,
                    system_prompt=system_prompt,
                    messages=messages,
                    response=reply,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            except Exception as exc:
                _logger.warning("[llm] JSONL log write failed: %s", exc)


async def stream_chat_completion(
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
    usage_sink: dict | None = None,
) -> AsyncIterator[str]:
    """Stream chat completion, yielding text chunks as the LLM generates them.

    Args:
        usage_sink: 可选 dict — 若提供，最后一个 SSE event 解析出的 usage
                    会写入 {"prompt_tokens": int, "completion_tokens": int}。
                    豆包按 OpenAI 协议，需 stream_options.include_usage=true 才返回。

    Raises:
        LLMError: On HTTP errors or network failures.
    """
    api_key = os.environ["DOUBAO_API_KEY"]
    model = os.environ["DOUBAO_MODEL"]

    payload = {
        "model": model,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": temperature,
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
            if response.status_code >= 400:
                await response.aread()
                body = response.text[:300]
                _logger.error("[llm] stream %d body: %s", response.status_code, body)
                raise LLMError(f"API error {response.status_code}: {body}")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                # usage 通常出现在最后一个 chunk 的顶层（OpenAI 协议 + include_usage）
                if usage_sink is not None:
                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        if "prompt_tokens" in usage:
                            usage_sink["prompt_tokens"] = int(usage["prompt_tokens"])
                        if "completion_tokens" in usage:
                            usage_sink["completion_tokens"] = int(usage["completion_tokens"])
                try:
                    content = chunk["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, TypeError):
                    continue
                if content:
                    yield content
    except httpx.HTTPError as exc:
        raise LLMError(f"Network error: {exc}") from exc
