# 双Agent完整实现 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 LLM Agent A（诊断）+ Agent B（报告）完全替换 Python quiz_scorer，迁移到本地 Supabase CLI，加入全链路 AI 日志。

**Architecture:** `/quiz/submit` 触发 Agent A 输出结构化诊断 JSON 并存入 DB（status="analyzed"）；`/result` 触发 Agent B 读取诊断包输出报告 JSON（status="complete"）；llm_logger 记录每次 LLM 调用的完整 prompt/response/token。

**Tech Stack:** FastAPI, SQLAlchemy, httpx, respx（mock），psycopg2-binary，本地 Supabase CLI（localhost:54322 PostgreSQL + localhost:54321 REST API）

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| 修改 | `requirements.txt` |
| 修改 | `.env` / `.env.example` |
| 修改 | `.gitignore` |
| 新增 | `supabase/migrations/20260430_add_version_notes_to_questions.sql` |
| 修改 | `app/models/assessment.py` |
| 新增 | `app/services/llm_logger.py` |
| 修改 | `app/services/llm_client.py` |
| 修改 | `app/main.py` |
| 新增 | `app/services/answer_package_builder.py` |
| 新增 | `app/agents/agent_a.py` |
| 新增（重写）| `app/agents/agent_b.py` |
| 修改 | `app/api/quiz.py` |
| 修改 | `app/api/result.py` |
| 修改 | `tests/conftest.py` |
| 新增 | `tests/services/test_answer_package_builder.py` |
| 新增 | `tests/services/test_llm_logger.py` |
| 新增 | `tests/agents/test_agent_a.py` |
| 新增 | `tests/agents/test_agent_b.py` |
| 修改 | `tests/api/test_quiz.py` |
| 修改 | `tests/api/test_result.py` |
| **删除** | `app/services/quiz_scorer.py` |
| **删除** | `app/agents/agent2_analysis.py` |

---

## Task 1: 环境配置（依赖、.env、.gitignore、conftest）

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `.env`
- Modify: `.gitignore`
- Modify: `tests/conftest.py`

- [ ] **Step 1: 在 requirements.txt 加入 psycopg2-binary**

  将以下行追加到 `requirements.txt`：
  ```
  psycopg2-binary==2.9.9
  ```

- [ ] **Step 2: 安装依赖**

  ```bash
  pip install -r requirements.txt
  ```
  Expected: Successfully installed psycopg2-binary...

- [ ] **Step 3: 更新 .env.example**

  将 `DATABASE_URL` 和 Supabase 相关行替换为：
  ```
  # 本地 Supabase CLI（localhost，无需 SSL）
  DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
  SUPABASE_URL=http://127.0.0.1:54321
  SUPABASE_KEY=your-local-anon-key
  ```

- [ ] **Step 4: 更新 .env（本地开发）**

  修改 `.env` 中对应行为：
  ```
  DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
  SUPABASE_URL=http://127.0.0.1:54321
  SUPABASE_KEY=<从 supabase status 输出中复制 anon key>
  ```

  获取本地 anon key：
  ```bash
  cd love-profiler  # 确保在 supabase 项目目录
  supabase status
  ```
  从输出的 `anon key` 行复制值。

- [ ] **Step 5: 更新 .gitignore**

  追加以下行到 `.gitignore`：
  ```
  logs/
  ```

- [ ] **Step 6: 更新 tests/conftest.py，加入 SUPABASE env vars**

  在 `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` 这行下方，加入：
  ```python
  os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
  os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
  ```

- [ ] **Step 7: 验证本地 Supabase 连通**

  ```bash
  python -c "
  import psycopg2
  conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:54322/postgres')
  print('connected, version:', conn.server_version)
  conn.close()
  "
  ```
  Expected: `connected, version: 150xxx`

- [ ] **Step 8: 运行现有测试确认基线通过**

  ```bash
  pytest tests/api/test_health.py tests/api/test_auth.py -v
  ```
  Expected: 全部 PASS

- [ ] **Step 9: Commit**

  ```bash
  git add requirements.txt .env.example .gitignore tests/conftest.py
  git commit -m "chore: add psycopg2-binary, local Supabase env, logs gitignore"
  ```

---

## Task 2: Questions 表 Migration（version + notes 字段）

**Files:**
- Create: `supabase/migrations/20260430_add_version_notes_to_questions.sql`

- [ ] **Step 1: 创建 supabase/migrations 目录**

  ```bash
  mkdir -p supabase/migrations
  ```

- [ ] **Step 2: 编写 migration SQL**

  创建 `supabase/migrations/20260430_add_version_notes_to_questions.sql`：
  ```sql
  -- 向 questions 表新增 version 和 notes 字段
  -- version: 题目版本号（如 "V2"），根据用户反馈迭代时升版
  -- notes: 设计备注，记录关键限定说明，供后续根据用户反馈调整
  ALTER TABLE questions ADD COLUMN IF NOT EXISTS version TEXT;
  ALTER TABLE questions ADD COLUMN IF NOT EXISTS notes TEXT;
  ```

- [ ] **Step 3: 应用 migration**

  ```bash
  supabase db push
  ```
  Expected: 无错误输出，migration applied

- [ ] **Step 4: 验证字段已添加**

  ```bash
  psql postgresql://postgres:postgres@127.0.0.1:54322/postgres \
    -c "\d questions" | grep -E "version|notes"
  ```
  Expected: 显示 `version` 和 `notes` 列

- [ ] **Step 5: Commit**

  ```bash
  git add supabase/migrations/20260430_add_version_notes_to_questions.sql
  git commit -m "feat: add version and notes columns to questions table"
  ```

---

## Task 3: Assessment 模型更新（新增三个 JSON 字段）

**Files:**
- Modify: `app/models/assessment.py`
- Test: `tests/models/test_assessment.py`（如已存在则修改，否则新增）

- [ ] **Step 1: 写失败测试**

  创建 `tests/models/test_assessment.py`（若已存在则追加）：
  ```python
  from app.models.assessment import Assessment

  def test_assessment_has_new_json_fields(db_session):
      a = Assessment(
          user_id=1,
          session_id="sess-model-test",
          mode="quick",
          status="pending",
      )
      db_session.add(a)
      db_session.commit()
      db_session.refresh(a)

      assert a.answers_json is None
      assert a.diagnosis_json is None
      assert a.report_json is None
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/models/test_assessment.py -v
  ```
  Expected: FAIL — AttributeError: type object 'Assessment' has no attribute 'answers_json'

- [ ] **Step 3: 在 Assessment 模型中加入三个字段**

  在 `app/models/assessment.py` 的 `dimension_scores` 字段行之后加入：
  ```python
      answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
      diagnosis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
      report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/models/test_assessment.py -v
  ```
  Expected: PASS

- [ ] **Step 5: 重建本地 PostgreSQL 表**

  由于 Supabase CLI 管理 Schema，需用 SQLAlchemy 在 Postgres 上建表（仅限业务表 users/assessments/orders，不影响 questions）。启动服务会自动调用 `create_tables()`，新字段通过 `ADD COLUMN` 需要手动或先 drop：

  ```bash
  psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -c "
  ALTER TABLE assessments ADD COLUMN IF NOT EXISTS answers_json TEXT;
  ALTER TABLE assessments ADD COLUMN IF NOT EXISTS diagnosis_json TEXT;
  ALTER TABLE assessments ADD COLUMN IF NOT EXISTS report_json TEXT;
  "
  ```
  Expected: ALTER TABLE (3次)

- [ ] **Step 6: Commit**

  ```bash
  git add app/models/assessment.py tests/models/test_assessment.py
  git commit -m "feat: add answers_json/diagnosis_json/report_json to Assessment model"
  ```

