"""
Agent 2 — personality scoring and report generation.
Maps 5-dimension psychological signals from Agent 1 into a personality type and narrative.

Primary axes (attachment theory):
  separation_anxiety × intimacy_comfort → quadrant → 安全/焦虑/回避/混乱
Supporting dimensions:
  conflict_pattern, needs_expression, attribution → reinforce quadrant vote
"""

from dataclasses import dataclass

from app.services.llm_client import chat_completion

PERSONALITY_TYPES: list[str] = ["安全型", "焦虑型", "回避型", "混乱型"]

_AGENT2_SYSTEM_PROMPT = (
    "你是一位专业的情感心理分析师。根据以下用户的心理信号摘要，"
    "用温暖、专业的语气撰写一份恋爱人格分析报告。"
    "报告应包含：依恋风格分析、情感需求解读、成长建议。"
    "全文控制在300字以内，使用中文。"
)


@dataclass(frozen=True)
class AnalysisResult:
    personality_type: str
    report_text: str
    summary: str


def _weight(dim: dict) -> int:
    return 2 if dim.get("weight") == "strong" else 1


def map_personality_type(signals: dict) -> str:
    """Derive personality type from 5-dimension nested signal dict.

    Uses a two-axis primary classification (separation_anxiety × intimacy_comfort)
    then reinforces with conflict_pattern, needs_expression, and attribution votes.
    """
    votes: dict[str, int] = {t: 0 for t in PERSONALITY_TYPES}

    # Primary axes: determine attachment quadrant
    sa = signals.get("separation_anxiety", {})
    ic = signals.get("intimacy_comfort", {})
    sa_high = sa.get("signal") == "high"
    ic_avoid = ic.get("signal") == "high_avoidance"
    primary_w = _weight(sa) + _weight(ic)

    if sa_high and ic_avoid:
        votes["混乱型"] += primary_w
    elif sa_high:
        votes["焦虑型"] += primary_w
    elif ic_avoid:
        votes["回避型"] += primary_w
    else:
        votes["安全型"] += primary_w

    # conflict_pattern: supporting vote
    cp = signals.get("conflict_pattern", {})
    cp_sig = cp.get("signal", "")
    if cp_sig == "attack":
        votes["焦虑型"] += _weight(cp)
    elif cp_sig == "withdraw":
        votes["回避型"] += _weight(cp)
    elif cp_sig == "collaborative":
        votes["安全型"] += _weight(cp)

    # needs_expression: explicit votes secure; implicit is ambiguous, no vote
    ne = signals.get("needs_expression", {})
    if ne.get("signal") == "explicit":
        votes["安全型"] += _weight(ne)

    # attribution: self_blame → anxious, external → avoidant, event → secure
    at = signals.get("attribution", {})
    at_sig = at.get("signal", "")
    if at_sig == "self_blame":
        votes["焦虑型"] += _weight(at)
    elif at_sig == "external":
        votes["回避型"] += _weight(at)
    elif at_sig == "event":
        votes["安全型"] += _weight(at)

    # If both primary axes elevated, disorganized attachment takes precedence
    if sa_high and ic_avoid:
        return "混乱型"
    best = max(votes, key=lambda t: votes[t])
    return best if votes[best] > 0 else "安全型"


async def generate_report(signals: dict) -> AnalysisResult:
    """Call the LLM to produce a narrative report and return an AnalysisResult.

    Args:
        signals: The 5-dimension psychological signal dict extracted by Agent 1.

    Returns:
        AnalysisResult with personality_type, report_text, and summary.

    Raises:
        LLMError: If the LLM API call fails.
    """
    personality_type = map_personality_type(signals)

    signal_lines = "\n".join(
        f"- {k}: 信号={v.get('signal')} 强度={v.get('weight')} 证据={v.get('evidence')}"
        for k, v in signals.items()
        if isinstance(v, dict)
    )
    user_message = (
        f"用户心理信号摘要：\n{signal_lines}\n\n"
        f"初步判断依恋类型：{personality_type}\n\n"
        "请撰写详细的恋爱人格分析报告。"
    )

    report_text = await chat_completion(
        system_prompt=_AGENT2_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    summary = report_text.split("。")[0] + "。" if "。" in report_text else report_text[:50]

    return AnalysisResult(
        personality_type=personality_type,
        report_text=report_text,
        summary=summary,
    )
