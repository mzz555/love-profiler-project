"""
Tests for agent1_chat — the 5-round dimension-driven assessment agent.
All I/O dependencies (LLM, session store) are mocked.
"""

from unittest.mock import AsyncMock, patch
import pytest
import time

from app.agents.agent1_chat import (
    run_chat_turn,
    SessionNotFoundError,
    AGENT1_OPENING_MESSAGE,
    STATUS_OPTIONS,
)
from app.services.session_store import SessionData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SESSION_ID = "session-abc"
USER_ID = "user-1"
USER_MSG = "我喜欢和她一起安静地待着"
ASSISTANT_REPLY = "听起来你很享受那份宁静。"

FINAL_ROUND_REPLY = """\
感谢你今天的分享，祝你早日找到属于自己的幸福。
```json
{
  "separation_anxiety": {"signal": "high",         "weight": "strong", "evidence": "反复查看手机"},
  "intimacy_comfort":   {"signal": "low_avoidance", "weight": "weak",   "evidence": "自然接受亲密"},
  "conflict_pattern":   {"signal": "attack",        "weight": "strong", "evidence": "用你总是开头"},
  "needs_expression":   {"signal": "implicit",      "weight": "weak",   "evidence": "通过冷战暗示"},
  "attribution":        {"signal": "self_blame",    "weight": "strong", "evidence": "觉得是自己不够好"}
}
```"""


def make_session(round_num: int = 1, status: str | None = None) -> SessionData:
    now = time.time()
    return SessionData(
        session_id=VALID_SESSION_ID,
        user_id=USER_ID,
        round_num=round_num,
        messages=[],
        created_at=now,
        expires_at=now + 3600,
        relationship_status=status,
        dimension_history=(),
    )


# ---------------------------------------------------------------------------
# SessionNotFoundError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_chat_turn_raises_when_session_not_found():
    with patch("app.agents.agent1_chat.get_session", return_value=None):
        with pytest.raises(SessionNotFoundError):
            await run_chat_turn(session_id="nonexistent", user_message=USER_MSG)


# ---------------------------------------------------------------------------
# Content safety gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_chat_turn_raises_content_safety_error_for_harmful_input():
    from app.services.content_safety import ContentSafetyError

    session = make_session()
    with patch("app.agents.agent1_chat.get_session", return_value=session):
        with patch("app.agents.agent1_chat.is_safe", return_value=False):
            with pytest.raises(ContentSafetyError):
                await run_chat_turn(session_id=VALID_SESSION_ID, user_message="我想自杀")


# ---------------------------------------------------------------------------
# Status round (round 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_round_stores_relationship_status():
    session = make_session(round_num=1)
    saved = {}

    def capture_update(s):
        saved["session"] = s

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=ASSISTANT_REPLY)), \
         patch("app.agents.agent1_chat.update_session", side_effect=capture_update):

        await run_chat_turn(session_id=VALID_SESSION_ID, user_message="热恋中")

    assert saved["session"].relationship_status == "热恋中"
    assert saved["session"].round_num == 2


@pytest.mark.asyncio
async def test_status_round_returns_no_signals():
    session = make_session(round_num=1)

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=ASSISTANT_REPLY)), \
         patch("app.agents.agent1_chat.update_session"):

        _, _, signals = await run_chat_turn(session_id=VALID_SESSION_ID, user_message="热恋中")

    assert signals is None


# ---------------------------------------------------------------------------
# Dimension rounds (rounds 2-4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dimension_round_returns_assistant_reply():
    session = make_session(round_num=2, status="热恋中")

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=ASSISTANT_REPLY)), \
         patch("app.agents.agent1_chat.update_session"):

        reply, _, signals = await run_chat_turn(session_id=VALID_SESSION_ID, user_message=USER_MSG)

    assert reply == ASSISTANT_REPLY
    assert signals is None


@pytest.mark.asyncio
async def test_dimension_round_increments_round_num():
    session = make_session(round_num=2, status="热恋中")
    saved = {}

    def capture_update(s):
        saved["session"] = s

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=ASSISTANT_REPLY)), \
         patch("app.agents.agent1_chat.update_session", side_effect=capture_update):

        await run_chat_turn(session_id=VALID_SESSION_ID, user_message=USER_MSG)

    assert saved["session"].round_num == 3


@pytest.mark.asyncio
async def test_dimension_round_appends_user_and_assistant_messages():
    session = make_session(round_num=2, status="热恋中")
    saved = {}

    def capture_update(s):
        saved["session"] = s

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=ASSISTANT_REPLY)), \
         patch("app.agents.agent1_chat.update_session", side_effect=capture_update):

        await run_chat_turn(session_id=VALID_SESSION_ID, user_message=USER_MSG)

    msgs = saved["session"].messages
    assert any(m["role"] == "user" and m["content"] == USER_MSG for m in msgs)
    assert any(m["role"] == "assistant" and m["content"] == ASSISTANT_REPLY for m in msgs)


@pytest.mark.asyncio
async def test_dimension_round_includes_directive_in_system_prompt():
    session = make_session(round_num=4, status="热恋中")
    captured = {}

    async def capture_llm(system_prompt, messages):
        captured["system_prompt"] = system_prompt
        return ASSISTANT_REPLY

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(side_effect=capture_llm)), \
         patch("app.agents.agent1_chat.update_session"):

        await run_chat_turn(session_id=VALID_SESSION_ID, user_message=USER_MSG)

    assert "冲突" in captured["system_prompt"]


# ---------------------------------------------------------------------------
# Final round (round 5) — JSON extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_round_returns_signals():
    session = make_session(round_num=5, status="热恋中")

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=FINAL_ROUND_REPLY)), \
         patch("app.agents.agent1_chat.update_session"):

        _, _, signals = await run_chat_turn(session_id=VALID_SESSION_ID, user_message="谢谢")

    assert signals is not None
    assert signals["separation_anxiety"]["signal"] == "high"


@pytest.mark.asyncio
async def test_final_round_strips_json_from_reply():
    session = make_session(round_num=5, status="热恋中")

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=FINAL_ROUND_REPLY)), \
         patch("app.agents.agent1_chat.update_session"):

        reply, _, _ = await run_chat_turn(session_id=VALID_SESSION_ID, user_message="谢谢")

    assert "separation_anxiety" not in reply


@pytest.mark.asyncio
async def test_final_round_does_not_increment_round_num():
    session = make_session(round_num=5, status="热恋中")
    saved = {}

    def capture_update(s):
        saved["session"] = s

    with patch("app.agents.agent1_chat.get_session", return_value=session), \
         patch("app.agents.agent1_chat.is_safe", return_value=True), \
         patch("app.agents.agent1_chat.chat_completion", new=AsyncMock(return_value=FINAL_ROUND_REPLY)), \
         patch("app.agents.agent1_chat.update_session", side_effect=capture_update):

        await run_chat_turn(session_id=VALID_SESSION_ID, user_message="谢谢")

    assert saved["session"].round_num == 5


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

def test_agent1_opening_message_is_non_empty():
    assert isinstance(AGENT1_OPENING_MESSAGE, str) and len(AGENT1_OPENING_MESSAGE) > 10


def test_status_options_has_five_items():
    assert len(STATUS_OPTIONS) == 5
    assert all(isinstance(opt, str) for opt in STATUS_OPTIONS)