---

## Task 4: llm_logger.py 实现

**Files:**
- Create: `app/services/llm_logger.py`
- Create: `tests/services/test_llm_logger.py`

- [ ] **Step 1: 写失败测试**

  创建 `tests/services/test_llm_logger.py`：
  ```python
  import json
  import os
  import tempfile
  from pathlib import Path
  from unittest.mock import patch

  import pytest

  from app.services.llm_logger import log_ai_call


  def test_log_ai_call_writes_jsonl(tmp_path):
      log_file = tmp_path / "ai_calls.jsonl"
      with patch("app.services.llm_logger._LOG_PATH", log_file):
          log_ai_call(
              call_id="test-id-123",
              call_type="agent_a",
              model="doubao-pro-32k",
              ok=True,
              elapsed_ms=1500,
              system_prompt="系统提示",
              messages=[{"role": "user", "content": "用户输入"}],
              response='{"type": "MA-CL-MH"}',
              usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
          )
      assert log_file.exists()
      record = json.loads(log_file.read_text(encoding="utf-8"))
      assert record["call_id"] == "test-id-123"
      assert record["type"] == "agent_a"
      assert record["ok"] is True
      assert record["elapsed_ms"] == 1500
      assert record["prompt_tokens"] == 100
      assert record["completion_tokens"] == 200
      assert record["total_tokens"] == 300
      assert record["system_prompt"] == "系统提示"
      assert record["response"] == '{"type": "MA-CL-MH"}'


  def test_log_ai_call_failure_record(tmp_path):
      log_file = tmp_path / "ai_calls.jsonl"
      with patch("app.services.llm_logger._LOG_PATH", log_file):
          log_ai_call(
              call_id="fail-id",
              call_type="agent_b",
              model="doubao-pro-32k",
              ok=False,
              elapsed_ms=5000,
              system_prompt="系统提示",
              messages=[],
              error="API error 429",
          )
      record = json.loads(log_file.read_text(encoding="utf-8"))
      assert record["ok"] is False
      assert record["error"] == "API error 429"
      assert "response" not in record
      assert "prompt_tokens" not in record


  def test_log_ai_call_silent_on_write_error():
      with patch("app.services.llm_logger._LOG_PATH", Path("/nonexistent/dir/ai_calls.jsonl")):
          # Must not raise
          log_ai_call(
              call_id="x",
              call_type="stream",
              model="doubao-pro-32k",
              ok=True,
              elapsed_ms=100,
              system_prompt="",
              messages=[],
          )
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/services/test_llm_logger.py -v
  ```
  Expected: FAIL — ModuleNotFoundError: No module named 'app.services.llm_logger'

- [ ] **Step 3: 实现 llm_logger.py**

  创建 `app/services/llm_logger.py`：
  ```python
  """
  LLM call logger — appends each AI API call as one JSON line to logs/ai_calls.jsonl.
  Write failures are silently ignored so the main flow is never interrupted.
  """

  import json
  from datetime import datetime, timezone
  from pathlib import Path

  _LOG_PATH = Path("logs/ai_calls.jsonl")


  def log_ai_call(
      call_id: str,
      call_type: str,
      model: str,
      ok: bool,
      elapsed_ms: int,
      system_prompt: str,
      messages: list[dict],
      response: str | None = None,
      error: str | None = None,
      usage: dict | None = None,
  ) -> None:
      """Append one AI call record to logs/ai_calls.jsonl.

      Args:
          call_id: UUID string identifying this call.
          call_type: "agent_a" | "agent_b" | "stream"
          model: LLM model name.
          ok: True if call succeeded.
          elapsed_ms: Wall-clock time in milliseconds.
          system_prompt: Full system prompt text.
          messages: Conversation messages list.
          response: Full response text (only when ok=True).
          error: Error description (only when ok=False).
          usage: Token usage dict with prompt_tokens/completion_tokens/total_tokens.
      """
      record: dict = {
          "ts": datetime.now(timezone.utc).isoformat(),
          "call_id": call_id,
          "type": call_type,
          "model": model,
          "ok": ok,
          "elapsed_ms": elapsed_ms,
          "system_prompt": system_prompt,
          "messages": messages,
      }
      if ok and response is not None:
          record["response"] = response
      if not ok and error is not None:
          record["error"] = error
      if usage:
          record["prompt_tokens"] = usage.get("prompt_tokens")
          record["completion_tokens"] = usage.get("completion_tokens")
          record["total_tokens"] = usage.get("total_tokens")

      try:
          _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
          with _LOG_PATH.open("a", encoding="utf-8") as f:
              f.write(json.dumps(record, ensure_ascii=False) + "\n")
      except Exception:
          pass
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/services/test_llm_logger.py -v
  ```
  Expected: 3 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/services/llm_logger.py tests/services/test_llm_logger.py
  git commit -m "feat: add llm_logger for full AI call audit trail"
  ```

---

## Task 5: llm_client.py 埋点（计时 + token + 日志）

**Files:**
- Modify: `app/services/llm_client.py`
- Test: `tests/services/test_llm_client.py`（新增或追加）

- [ ] **Step 1: 写失败测试**

  创建 `tests/services/test_llm_client.py`：
  ```python
  import json
  from unittest.mock import MagicMock, patch

  import httpx
  import pytest
  import respx

  from app.services.llm_client import LLMError, chat_completion, stream_chat_completion

  DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"


  @pytest.mark.asyncio
  async def test_chat_completion_calls_log_ai_call_on_success():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": "回复内容"}}],
                      "usage": {
                          "prompt_tokens": 10,
                          "completion_tokens": 5,
                          "total_tokens": 15,
                      },
                  },
              )
          )
          with patch("app.services.llm_client.log_ai_call") as mock_log:
              result = await chat_completion("系统提示", [{"role": "user", "content": "你好"}])

      assert result == "回复内容"
      mock_log.assert_called_once()
      kwargs = mock_log.call_args.kwargs
      assert kwargs["ok"] is True
      assert kwargs["call_type"] == "completion"
      assert kwargs["usage"]["prompt_tokens"] == 10
      assert kwargs["response"] == "回复内容"
      assert kwargs["elapsed_ms"] >= 0


  @pytest.mark.asyncio
  async def test_chat_completion_calls_log_ai_call_on_failure():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(return_value=httpx.Response(500))
          with patch("app.services.llm_client.log_ai_call") as mock_log:
              with pytest.raises(LLMError):
                  await chat_completion("系统提示", [])

      mock_log.assert_called_once()
      kwargs = mock_log.call_args.kwargs
      assert kwargs["ok"] is False
      assert "error" in kwargs


  @pytest.mark.asyncio
  async def test_stream_chat_completion_accumulates_and_logs():
      chunks = [
          'data: {"choices":[{"delta":{"content":"你"}}]}\n',
          'data: {"choices":[{"delta":{"content":"好"}}]}\n',
          "data: [DONE]\n",
      ]

      async def mock_aiter_lines():
          for chunk in chunks:
              yield chunk.strip()

      mock_response = MagicMock()
      mock_response.raise_for_status = MagicMock()
      mock_response.aiter_lines = mock_aiter_lines

      with patch("app.services.llm_client.log_ai_call") as mock_log:
          with patch.object(
              httpx.AsyncClient,
              "stream",
              return_value=MagicMock(
                  __aenter__=lambda s, *a, **kw: mock_response,
                  __aexit__=MagicMock(return_value=False),
              ),
          ):
              collected = []
              async for chunk in stream_chat_completion("系统提示", []):
                  collected.append(chunk)

      assert "".join(collected) == "你好"
      mock_log.assert_called_once()
      kwargs = mock_log.call_args.kwargs
      assert kwargs["ok"] is True
      assert kwargs["response"] == "你好"
      assert kwargs["call_type"] == "stream"
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/services/test_llm_client.py -v
  ```
  Expected: FAIL — AttributeError 或 AssertionError（log_ai_call not called）

- [ ] **Step 3: 重写 llm_client.py 加入埋点**

  完整替换 `app/services/llm_client.py`：
  ```python
  """
  LLM client — async wrapper around the Doubao (豆包) chat completion API.
  """

  import json
  import os
  import time
  import uuid
  from collections.abc import AsyncIterator

  import httpx

  from app.services.llm_logger import log_ai_call

  DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
  _TIMEOUT_SECONDS = 60

  _client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)


  class LLMError(Exception):
      """Raised when the LLM API call fails for any reason."""


  async def chat_completion(
      system_prompt: str,
      messages: list[dict],
  ) -> str:
      """Send a chat completion request and return the assistant reply text."""
      api_key = os.environ["DOUBAO_API_KEY"]
      model = os.environ["DOUBAO_MODEL"]
      call_id = str(uuid.uuid4())
      start = time.perf_counter()

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
          elapsed_ms = int((time.perf_counter() - start) * 1000)
          log_ai_call(
              call_id=call_id,
              call_type="completion",
              model=model,
              ok=False,
              elapsed_ms=elapsed_ms,
              system_prompt=system_prompt,
              messages=messages,
              error=f"API error {exc.response.status_code}",
          )
          raise LLMError(f"API error {exc.response.status_code}") from exc
      except httpx.HTTPError as exc:
          elapsed_ms = int((time.perf_counter() - start) * 1000)
          log_ai_call(
              call_id=call_id,
              call_type="completion",
              model=model,
              ok=False,
              elapsed_ms=elapsed_ms,
              system_prompt=system_prompt,
              messages=messages,
              error=f"Network error: {exc}",
          )
          raise LLMError(f"Network error: {exc}") from exc

      try:
          reply = response.json()["choices"][0]["message"]["content"]
      except (KeyError, IndexError, TypeError) as exc:
          raise LLMError(f"Unexpected response shape: {response.text[:200]}") from exc

      elapsed_ms = int((time.perf_counter() - start) * 1000)
      usage = response.json().get("usage")
      log_ai_call(
          call_id=call_id,
          call_type="completion",
          model=model,
          ok=True,
          elapsed_ms=elapsed_ms,
          system_prompt=system_prompt,
          messages=messages,
          response=reply,
          usage=usage,
      )
      return reply


  async def stream_chat_completion(
      system_prompt: str,
      messages: list[dict],
  ) -> AsyncIterator[str]:
      """Stream chat completion, yielding text chunks as the LLM generates them."""
      api_key = os.environ["DOUBAO_API_KEY"]
      model = os.environ["DOUBAO_MODEL"]
      call_id = str(uuid.uuid4())
      start = time.perf_counter()
      accumulated: list[str] = []

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
                      break
                  try:
                      chunk = json.loads(data)
                      content = chunk["choices"][0]["delta"].get("content", "")
                      if content:
                          accumulated.append(content)
                          yield content
                  except (json.JSONDecodeError, KeyError, IndexError):
                      continue

          elapsed_ms = int((time.perf_counter() - start) * 1000)
          log_ai_call(
              call_id=call_id,
              call_type="stream",
              model=model,
              ok=True,
              elapsed_ms=elapsed_ms,
              system_prompt=system_prompt,
              messages=messages,
              response="".join(accumulated),
          )
      except httpx.HTTPStatusError as exc:
          elapsed_ms = int((time.perf_counter() - start) * 1000)
          log_ai_call(
              call_id=call_id,
              call_type="stream",
              model=model,
              ok=False,
              elapsed_ms=elapsed_ms,
              system_prompt=system_prompt,
              messages=messages,
              error=f"API error {exc.response.status_code}",
          )
          raise LLMError(f"API error {exc.response.status_code}") from exc
      except httpx.HTTPError as exc:
          elapsed_ms = int((time.perf_counter() - start) * 1000)
          log_ai_call(
              call_id=call_id,
              call_type="stream",
              model=model,
              ok=False,
              elapsed_ms=elapsed_ms,
              system_prompt=system_prompt,
              messages=messages,
              error=f"Network error: {exc}",
          )
          raise LLMError(f"Network error: {exc}") from exc
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/services/test_llm_client.py -v
  ```
  Expected: 3 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/services/llm_client.py tests/services/test_llm_client.py
  git commit -m "feat: instrument llm_client with timing and full call logging"
  ```

