import json
import os
import tempfile

import pytest

from app.services.llm_logger import log_ai_call


@pytest.fixture()
def log_file(tmp_path):
    return str(tmp_path / "ai_calls.jsonl")


def test_log_writes_jsonl_entry(log_file):
    log_ai_call(
        log_path=log_file,
        agent="agent_a",
        system_prompt="You are a diagnostician.",
        messages=[{"role": "user", "content": "Hello"}],
        response="Diagnosis result",
        duration_ms=123,
        prompt_tokens=10,
        completion_tokens=5,
    )
    with open(log_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["agent"] == "agent_a"
    assert entry["system_prompt"] == "You are a diagnostician."
    assert entry["messages"] == [{"role": "user", "content": "Hello"}]
    assert entry["response"] == "Diagnosis result"
    assert entry["duration_ms"] == 123
    assert entry["prompt_tokens"] == 10
    assert entry["completion_tokens"] == 5
    assert "ts" in entry


def test_log_appends_multiple_entries(log_file):
    for i in range(3):
        log_ai_call(
            log_path=log_file,
            agent="agent_b",
            system_prompt="sys",
            messages=[],
            response=f"resp {i}",
            duration_ms=i * 10,
            prompt_tokens=i,
            completion_tokens=i,
        )
    with open(log_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 3
    assert json.loads(lines[2])["response"] == "resp 2"


def test_log_creates_parent_dirs(tmp_path):
    nested = str(tmp_path / "a" / "b" / "ai_calls.jsonl")
    log_ai_call(
        log_path=nested,
        agent="test",
        system_prompt="",
        messages=[],
        response="ok",
        duration_ms=0,
        prompt_tokens=0,
        completion_tokens=0,
    )
    assert os.path.exists(nested)


def test_log_missing_tokens_defaults_to_zero(log_file):
    log_ai_call(
        log_path=log_file,
        agent="agent_a",
        system_prompt="",
        messages=[],
        response="r",
        duration_ms=0,
    )
    entry = json.loads(open(log_file, encoding="utf-8").read())
    assert entry["prompt_tokens"] == 0
    assert entry["completion_tokens"] == 0
