"""
Agent 1 — 5-round dimension-driven psychological assessment dialogue.

Round 1: Relationship status selection (fixed options, no LLM)
Round 2: Separation anxiety
Round 3: Intimacy comfort
Round 4: Conflict pattern
Round 5: Needs expression + infer attribution; output 5-dimension JSON
"""

from app.services.content_safety import ContentSafetyError, is_safe
from app.services.dimension_bank import get_dimension_for_round
from app.services.json_validator import extract_and_validate
from app.services.llm_client import chat_completion
from app.services.round_controller import get_round_directive, is_final_round, is_status_round
from app.services.session_store import (
    SessionData,
    append_message,
    get_session,
    record_dimension,
    set_relationship_status,
    update_session,
)

# Status options shown to user in Round 1
STATUS_OPTIONS: list[str] = [
    "热恋中",
    "暗恋/追求中",
    "分手/失恋",
    "单身但有过恋爱",
    "几乎没有恋爱经历",
]

_BASE_SYSTEM_PROMPT = """\
【角色】
你是一位受过专业训练的情感分析师，具备依恋理论（Levine）、卡尼曼双系统理论和非暴力沟通（NVC）背景。
你的任务是通过自然、温暖的对话，在5轮中收集用户的依恋模式信号。

【禁止】
- 禁止使用"测试""问卷""评分""心理学""维度"等显暴露框架的词
- 禁止连续问两个问题
- 禁止直接解释信号含义（如"这说明你是焦虑型"）
- 禁止超过120字的回复

【对话规则】
- 语气像聊天，不像咨询
- 遇到泛化回答（"还好""无所谓""一般"）必须追问一个具体情景
- 每轮只推进一个维度，不跳跃
- 用共情句开头（除第一轮外），再自然引出下一个情景

【穿透链（NVC四步）】
观察具体事件 → 反映用户感受 → 猜测背后需求 → 记录信号证据

【防御识别与穿透】
- 理性包装（"客观来说…"）→ 追问："那你自己心里是什么感觉？"
- 社会期望管理（"我觉得应该…"）→ 追问："那你实际上会怎么做？"
- 泛化回避（"都差不多"）→ 追问具体的一次经历

【信号权重】
- 强信号（strong）：用户主动详述、情绪明显、重复提及
- 弱信号（weak）：简短回答、语气模糊、需要追问才说出
"""

# Fixed opening shown before any LLM call (Round 1 status selection)
AGENT1_OPENING_MESSAGE = (
    "你好～在开始之前，想先了解一下你现在的感情状态，"
    "这样我能更好地跟你聊。你现在是哪种情况？"
)


class SessionNotFoundError(Exception):
    """Raised when the requested session does not exist or has expired."""


async def run_chat_turn(
    session_id: str,
    user_message: str,
) -> tuple[str, SessionData, dict | None]:
    """Process one user turn and return (reply, updated_session, signals_or_None).

    Returns:
        - reply: Assistant reply text (JSON block stripped on final round).
        - session: The updated SessionData after this turn.
        - signals: Extracted 5-dimension dict on round 5; None otherwise.

    Raises:
        SessionNotFoundError: If the session is missing or expired.
        ContentSafetyError: If user_message fails safety screening.
        LLMError: If the LLM API call fails.
    """
    session = get_session(session_id)
    if session is None:
        raise SessionNotFoundError(f"Session not found: {session_id}")

    if not is_safe(user_message):
        raise ContentSafetyError("用户输入包含不安全内容")

    if is_status_round(session.round_num):
        return await _handle_status_round(session, user_message)

    if is_final_round(session.round_num):
        return await _handle_final_round(session, user_message)

    return await _handle_dimension_round(session, user_message)


async def _handle_status_round(
    session: SessionData,
    user_message: str,
) -> tuple[str, SessionData, None]:
    """Round 1: store relationship status, then ask first dimension question via LLM."""
    session_with_user = append_message(session, {"role": "user", "content": user_message})
    session_with_status = set_relationship_status(session_with_user, user_message)

    used = list(session.dimension_history)
    directive = get_round_directive(round_num=1, status=user_message, used_questions=used)
    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{directive}"

    reply = await chat_completion(
        system_prompt=system_prompt,
        messages=session_with_status.messages,
    )

    session_with_assistant = append_message(
        session_with_status, {"role": "assistant", "content": reply}
    )
    updated = SessionData(
        session_id=session_with_assistant.session_id,
        user_id=session_with_assistant.user_id,
        round_num=2,
        messages=session_with_assistant.messages,
        created_at=session_with_assistant.created_at,
        expires_at=session_with_assistant.expires_at,
        relationship_status=session_with_assistant.relationship_status,
        dimension_history=session_with_assistant.dimension_history,
    )
    update_session(updated)
    return reply, updated, None


async def _handle_dimension_round(
    session: SessionData,
    user_message: str,
) -> tuple[str, SessionData, None]:
    """Rounds 2-4: cover one dimension, advance round counter."""
    used = list(session.dimension_history)
    directive = get_round_directive(
        round_num=session.round_num,
        status=session.relationship_status or "",
        used_questions=used,
    )
    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{directive}"

    session_with_user = append_message(session, {"role": "user", "content": user_message})

    reply = await chat_completion(
        system_prompt=system_prompt,
        messages=session_with_user.messages,
    )

    session_with_assistant = append_message(
        session_with_user, {"role": "assistant", "content": reply}
    )

    dim = get_dimension_for_round(session.round_num)
    if dim is not None:
        session_with_assistant = record_dimension(session_with_assistant, dim.value)

    updated = SessionData(
        session_id=session_with_assistant.session_id,
        user_id=session_with_assistant.user_id,
        round_num=session.round_num + 1,
        messages=session_with_assistant.messages,
        created_at=session_with_assistant.created_at,
        expires_at=session_with_assistant.expires_at,
        relationship_status=session_with_assistant.relationship_status,
        dimension_history=session_with_assistant.dimension_history,
    )
    update_session(updated)
    return reply, updated, None


async def _handle_final_round(
    session: SessionData,
    user_message: str,
) -> tuple[str, SessionData, dict | None]:
    """Round 5: collect needs_expression, infer attribution, extract 5-dimension JSON."""
    used = list(session.dimension_history)
    directive = get_round_directive(
        round_num=session.round_num,
        status=session.relationship_status or "",
        used_questions=used,
    )
    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{directive}"

    session_with_user = append_message(session, {"role": "user", "content": user_message})

    raw_reply = await chat_completion(
        system_prompt=system_prompt,
        messages=session_with_user.messages,
    )

    signals, reply = extract_and_validate(raw_reply)

    session_with_assistant = append_message(
        session_with_user, {"role": "assistant", "content": reply}
    )

    # Round stays at 5 (final) — no further progression
    updated = SessionData(
        session_id=session_with_assistant.session_id,
        user_id=session_with_assistant.user_id,
        round_num=session.round_num,
        messages=session_with_assistant.messages,
        created_at=session_with_assistant.created_at,
        expires_at=session_with_assistant.expires_at,
        relationship_status=session_with_assistant.relationship_status,
        dimension_history=session_with_assistant.dimension_history,
    )
    update_session(updated)
    return reply, updated, signals