---

## Task 6: main.py 文件日志（RotatingFileHandler）

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 在 main.py 加入 _setup_file_logging()**

  在 `app/main.py` 的 import 区加入：
  ```python
  from logging.handlers import RotatingFileHandler
  from pathlib import Path
  ```

  在 `logger = logging.getLogger(__name__)` 行下方（`from fastapi import FastAPI` 之前）加入：
  ```python
  def _setup_file_logging() -> None:
      Path("logs").mkdir(exist_ok=True)
      handler = RotatingFileHandler(
          "logs/app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
      )
      handler.setFormatter(
          logging.Formatter(
              "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
          )
      )
      logging.getLogger().addHandler(handler)
  ```

  在 `lifespan` 函数中，`create_tables()` 行之前调用：
  ```python
  _setup_file_logging()
  ```

- [ ] **Step 2: 验证启动时创建日志文件**

  ```bash
  uvicorn app.main:app --port 8001 &
  sleep 2
  ls logs/
  kill %1
  ```
  Expected: `app.log` 出现在 `logs/` 目录

- [ ] **Step 3: Commit**

  ```bash
  git add app/main.py
  git commit -m "feat: add rotating file log handler to app startup"
  ```

---

## Task 7: answer_package_builder.py 实现

**Files:**
- Create: `app/services/answer_package_builder.py`
- Create: `tests/services/test_answer_package_builder.py`

