"""
LLM client — async wrapper around the Doubao (豆包) chat completion API.
Every call (success or error) is logged to the ai_call_logs table and,
optionally, to a JSONL file when AI_LOG_PATH is set.

Phase B.2: chat_completion 内置 transient-only 重试：
- 可重试：HTTP 5xx、连接错误、读超时、响应 schema 异常
- 不可重试：HTTP 4xx（auth / quota / bad request）
- 指数退避 base=0.5s, attempts<=2 → 最坏 3 次调用
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

# Retry tuning — keep conservative; outer agent_b quality-gate retry can compound.
_MAX_TRANSIENT_RETRIES = 2          # 总尝试次数 = 1 + _MAX_TRANSIENT_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 0.5     # 退避基数：0.5s → 1s → 2s（最后一次不再 sleep）

_client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
_logger = logging.getLogger(__name__)

# 重试退避用的 sleep 函数；测试时可 monkeypatch 这一引用以避免真正等待。
_sleep = asyncio.sleep


class LLMError(Exception):
    """Raised when the LLM API call fails for any reason."""


class TransientLLMError(LLMError):
    """Subclass for retryable failures (HTTP 5xx, network errors, malformed JSON).

    凡是抛 TransientLLMError 的位置都默认是"重试可能成功"的语义；4xx 类故障应抛
    基类 LLMError，不进入重试循环。
    """


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


async def _chat_completion_once(
    *,
    system_prompt: str,
    messages: list[dict],
    temperature: float,
    agent: str,
    session_id: str | None,
    user_id: int | None,
    retry_index: int,
    usage_sink: dict | None,
) -> str:
    """单次 chat completion 调用：负责发请求 + 解析 + 写日志。

    可重试错误（5xx / 网络 / 协议异常）抛 TransientLLMError；
    不可重试错误（4xx）抛基类 LLMError。
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
            if 500 <= http_status_code < 600:
                raise TransientLLMError(f"API error {http_status_code}") from exc
            raise LLMError(f"API error {http_status_code}") from exc
        except httpx.HTTPError as exc:
            # ConnectError / ReadTimeout / RemoteProtocolError 等抖动类
            # 用 type 名 + repr 而不是 str，避免某些异常 __str__ 为空时尾巴空白看不出根因
            error_message = f"Network error ({type(exc).__name__}): {exc!r}"
            raise TransientLLMError(error_message) from exc

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            error_message = f"Response not JSON: {response.text[:200]}"
            raise TransientLLMError(error_message) from exc

        try:
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            error_message = f"Unexpected response shape: {response.text[:200]}"
            raise TransientLLMError(error_message) from exc

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


def _backoff_seconds(attempt: int) -> float:
    """attempt=0 → 0.5s, =1 → 1s, =2 → 2s"""
    return _RETRY_BASE_DELAY_SECONDS * (2 ** attempt)


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
    """Send a chat completion request with transient-error retry.

    每次内部 transient retry 都会重新调用 _chat_completion_once，因此每次都会
    在 ai_call_logs 写一行（retry_index = caller 传入值 + 本次内部 attempt）。

    Args:
        retry_index: 调用方意图的"外层 retry 计数"（来自 report_writer.run 的 quality-gate
                     retry）；内部 transient 重试会在此基础上 +attempt 写入日志。

    Raises:
        LLMError: 4xx（永久失败）或 transient 错误重试到上限仍未恢复。
    """
    last_transient: TransientLLMError | None = None
    for attempt in range(_MAX_TRANSIENT_RETRIES + 1):
        effective_retry_index = retry_index + attempt
        try:
            return await _chat_completion_once(
                system_prompt=system_prompt,
                messages=messages,
                temperature=temperature,
                agent=agent,
                session_id=session_id,
                user_id=user_id,
                retry_index=effective_retry_index,
                usage_sink=usage_sink,
            )
        except TransientLLMError as exc:
            last_transient = exc
            if attempt >= _MAX_TRANSIENT_RETRIES:
                _logger.error(
                    "[llm/retry] agent=%s attempt=%d 已达上限，放弃：%s",
                    agent, attempt, exc,
                )
                raise
            sleep_s = _backoff_seconds(attempt)
            _logger.warning(
                "[llm/retry] agent=%s attempt=%d transient %s，%.2fs 后重试",
                agent, attempt, exc, sleep_s,
            )
            await _sleep(sleep_s)
        # LLMError 子类之外的异常照常向上抛（4xx → 直接出循环）

    # 理论上不可达：上面要么 return 要么 raise
    assert last_transient is not None
    raise last_transient


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
                # 与 chat_completion 错误分类一致：5xx 视为 transient，便于上层判别
                if response.status_code >= 500:
                    raise TransientLLMError(f"API error {response.status_code}: {body}")
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
        # stream 模式下豆包侧/中间网关常抛 RemoteProtocolError 且 __str__ 为空
        # 用 type 名 + repr 保住根因，便于排查"5xxx ms 后被对端关闭"这类抖动
        raise TransientLLMError(f"Network error ({type(exc).__name__}): {exc!r}") from exc
