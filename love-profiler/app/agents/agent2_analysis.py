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


_LOVE_LANGUAGE_NAMES: dict[str, str] = {
    "T1": "言语肯定",
    "T2": "精心时刻",
    "T3": "用心小惊喜",
    "T4": "服务行动",
    "T5": "身体接触",
}

_AGENT2_QUIZ_SYSTEM_PROMPT = (
    "你是一位专业的情感心理分析师。根据以下用户的恋爱测评维度得分，"
    "用温暖、专业的语气撰写一份详细的恋爱人格分析报告。"
    "报告必须包含五个部分：1)依恋风格分析 2)边界与冲突模式 3)主导爱的语言解读 "
    "4)沟通风格特点 5)成长建议。"
    "全文600字以内，使用中文，每个部分用小标题区分。"
)


def _map_personality_from_scores(scores: dict) -> str:
    """Map dimension scores to a personality type label."""
    attachment = scores.get("attachment", 0)
    boundary = scores.get("boundary", 0)
    conflict = scores.get("conflict", 0)
    avg = (attachment + boundary + conflict) / 3
    if avg >= 6:
        return "安全型"
    elif avg >= 0:
        return "成长型"
    else:
        return "焦虑/回避型"


async def generate_report_from_scores(dimension_scores: dict) -> AnalysisResult:
    """Generate personality report from quiz dimension scores.

    Args:
        dimension_scores: Computed scores from quiz_scorer.compute_scores().

    Returns:
        AnalysisResult with personality_type, report_text, and summary.

    Raises:
        LLMError: If the LLM API call fails.
    """
    personality_type = _map_personality_from_scores(dimension_scores)

    love_lang = dimension_scores.get("love_language", {})
    primary_code = love_lang.get("primary", "T1")
    primary_name = _LOVE_LANGUAGE_NAMES.get(primary_code, primary_code)

    style = dimension_scores.get("style", {})

    user_message = (
        f"用户恋爱测评维度得分（满分/最高分12，负分表示该维度问题倾向）：\n"
        f"- 依恋安全感：{dimension_scores.get('attachment', 0)} 分\n"
        f"- 边界清晰度：{dimension_scores.get('boundary', 0)} 分\n"
        f"- 冲突健康度：{dimension_scores.get('conflict', 0)} 分\n"
        f"- 主导爱的语言：{primary_name}（{primary_code}，得分 {love_lang.get(primary_code, 0)}）\n"
        f"  各语言得分：言语肯定={love_lang.get('T1',0)} 精心时刻={love_lang.get('T2',0)} "
        f"用心小惊喜={love_lang.get('T3',0)} 服务行动={love_lang.get('T4',0)} "
        f"身体接触={love_lang.get('T5',0)}\n"
        f"- 沟通风格：直接性 {style.get('directness', 0)} 分，分享欲 {style.get('sharing', 0)} 分\n\n"
        f"初步判断依恋类型：{personality_type}\n\n"
        "请撰写详细的恋爱人格分析报告。"
    )

    report_text = await chat_completion(
        system_prompt=_AGENT2_QUIZ_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    summary = report_text.split("。")[0] + "。" if "。" in report_text else report_text[:50]
    return AnalysisResult(
        personality_type=personality_type,
        report_text=report_text,
        summary=summary,
    )