- [ ] **Step 1: 写失败测试**

  创建 `tests/services/test_answer_package_builder.py`：
  ```python
  import pytest
  from app.services.answer_package_builder import _parse_score_entry, build_answer_package


  # ---------------------------------------------------------------------------
  # _parse_score_entry 单元测试
  # ---------------------------------------------------------------------------

  def test_parse_positive_numeric():
      value, meta = _parse_score_entry("+2")
      assert value == 2
      assert meta == {}


  def test_parse_negative_numeric():
      value, meta = _parse_score_entry("-1")
      assert value == -1
      assert meta == {}


  def test_parse_love_language():
      value, meta = _parse_score_entry("T1+2")
      assert value == 2
      assert meta == {"type": "T1"}


  def test_parse_love_language_t3():
      value, meta = _parse_score_entry("T3+1")
      assert value == 1
      assert meta == {"type": "T3"}


  def test_parse_empty_returns_zero():
      value, meta = _parse_score_entry("")
      assert value == 0
      assert meta == {}


  def test_parse_none_returns_zero():
      value, meta = _parse_score_entry(None)
      assert value == 0
      assert meta == {}


  # ---------------------------------------------------------------------------
  # build_answer_package 集成测试
  # ---------------------------------------------------------------------------

  MOCK_QUESTIONS = [
      {
          "question_id": "D1-Q01",
          "dimension": "依恋",
          "signal_code": "S1",
          "signal_name": "不确定性解读",
          "question_type": "核心题",
          "option_a": "选项A", "score_a": "+2",
          "option_b": "选项B", "score_b": "+1",
          "option_c": "选项C", "score_c": "-1",
          "option_d": "选项D", "score_d": "-2",
          "option_e": None, "score_e": None,
          "version": "V2",
          "notes": None,
      },
      {
          "question_id": "D4-Q01",
          "dimension": "情感",
          "signal_code": "T1",
          "signal_name": "言语肯定",
          "question_type": "核心题",
          "option_a": "选项A", "score_a": "T1+2",
          "option_b": "选项B", "score_b": "T2+1",
          "option_c": "选项C", "score_c": "T3+1",
          "option_d": "选项D", "score_d": "T4+1",
          "option_e": "选项E", "score_e": "T5+1",
          "version": "V2",
          "notes": None,
      },
  ]


  def test_build_answer_package_basic():
      answers = [{"question_id": "D1-Q01", "chosen_option": "a"}]
      pkg = build_answer_package("sess-001", answers, MOCK_QUESTIONS)

      assert pkg["session_id"] == "sess-001"
      assert pkg["question_set_version"] == "V2"
      assert len(pkg["answers"]) == 1

      item = pkg["answers"][0]
      assert item["question_code"] == "D1-Q01"
      assert item["dimension_code"] == "D1"
      assert item["signal_code"] == "S1"
      assert item["signal_name"] == "不确定性解读"
      assert item["question_type"] == "核心题"
      assert item["selected_option"] == "A"
      assert item["score_value"] == 2
      assert item["score_meta"] == {}


  def test_build_answer_package_love_language():
      answers = [{"question_id": "D4-Q01", "chosen_option": "a"}]
      pkg = build_answer_package("sess-002", answers, MOCK_QUESTIONS)

      item = pkg["answers"][0]
      assert item["score_value"] == 2
      assert item["score_meta"] == {"type": "T1"}


  def test_build_answer_package_unknown_question_skipped():
      answers = [{"question_id": "UNKNOWN", "chosen_option": "a"}]
      pkg = build_answer_package("sess-003", answers, MOCK_QUESTIONS)
      assert len(pkg["answers"]) == 0


  def test_build_answer_package_version_from_questions():
      answers = [{"question_id": "D1-Q01", "chosen_option": "b"}]
      pkg = build_answer_package("sess-004", answers, MOCK_QUESTIONS)
      assert pkg["question_set_version"] == "V2"


  def test_build_answer_package_no_version_defaults_unknown():
      questions_no_version = [{**MOCK_QUESTIONS[0], "version": None}]
      answers = [{"question_id": "D1-Q01", "chosen_option": "a"}]
      pkg = build_answer_package("sess-005", answers, questions_no_version)
      assert pkg["question_set_version"] == "unknown"


  # ---------------------------------------------------------------------------
  # D3-Q06 追逃亚型特殊规则（规则文档 3.2 节）
  # ---------------------------------------------------------------------------

  D3Q06_QUESTION = {
      "question_id": "D3-Q06",
      "dimension": "冲突",
      "signal_code": "S5",
      "signal_name": "追逃模式",
      "question_type": "核心题",
      "option_a": "觉察打破循环", "score_a": "+2",
      "option_b": "无固定模式",   "score_b": "+1",
      "option_c": "追的角色",     "score_c": "-2",
      "option_d": "逃的角色",     "score_d": "-2",
      "option_e": None, "score_e": None,
      "version": "V2", "notes": None,
  }


  def test_d3_q06_option_c_marks_pursue():
      answers = [{"question_id": "D3-Q06", "chosen_option": "c"}]
      pkg = build_answer_package("sess-d3c", answers, [D3Q06_QUESTION])
      item = pkg["answers"][0]
      assert item["score_value"] == -2
      assert item["score_meta"] == {"pursue_avoid": "pursue"}


  def test_d3_q06_option_d_marks_avoid():
      answers = [{"question_id": "D3-Q06", "chosen_option": "d"}]
      pkg = build_answer_package("sess-d3d", answers, [D3Q06_QUESTION])
      item = pkg["answers"][0]
      assert item["score_value"] == -2
      assert item["score_meta"] == {"pursue_avoid": "avoid"}


  def test_d3_q06_option_a_no_subtype():
      answers = [{"question_id": "D3-Q06", "chosen_option": "a"}]
      pkg = build_answer_package("sess-d3a", answers, [D3Q06_QUESTION])
      item = pkg["answers"][0]
      assert item["score_value"] == 2
      assert item["score_meta"] == {}
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/services/test_answer_package_builder.py -v
  ```
  Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 answer_package_builder.py**

  创建 `app/services/answer_package_builder.py`：
  ```python
  """
  Answer package builder — assembles structured answer package for Agent A.
  Migrates score parsing from quiz_scorer._parse_score with adjusted output format.

  Special rule: D3-Q06 options C/D carry pursue_avoid_subtype in score_meta.
  See docs/superpowers/specs/2026-04-30-scoring-rules.md section 3.2.
  """

  import re

  # D3-Q06 特殊追逃亚型映射（C=追, D=逃），按规则文档 3.2 节
  _D3_Q06_PURSUE_AVOID = {
      "c": "pursue",
      "d": "avoid",
  }


  def _parse_score_entry(score_str: str | None) -> tuple[int, dict]:
      """Parse a score string into (score_value, score_meta).

      '+2' / '-1'  →  (2, {})  /  (-1, {})
      'T1+2'       →  (2, {"type": "T1"})
      None / ''    →  (0, {})
      """
      if not score_str:
          return 0, {}
      m = re.match(r"(T\d)\+?(-?\d+)", score_str)
      if m:
          return int(m.group(2)), {"type": m.group(1)}
      try:
          return int(score_str.replace("+", "")), {}
      except ValueError:
          return 0, {}


  def build_answer_package(
      session_id: str,
      answers: list[dict],
      questions: list[dict],
  ) -> dict:
      """Build a structured answer package for Agent A consumption.

      Args:
          session_id: UUID string from the current session.
          answers: [{"question_id": str, "chosen_option": str}] — chosen_option is a-e.
          questions: Full question list from Supabase (includes score_a/b/c/d/e, version, etc.)

      Returns:
          Answer package dict with session_id, question_set_version, and answers list.
      """
      q_map = {q["question_id"]: q for q in questions}

      version = "unknown"
      for q in questions:
          v = q.get("version")
          if v:
              version = v
              break

      items = []
      for answer in answers:
          qid = answer["question_id"]
          if qid not in q_map:
              continue
          q = q_map[qid]
          opt = answer["chosen_option"].lower()
          score_str = q.get(f"score_{opt}") or ""
          score_value, score_meta = _parse_score_entry(score_str)
          dimension_code = qid[:2]  # "D1-Q01" → "D1"

          # D3-Q06 特殊规则：C/D 选项额外标记追逃亚型
          if qid == "D3-Q06" and opt in _D3_Q06_PURSUE_AVOID:
              score_meta = {"pursue_avoid": _D3_Q06_PURSUE_AVOID[opt]}

          items.append({
              "question_code": qid,
              "dimension_code": dimension_code,
              "signal_code": q.get("signal_code", ""),
              "signal_name": q.get("signal_name", ""),
              "question_type": q.get("question_type", ""),
              "selected_option": answer["chosen_option"].upper(),
              "score_value": score_value,
              "score_meta": score_meta,
          })

      return {
          "session_id": session_id,
          "question_set_version": version,
          "answers": items,
      }
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/services/test_answer_package_builder.py -v
  ```
  Expected: 10 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/services/answer_package_builder.py tests/services/test_answer_package_builder.py
  git commit -m "feat: add answer_package_builder with score parsing for Agent A"
  ```

---

## Task 8: agent_a.py 实现

**Files:**
- Create: `app/agents/agent_a.py`
- Create: `tests/agents/test_agent_a.py`

> **⚠️ 关键操作（此步骤需要手动操作）：** Agent A 的 system prompt 内容在 PDF《双Agent Prompts v0.1》中的 "Agent A System Prompt" 部分。在 Step 3 中，将该 PDF 中的完整 Agent A system prompt 粘贴到 `AGENT_A_SYSTEM_PROMPT` 常量中。
>
> **Agent A system prompt 必须包含的计算规则（见 `docs/superpowers/specs/2026-04-30-scoring-rules.md`）：**
> - **强度型打分（D1/D2/D3）：** A=+2, B=+1, C=-1, D=-2，6 题累加，映射 5 类标签（≥6/3~5/-2~2/-5~-3/≤-6）
> - **D3-Q06 追逃亚型：** C(-2)标记 pursue_avoid_role="pursue"，D(-2)标记 pursue_avoid_role="avoid"（答题包中 score_meta 已携带，Agent A 直接读取）
> - **D4 类型偏好型：** 按选项指向 T1-T5 累加原始分，**归一化**（T1÷9, T2÷8, T3÷6, T4÷9, T5÷8），取 top2；D4-Q01 主动选 vs 归一化 top1 做一致性检查
> - **D5 双子面型：** S1(Q01-03)和 S2(Q04-06)各自累加，>3=高直接/高分享，-3~3=中，<-3=高含蓄/低分享，组合成 2x2 象限
> - **三层跨维度审查全部执行：** 维度内（D1-S4/D2-S1/D3-S1）+ 维度间（D2D3/D1D5/D2D5）+ 全局标记（4 个）
> - **16 类分型：** 依恋(S/MS/MA/A) × 边界(CL/BL) × 冲突(H/P)，type_code 格式如 "MA-CL-MH"

- [ ] **Step 1: 写失败测试**

  创建 `tests/agents/test_agent_a.py`：
  ```python
  import json
  from unittest.mock import AsyncMock, patch

  import httpx
  import pytest
  import respx

  from app.agents.agent_a import AgentAError, run

  DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

  VALID_DIAGNOSIS = {
      "dimension_scores": {
          "D1": {"score": 8, "level": "高"},
          "D2": {"score": 6, "level": "中"},
          "D3": {"score": 4, "level": "低"},
          "D4": {"primary": "T1", "scores": {"T1": 8, "T2": 4, "T3": 2, "T4": 2, "T5": 2}},
          "D5": {"directness": 6, "sharing": 4},
      },
      "cross_validation": ["验证1", "验证2"],
      "global_flags": {"flag1": True},
      "personality_type": "MA-CL-MH",
      "diagnosis_insights": {"insight": "示例洞察"},
  }

  ANSWER_PACKAGE = {
      "session_id": "test-session",
      "question_set_version": "V2",
      "answers": [],
  }


  @pytest.mark.asyncio
  async def test_agent_a_success_returns_dict():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": json.dumps(VALID_DIAGNOSIS)}}],
                      "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
                  },
              )
          )
          result = await run(ANSWER_PACKAGE)

      assert result["personality_type"] == "MA-CL-MH"
      assert "dimension_scores" in result


  @pytest.mark.asyncio
  async def test_agent_a_json_with_preamble_still_parses():
      content = "好的，以下是诊断结果：\n" + json.dumps(VALID_DIAGNOSIS)
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": content}}],
                      "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
                  },
              )
          )
          result = await run(ANSWER_PACKAGE)

      assert result["personality_type"] == "MA-CL-MH"


  @pytest.mark.asyncio
  async def test_agent_a_invalid_json_all_retries_raises_agent_a_error():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": "这不是JSON"}}],
                      "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                  },
              )
          )
          with pytest.raises(AgentAError):
              await run(ANSWER_PACKAGE)


  @pytest.mark.asyncio
  async def test_agent_a_retries_on_json_failure():
      responses = [
          httpx.Response(
              200,
              json={
                  "choices": [{"message": {"content": "invalid"}}],
                  "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
              },
          ),
          httpx.Response(
              200,
              json={
                  "choices": [{"message": {"content": json.dumps(VALID_DIAGNOSIS)}}],
                  "usage": {"prompt_tokens": 100, "completion_tokens": 300, "total_tokens": 400},
              },
          ),
      ]
      call_count = 0

      def side_effect(request):
          nonlocal call_count
          resp = responses[min(call_count, len(responses) - 1)]
          call_count += 1
          return resp

      with respx.mock:
          respx.post(DOUBAO_URL).mock(side_effect=side_effect)
          result = await run(ANSWER_PACKAGE)

      assert call_count == 2
      assert result["personality_type"] == "MA-CL-MH"
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/agents/test_agent_a.py -v
  ```
  Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 agent_a.py（含 system prompt）**

  创建 `app/agents/agent_a.py`。

  **重要：** 将下方 `AGENT_A_SYSTEM_PROMPT` 的占位注释替换为 PDF《双Agent Prompts v0.1》中 Agent A 的完整 System Prompt：

  ```python
  """
  Agent A — processes answer package → structured diagnosis JSON.
  Temperature: 0.1 (set via model default or future config).
  """

  import json
  import re

  from app.services.llm_client import LLMError, chat_completion

  # 从 PDF《双Agent Prompts v0.1》— Agent A System Prompt 部分粘贴完整内容
  AGENT_A_SYSTEM_PROMPT = """
  [在此粘贴 PDF《双Agent Prompts v0.1》中 Agent A 的完整 System Prompt]
  """


  class AgentAError(Exception):
      """Raised when Agent A fails to return valid JSON after all retries."""


  def _extract_json(text: str) -> dict | None:
      """Extract the first {...} JSON object from text, ignoring preamble text."""
      start = text.find("{")
      end = text.rfind("}") + 1
      if start == -1 or end <= start:
          return None
      try:
          return json.loads(text[start:end])
      except json.JSONDecodeError:
          return None


  async def run(answer_package: dict) -> dict:
      """Run Agent A: answer package → structured diagnosis dict.

      Args:
          answer_package: Built by answer_package_builder.build_answer_package().

      Returns:
          Diagnosis dict (dimension_scores, cross_validation, global_flags,
          personality_type, diagnosis_insights).

      Raises:
          AgentAError: If JSON parsing fails after 3 attempts.
          LLMError: If the API call itself fails (network/HTTP error).
      """
      base_content = json.dumps(answer_package, ensure_ascii=False)
      retry_suffix = "\n\n严格要求：第一个字符必须是{，最后一个字符必须是}"

      for attempt in range(3):
          content = base_content if attempt == 0 else base_content + retry_suffix
          raw = await chat_completion(
              AGENT_A_SYSTEM_PROMPT,
              [{"role": "user", "content": content}],
          )
          result = _extract_json(raw)
          if result is not None:
              return result

      raise AgentAError("Agent A failed to return valid JSON after 3 attempts")
  ```

  **粘贴 System Prompt 后**，去掉 `[在此粘贴...]` 占位文字。

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/agents/test_agent_a.py -v
  ```
  Expected: 4 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/agents/agent_a.py tests/agents/test_agent_a.py
  git commit -m "feat: add Agent A with LLM diagnosis and JSON retry logic"
  ```

---

## Task 9: agent_b.py 重写

**Files:**
- Create (rewrite): `app/agents/agent_b.py`
- Create: `tests/agents/test_agent_b.py`

> **⚠️ 关键操作：** Agent B 的 system prompt 在 PDF《双Agent Prompts v0.1》中的 "Agent B System Prompt" 部分。在 Step 3 中粘贴完整内容。

- [ ] **Step 1: 写失败测试**

  创建 `tests/agents/test_agent_b.py`：
  ```python
  import json
  from unittest.mock import AsyncMock, patch

  import httpx
  import pytest
  import respx

  from app.agents.agent_b import AgentBError, run

  DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

  VALID_REPORT = {
      "report_text": "你是一个安全型依恋风格的人，在感情中表现出高度的信任感与安全感。",
      "sections": {
          "type_name": "MA-CL-MH",
          "attachment_analysis": "依恋分析内容",
          "boundary_conflict": "边界冲突分析",
          "love_language": "爱的语言解读",
          "communication_style": "沟通风格",
          "growth_suggestions": "成长建议",
      },
  }

  MOCK_DIAGNOSIS = {
      "personality_type": "MA-CL-MH",
      "dimension_scores": {},
      "diagnosis_insights": {},
  }


  @pytest.mark.asyncio
  async def test_agent_b_success_returns_dict():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": json.dumps(VALID_REPORT)}}],
                      "usage": {"prompt_tokens": 800, "completion_tokens": 500, "total_tokens": 1300},
                  },
              )
          )
          result = await run(MOCK_DIAGNOSIS)

      assert result["report_text"] == VALID_REPORT["report_text"]
      assert result["sections"]["type_name"] == "MA-CL-MH"


  @pytest.mark.asyncio
  async def test_agent_b_invalid_json_raises_agent_b_error():
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": "这不是有效JSON"}}],
                      "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                  },
              )
          )
          with pytest.raises(AgentBError):
              await run(MOCK_DIAGNOSIS)


  @pytest.mark.asyncio
  async def test_agent_b_json_with_preamble_still_parses():
      content = "以下是报告：\n" + json.dumps(VALID_REPORT)
      with respx.mock:
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": content}}],
                      "usage": {"prompt_tokens": 800, "completion_tokens": 500, "total_tokens": 1300},
                  },
              )
          )
          result = await run(MOCK_DIAGNOSIS)

      assert result["sections"]["type_name"] == "MA-CL-MH"
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/agents/test_agent_b.py -v
  ```
  Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 agent_b.py**

  创建 `app/agents/agent_b.py`。**将 Agent B system prompt 从 PDF 粘贴到 `AGENT_B_SYSTEM_PROMPT`：**

  ```python
  """
  Agent B — processes Agent A diagnosis dict → narrative report JSON.
  Temperature: 0.6 (set via model default or future config).
  """

  import json

  from app.services.llm_client import LLMError, chat_completion

  # 从 PDF《双Agent Prompts v0.1》— Agent B System Prompt 部分粘贴完整内容
  AGENT_B_SYSTEM_PROMPT = """
  [在此粘贴 PDF《双Agent Prompts v0.1》中 Agent B 的完整 System Prompt]
  """


  class AgentBError(Exception):
      """Raised when Agent B fails to return valid JSON after all retries."""


  def _extract_json(text: str) -> dict | None:
      """Extract the first {...} JSON object from text, ignoring preamble."""
      start = text.find("{")
      end = text.rfind("}") + 1
      if start == -1 or end <= start:
          return None
      try:
          return json.loads(text[start:end])
      except json.JSONDecodeError:
          return None


  async def run(diagnosis: dict) -> dict:
      """Run Agent B: diagnosis dict → report dict.

      Args:
          diagnosis: Agent A output dict (dimension_scores, personality_type, etc.)

      Returns:
          Report dict with keys: report_text, sections (including type_name).

      Raises:
          AgentBError: If JSON parsing fails after 3 attempts.
          LLMError: If the API call itself fails.
      """
      base_content = json.dumps(diagnosis, ensure_ascii=False)
      retry_suffix = "\n\n严格要求：第一个字符必须是{，最后一个字符必须是}"

      for attempt in range(3):
          content = base_content if attempt == 0 else base_content + retry_suffix
          raw = await chat_completion(
              AGENT_B_SYSTEM_PROMPT,
              [{"role": "user", "content": content}],
          )
          result = _extract_json(raw)
          if result is not None:
              return result

      raise AgentBError("Agent B failed to return valid JSON after 3 attempts")
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/agents/test_agent_b.py -v
  ```
  Expected: 3 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/agents/agent_b.py tests/agents/test_agent_b.py
  git commit -m "feat: rewrite agent_b to consume Agent A diagnosis JSON"
  ```

