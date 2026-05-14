"""
LLM call logger — appends one JSON line per AI call to a .jsonl file.
"""

import json
import os
from datetime import datetime, timezone


def log_ai_call(
    *,
    log_path: str,
    agent: str,
    system_prompt: str,
    messages: list[dict],
    response: str,
    duration_ms: int | float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Append a single AI call record to *log_path* in JSONL format.

    Creates parent directories if they don't exist.
    """
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "system_prompt": system_prompt,
        "messages": messages,
        "response": response,
        "duration_ms": int(duration_ms),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