---

## Task 10: /quiz/submit 改造

**Files:**
- Modify: `app/api/quiz.py`
- Modify: `tests/api/test_quiz.py`

- [ ] **Step 1: 更新 test_quiz.py 中的 mock URL 和期望值**

  打开 `tests/api/test_quiz.py`，做以下修改：

  1. 将顶部常量改为：
  ```python
  SUPABASE_URL = "http://127.0.0.1:54321"
  ```

  2. 更新 `MOCK_QUESTIONS` 增加新字段：
  ```python
  MOCK_QUESTIONS = [
      {
          "question_id": f"D1-Q{i:02d}",
          "dimension": "依恋",
          "signal_code": "S1",
          "signal_name": "不确定性解读",
          "question_type": "核心题",
          "stem": f"题干{i}",
          "sort_order": i,
          "option_a": "选项A", "score_a": "+2",
          "option_b": "选项B", "score_b": "+1",
          "option_c": "选项C", "score_c": "-1",
          "option_d": "选项D", "score_d": "-2",
          "option_e": None, "score_e": None,
          "version": "V2",
          "notes": None,
      }
      for i in range(1, 31)
  ]
  ```

  3. 更新 `test_quiz_submit_computes_scores` 测试（完整替换）：
  ```python
  def test_quiz_submit_calls_agent_a(client, auth_headers, db_session):
      DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
      import json as _json
      MOCK_DIAGNOSIS = {
          "dimension_scores": {"D1": {"score": 8}},
          "personality_type": "MA-CL-MH",
          "diagnosis_insights": {},
          "cross_validation": [],
          "global_flags": {},
      }

      with respx.mock:
          respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
              return_value=httpx.Response(200, json=MOCK_QUESTIONS)
          )
          start = client.post("/quiz/start", headers=auth_headers)
      assert start.status_code == 200
      session_id = start.json()["session_id"]

      answers = [
          {"question_id": f"D1-Q{i:02d}", "chosen_option": "a"}
          for i in range(1, 31)
      ]
      with respx.mock:
          respx.get(f"{SUPABASE_URL}/rest/v1/questions").mock(
              return_value=httpx.Response(200, json=MOCK_QUESTIONS)
          )
          respx.post(DOUBAO_URL).mock(
              return_value=httpx.Response(
                  200,
                  json={
                      "choices": [{"message": {"content": _json.dumps(MOCK_DIAGNOSIS)}}],
                      "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
                  },
              )
          )
          resp = client.post(
              "/quiz/submit",
              json={"session_id": session_id, "answers": answers},
              headers=auth_headers,
          )
      assert resp.status_code == 200
      assert resp.json()["status"] == "analyzed"

      from app.models.assessment import Assessment
      db_session.expire_all()
      assessment = db_session.query(Assessment).filter(
          Assessment.session_id == session_id
      ).first()
      assert assessment is not None
      assert assessment.status == "analyzed"
      assert assessment.mode == "quick"
      assert assessment.diagnosis_json is not None
      diagnosis = _json.loads(assessment.diagnosis_json)
      assert diagnosis["personality_type"] == "MA-CL-MH"
  ```

- [ ] **Step 2: 运行测试确认失败（期望新的行为但代码未改）**

  ```bash
  pytest tests/api/test_quiz.py -v
  ```
  Expected: `test_quiz_submit_calls_agent_a` FAIL（因为 quiz.py 还未修改）

- [ ] **Step 3: 重写 app/api/quiz.py**

  完整替换 `app/api/quiz.py`：
  ```python
  """
  Quiz API — serve questions from Supabase and submit answers to Agent A.
  POST /quiz/start   →  { session_id, assessment_id, questions: [...] }
  POST /quiz/submit  →  { assessment_id, status: "analyzed" }
  """

  import json
  import logging
  import uuid

  from fastapi import APIRouter, Depends, HTTPException, Request, status
  from pydantic import BaseModel
  from sqlalchemy.orm import Session

  from app.agents.agent_a import AgentAError, run as agent_a_run
  from app.database import get_db
  from app.limiter import limiter
  from app.middleware.auth import get_current_user_id
  from app.models.assessment import Assessment
  from app.services.answer_package_builder import build_answer_package
  from app.services.supabase_client import fetch_questions

  logger = logging.getLogger(__name__)
  router = APIRouter(prefix="/quiz", tags=["quiz"])


  class StartResponse(BaseModel):
      session_id: str
      assessment_id: int
      questions: list[dict]


  class AnswerItem(BaseModel):
      question_id: str
      chosen_option: str


  class SubmitRequest(BaseModel):
      session_id: str
      answers: list[AnswerItem]


  class SubmitResponse(BaseModel):
      assessment_id: int
      status: str


  @router.post("/start", response_model=StartResponse)
  @limiter.limit("5/minute")
  async def quiz_start(
      request: Request,
      user_id: int = Depends(get_current_user_id),
      db: Session = Depends(get_db),
  ) -> StartResponse:
      """Create a quiz assessment and return all 30 questions."""
      questions = await fetch_questions()
      session_id = str(uuid.uuid4())
      assessment = Assessment(
          user_id=user_id,
          session_id=session_id,
          mode="quick",
          status="pending",
      )
      db.add(assessment)
      db.commit()
      db.refresh(assessment)
      logger.info("[/quiz/start] user_id=%s assessment_id=%s", user_id, assessment.id)
      return StartResponse(
          session_id=session_id,
          assessment_id=assessment.id,
          questions=questions,
      )


  @router.post("/submit", response_model=SubmitResponse)
  @limiter.limit("5/minute")
  async def quiz_submit(
      request: Request,
      body: SubmitRequest,
      user_id: int = Depends(get_current_user_id),
      db: Session = Depends(get_db),
  ) -> SubmitResponse:
      """Submit quiz answers, run Agent A diagnosis, store diagnosis JSON."""
      assessment = (
          db.query(Assessment)
          .filter(Assessment.session_id == body.session_id, Assessment.user_id == user_id)
          .first()
      )
      if assessment is None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

      questions = await fetch_questions()
      answers = [a.model_dump() for a in body.answers]
      answer_package = build_answer_package(body.session_id, answers, questions)

      assessment.answers_json = json.dumps(answers, ensure_ascii=False)

      try:
          diagnosis = await agent_a_run(answer_package)
      except AgentAError as exc:
          assessment.status = "failed"
          db.commit()
          logger.error("[/quiz/submit] Agent A failed: %s", exc)
          raise HTTPException(
              status_code=status.HTTP_502_BAD_GATEWAY,
              detail="诊断服务暂时不可用，请稍后再试。",
          ) from exc

      assessment.diagnosis_json = json.dumps(diagnosis, ensure_ascii=False)
      assessment.status = "analyzed"
      db.commit()
      logger.info("[/quiz/submit] assessment_id=%s status=analyzed", assessment.id)
      return SubmitResponse(assessment_id=assessment.id, status="analyzed")
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/api/test_quiz.py -v
  ```
  Expected: 3 PASS（start + submit_calls_agent_a + wrong_session_404）

- [ ] **Step 5: Commit**

  ```bash
  git add app/api/quiz.py tests/api/test_quiz.py
  git commit -m "feat: rewrite /quiz/submit to call Agent A and store diagnosis_json"
  ```

---

## Task 11: /result 改造

**Files:**
- Modify: `app/api/result.py`
- Modify: `tests/api/test_result.py`

- [ ] **Step 1: 更新 tests/api/test_result.py**

  完整替换 `tests/api/test_result.py`：
  ```python
  """
  Tests for POST /result — personality report generation endpoint.
  """

  import json
  from unittest.mock import AsyncMock, patch

  from app.models.assessment import Assessment
  from app.models.user import User

  DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

  MOCK_DIAGNOSIS = {
      "personality_type": "MA-CL-MH",
      "dimension_scores": {"D1": {"score": 8}},
      "diagnosis_insights": {},
      "cross_validation": [],
      "global_flags": {},
  }

  MOCK_REPORT = {
      "report_text": "你是一个情感稳定、善于沟通的伴侣，属于安全型依恋风格。",
      "sections": {
          "type_name": "MA-CL-MH",
          "attachment_analysis": "依恋分析",
          "growth_suggestions": "成长建议",
      },
  }


  def _make_user_and_token(db_session, openid="o_result_test"):
      from app.middleware.auth import create_access_token
      user = User(openid=openid)
      db_session.add(user)
      db_session.commit()
      db_session.refresh(user)
      token = create_access_token(user.id)
      return user, {"Authorization": f"Bearer {token}"}


  def _make_analyzed_assessment(db_session, user_id: int, session_id: str = "sess-result-test") -> Assessment:
      a = Assessment(
          user_id=user_id,
          session_id=session_id,
          mode="quick",
          status="analyzed",
          diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
      )
      db_session.add(a)
      db_session.commit()
      db_session.refresh(a)
      return a


  def _make_complete_assessment(db_session, user_id: int, session_id: str = "sess-complete-test") -> Assessment:
      a = Assessment(
          user_id=user_id,
          session_id=session_id,
          mode="quick",
          status="complete",
          personality_type="MA-CL-MH",
          report_text=MOCK_REPORT["report_text"],
          report_json=json.dumps(MOCK_REPORT),
          diagnosis_json=json.dumps(MOCK_DIAGNOSIS),
      )
      db_session.add(a)
      db_session.commit()
      db_session.refresh(a)
      return a


  def test_result_returns_report(client, db_session):
      user, headers = _make_user_and_token(db_session)
      assessment = _make_analyzed_assessment(db_session, user.id)

      with patch("app.agents.agent_b.chat_completion", new=AsyncMock(
          return_value=json.dumps(MOCK_REPORT)
      )):
          response = client.post(
              "/result",
              json={"session_id": assessment.session_id},
              headers=headers,
          )

      assert response.status_code == 200
      data = response.json()
      assert data["report_text"] == MOCK_REPORT["report_text"]
      assert data["personality_type"] == "MA-CL-MH"
      assert "summary" in data


  def test_result_caches_on_second_call(client, db_session):
      user, headers = _make_user_and_token(db_session, "o_result_cache")
      assessment = _make_analyzed_assessment(db_session, user.id, "sess-cache")

      with patch("app.agents.agent_b.chat_completion", new=AsyncMock(
          return_value=json.dumps(MOCK_REPORT)
      )) as mock_llm:
          client.post("/result", json={"session_id": assessment.session_id}, headers=headers)
          client.post("/result", json={"session_id": assessment.session_id}, headers=headers)

      assert mock_llm.call_count == 1


  def test_result_returns_cached_when_complete(client, db_session):
      user, headers = _make_user_and_token(db_session, "o_result_cached")
      assessment = _make_complete_assessment(db_session, user.id)

      with patch("app.agents.agent_b.chat_completion", new=AsyncMock()) as mock_llm:
          response = client.post(
              "/result",
              json={"session_id": assessment.session_id},
              headers=headers,
          )

      assert response.status_code == 200
      assert mock_llm.call_count == 0
      assert response.json()["personality_type"] == "MA-CL-MH"


  def test_result_returns_404_for_unknown_session(client, db_session):
      _, headers = _make_user_and_token(db_session, "o_result_404")
      response = client.post("/result", json={"session_id": "nonexistent"}, headers=headers)
      assert response.status_code == 404


  def test_result_returns_400_when_assessment_pending(client, db_session):
      user, headers = _make_user_and_token(db_session, "o_result_pending")
      a = Assessment(
          user_id=user.id,
          session_id="sess-pending",
          signals="{}",
          status="pending",
      )
      db_session.add(a)
      db_session.commit()

      response = client.post("/result", json={"session_id": a.session_id}, headers=headers)
      assert response.status_code == 400


  def test_result_requires_auth(client):
      response = client.post("/result", json={"session_id": "any"})
      assert response.status_code in (401, 403)
  ```

- [ ] **Step 2: 运行测试确认失败**

  ```bash
  pytest tests/api/test_result.py -v
  ```
  Expected: 多数 FAIL（因为 result.py 还未修改）

- [ ] **Step 3: 重写 app/api/result.py**

  完整替换 `app/api/result.py`：
  ```python
  """
  Result API — trigger Agent B to generate the personality report.
  POST /result  { session_id: str }
             →  { personality_type: str, report_text: str, summary: str }
  """

  import json
  import logging
  import os

  from fastapi import APIRouter, Depends, HTTPException, Request, status
  from pydantic import BaseModel
  from sqlalchemy.orm import Session

  from app.agents.agent_b import AgentBError, run as agent_b_run
  from app.database import get_db
  from app.limiter import limiter
  from app.middleware.auth import get_current_user_id
  from app.models.assessment import Assessment
  from app.models.order import Order
  from app.services.llm_client import LLMError

  logger = logging.getLogger(__name__)
  router = APIRouter(prefix="/result", tags=["result"])


  class ResultRequest(BaseModel):
      session_id: str


  class ResultResponse(BaseModel):
      personality_type: str
      report_text: str
      summary: str


  def _extract_summary(report_text: str) -> str:
      return report_text.split("。")[0] + "。" if "。" in report_text else report_text[:50]


  @router.post("", response_model=ResultResponse)
  @limiter.limit("10/minute")
  async def get_result(
      request: Request,
      body: ResultRequest,
      user_id: int = Depends(get_current_user_id),
      db: Session = Depends(get_db),
  ) -> ResultResponse:
      """Generate and return the personality analysis report."""
      assessment = (
          db.query(Assessment)
          .filter(
              Assessment.session_id == body.session_id,
              Assessment.user_id == user_id,
          )
          .first()
      )
      logger.info("[/result] user_id=%s session=%s", user_id, body.session_id[:8])

      if assessment is None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

      if assessment.status == "complete":
          logger.info("[/result] 命中缓存报告 personality_type=%s", assessment.personality_type)
          return ResultResponse(
              personality_type=assessment.personality_type or "",
              report_text=assessment.report_text or "",
              summary=_extract_summary(assessment.report_text or ""),
          )

      if assessment.status != "analyzed":
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Assessment is not yet analyzed",
          )

      # 付费墙守卫
      if os.environ.get("DEV_MODE", "").lower() != "true":
          paid_order = (
              db.query(Order)
              .filter(
                  Order.assessment_id == assessment.id,
                  Order.user_id == user_id,
                  Order.status == "paid",
              )
              .first()
          )
          if paid_order is None:
              logger.warning("[/result] user_id=%s 未解锁", user_id)
              raise HTTPException(
                  status_code=status.HTTP_402_PAYMENT_REQUIRED,
                  detail="报告未解锁，请付费或观看广告后获取。",
              )

      diagnosis = json.loads(assessment.diagnosis_json or "{}")

      try:
          report = await agent_b_run(diagnosis)
      except (AgentBError, LLMError) as exc:
          logger.error("[/result] Agent B failed: %s", exc)
          raise HTTPException(
              status_code=status.HTTP_502_BAD_GATEWAY,
              detail="AI服务暂时不可用，请稍后再试。",
          ) from exc

      assessment.report_json = json.dumps(report, ensure_ascii=False)
      assessment.report_text = report["report_text"]
      assessment.personality_type = report["sections"]["type_name"]
      assessment.summary = _extract_summary(report["report_text"])
      assessment.status = "complete"
      db.commit()
      logger.info("[/result] 报告生成完成 personality_type=%s", assessment.personality_type)

      return ResultResponse(
          personality_type=assessment.personality_type,
          report_text=assessment.report_text,
          summary=assessment.summary,
      )
  ```

- [ ] **Step 4: 运行测试确认通过**

  ```bash
  pytest tests/api/test_result.py -v
  ```
  Expected: 6 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add app/api/result.py tests/api/test_result.py
  git commit -m "feat: rewrite /result to call Agent B from diagnosis_json"
  ```

---

## Task 12: 清理旧文件 + 全量测试

**Files:**
- Delete: `app/services/quiz_scorer.py`
- Delete: `app/agents/agent2_analysis.py`

- [ ] **Step 1: 确认没有代码仍引用 quiz_scorer**

  ```bash
  grep -r "quiz_scorer" app/ tests/
  ```
  Expected: 无匹配（如有，先修复引用再删除）

- [ ] **Step 2: 确认没有代码仍引用 agent2_analysis**

  ```bash
  grep -r "agent2_analysis" app/ tests/
  ```
  Expected: 无匹配（如有，先修复引用再删除）

- [ ] **Step 3: 删除 quiz_scorer.py**

  ```bash
  rm app/services/quiz_scorer.py
  ```

- [ ] **Step 4: 删除 agent2_analysis.py**

  ```bash
  rm app/agents/agent2_analysis.py
  ```

- [ ] **Step 5: 运行全量测试**

  ```bash
  pytest -v
  ```
  Expected: 全部 PASS，无任何 import 错误

- [ ] **Step 6: 手动端到端联调**

  ```bash
  # 1. 启动本地 Supabase
  supabase start

  # 2. 启动后端（DEV_MODE=true 跳过支付墙）
  DEV_MODE=true uvicorn app.main:app --reload --port 8000

  # 3. 获取开发 token
  curl -s -X POST http://localhost:8000/auth/dev-login \
    -H "Content-Type: application/json" \
    -d '{"openid":"test_user_001"}' | python -m json.tool

  # 4. 用 token 开始 quiz（替换 <token>）
  curl -s -X POST http://localhost:8000/quiz/start \
    -H "Authorization: Bearer <token>" | python -m json.tool

  # 5. 提交 30 个答案（替换 session_id 和 token）
  # （构造 30 个 answers JSON，或用小程序前端联调）

  # 6. 确认 assessment 状态为 "analyzed"，diagnosis_json 已写入
  # 7. 调 /result，确认 Agent B 生成报告，status="complete"
  # 8. 再次调 /result，确认直接返回缓存（无 LLM 调用）

  # 9. 检查日志
  cat logs/ai_calls.jsonl | python -m json.tool | head -100
  cat logs/app.log | tail -50
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add -A
  git commit -m "chore: remove quiz_scorer and agent2_analysis after dual-agent migration"
  ```

---

## 完成后验收检查清单

- [ ] `pytest` 全绿
- [ ] `logs/ai_calls.jsonl` 有完整记录（ts, call_id, type, model, ok, elapsed_ms, system_prompt, messages, response/error, usage）
- [ ] `/quiz/submit` 返回 `status: "analyzed"`，DB 中 `diagnosis_json` 非空
- [ ] `/result` 第一次调用时触发 Agent B，第二次直接返回缓存
- [ ] `assessment.personality_type` 格式为 16 类型码（如 `MA-CL-MH`）
- [ ] questions 表有 `version` 和 `notes` 列
- [ ] `quiz_scorer.py` 和 `agent2_analysis.py` 已删除
