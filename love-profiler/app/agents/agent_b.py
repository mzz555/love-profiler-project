"""
Agent B — diagnosis dict → plain-text personality report.
Temperature: 0.6 (warm, personalized narrative).

The system prompt is the verbatim docs file (no runtime mutation).
The user message is built from `diagnosis` as natural-language text;
all static knowledge (type-name dict, D4 language definitions, D5
quadrant guides) lives in DB tables and is injected per-request by
the enrich step in /quiz/submit, so the model only sees the slice
relevant to this user.
"""

import logging
import pathlib
import re

from app.services.llm_client import chat_completion, stream_chat_completion
from app.services.report_quality_gate import QualityGateError, check_report

logger = logging.getLogger(__name__)

_PROMPT_FILE = pathlib.Path(__file__).parents[2] / "docs" / "agent-b-system-prompt.md"
_PROMPT_RAW = _PROMPT_FILE.read_text(encoding="utf-8")
AGENT_B_SYSTEM_PROMPT = _PROMPT_RAW.split("\n## 版本记录")[0].rstrip()


def _parse_prompt_version(raw: str) -> str:
    """从 prompt 文件头的 <!-- prompt-version: x.y --> 注解抽取版本号。

    无注解时回退 "0"（保留 NULL 在 DB 那一层做，应用层永远是字符串）。
    """
    m = re.search(r"<!--\s*prompt-version:\s*([\w.\-]+)\s*-->", raw)
    return m.group(1) if m else "0"


PROMPT_VERSION: str = _parse_prompt_version(_PROMPT_RAW)
# 报告 Section 结构版本号；与 prompt-version 解耦，仅在 Section 拆分/重命名时升级
REPORT_VERSION: int = 1


class AgentBError(Exception):
    """Raised when Agent B fails to return meaningful text."""


def build_user_message(diagnosis: dict) -> str:
    """Render diagnosis as natural-language input for the LLM.

    All static knowledge (type-name dictionary, D4 language definitions, D5
    quadrant guides) lives in DB tables (base_love_type / base_D4_type /
    base_D5_quadrant) and is injected by the enrich step in /quiz/submit
    as `type_anchor`, `D4_details`, `D5_guide`. We then render only the
    user's slice here, so the model spends its attention on the user's
    actual data instead of rescanning multi-row dictionaries every call.
    """
    lines: list[str] = []

    type_code    = diagnosis.get("type_code", "")
    type_name    = diagnosis.get("type_name", "")
    type_tagline = diagnosis.get("type_tagline", "")
    type_anchor  = diagnosis.get("type_anchor", "")

    lines.append("# 用户类型")
    lines.append(f"- 类型代码：{type_code}")
    lines.append(f"- 类型名（用作报告标题）：{type_name}")
    if type_tagline:
        lines.append(f"- 副标题：{type_tagline}")
    if type_anchor:
        lines.append(f"- 类型锚定句（开篇画像必须以此为起点展开）：{type_anchor}")
    lines.append("")

    dims = diagnosis.get("dimensions", {}) or {}
    lines.append("# 五维度结果（D1-D5 全部展开）")

    d1 = dims.get("D1", {}) or {}
    lines.append(f"- D1 依恋：interp = {d1.get('interp', '')}")

    d2 = dims.get("D2", {}) or {}
    lines.append(f"- D2 边界：interp = {d2.get('interp', '')}")

    d3 = dims.get("D3", {}) or {}
    pa = d3.get("pursue_avoid", "")
    pa_note = f"，追逃角色 = {pa}（须在该段融入追/逃视角）" if pa and pa != "stable" else ""
    lines.append(f"- D3 冲突：interp = {d3.get('interp', '')}{pa_note}")

    d4 = dims.get("D4", {}) or {}
    top2     = d4.get("top2", []) or []
    aligned  = d4.get("aligned", True)
    declared = d4.get("declared", "")
    d4_details = diagnosis.get("D4_details", []) or []
    lines.append(f"- D4 爱的语言：top2 = {top2}")
    for d in d4_details:
        lines.append(f"    · {d.get('code', '')} {d.get('name', '')}：{d.get('detail', '')}")
    if not aligned and declared:
        lines.append(
            f"  注意 aligned=false：用户主动选择的是 {declared}，但行为得分指向 top2 第一项；"
            "必须在 D4 段后追加「自我认知盲区」子段"
        )

    d5 = dims.get("D5", {}) or {}
    style    = d5.get("style", "")
    quadrant = d5.get("quadrant", "")
    guide    = diagnosis.get("D5_guide", "")
    lines.append(f"- D5 表达风格：{style}（{quadrant}）")
    if guide:
        lines.append(f"    · 该象限写作方向：{guide}")
    lines.append("")

    highlights = diagnosis.get("highlights", []) or []
    lines.append("# 深层洞察素材（遍历每条生成 150-250 字）")
    if not highlights:
        lines.append("（本次 highlights 为空 — 跳过洞察段）")
    else:
        for i, h in enumerate(highlights, 1):
            lines.append(
                f"{i}. 标题：{h.get('name_cn', '')} | severity={h.get('severity', '')} "
                f"| is_positive={h.get('is_positive', False)}"
            )
            lines.append(f"   写作种子：{h.get('report_seed', '')}")
            lines.append(f"   解读路径：{h.get('interp_path', '')}")

    return "\n".join(lines)


async def run_stream(diagnosis: dict, session_id: str | None = None):
    """Stream Agent B: yields text chunks in real time, then a final dict.

    Yields:
        str  — text chunk (forwarded in real time from the LLM)
        dict — {"report_text": "..."} (exactly one item, at the end)

    Raises:
        AgentBError: if response is empty.
        LLMError:    if the API call fails.
    """
    user_msg = build_user_message(diagnosis)
    sid_short = (session_id or "")[:8]
    logger.info("[agent_b/in] session=%s user_msg=\n%s", sid_short, user_msg)
    all_text = ""

    async for chunk in stream_chat_completion(
        system_prompt=AGENT_B_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.6,
    ):
        all_text += chunk
        yield chunk

    if not all_text.strip():
        raise AgentBError("run_stream: empty response")

    try:
        warnings = check_report(all_text, diagnosis)
    except QualityGateError as exc:
        logger.error("[agent_b/quality] hard fail session=%s: %s", sid_short, exc)
        raise AgentBError(f"quality_gate_failed: {exc}") from exc
    for w in warnings:
        logger.warning("[agent_b/quality] soft warning session=%s: %s", sid_short, w)

    logger.info(
        "[agent_b/out] session=%s chars=%d warnings=%d report_text=\n%s",
        sid_short, len(all_text), len(warnings), all_text,
    )
    yield {
        "report_text": all_text,
        "quality_warnings": [str(w) for w in warnings],
    }


async def run(diagnosis: dict, session_id: str | None = None) -> str:
    """Run Agent B: diagnosis dict → plain text report.

    Returns:
        Full report text string.

    Raises:
        AgentBError: If response is empty after 2 attempts.
        LLMError:    If the API call itself fails.
    """
    base_msg = build_user_message(diagnosis)
    sid_short = (session_id or "")[:8]
    logger.info("[agent_b/in] session=%s user_msg=\n%s", sid_short, base_msg)
    retry_suffix = "\n\n【重试要求】请直接输出报告纯文本，不要输出 JSON 或代码围栏。"

    last_quality_error: QualityGateError | None = None
    for attempt in range(2):
        content = base_msg if attempt == 0 else base_msg + retry_suffix
        raw = await chat_completion(
            system_prompt=AGENT_B_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            temperature=0.6,
            agent="agent_b",
            session_id=session_id,
            retry_index=attempt,
        )
        if not raw.strip():
            continue
        try:
            warnings = check_report(raw, diagnosis)
        except QualityGateError as exc:
            last_quality_error = exc
            logger.warning(
                "[agent_b/quality] attempt=%d session=%s 质量门未通过：%s",
                attempt, sid_short, exc,
            )
            continue
        for w in warnings:
            logger.warning("[agent_b/quality] soft warning session=%s: %s", sid_short, w)
        logger.info(
            "[agent_b/out] session=%s chars=%d warnings=%d report_text=\n%s",
            sid_short, len(raw), len(warnings), raw,
        )
        return raw

    if last_quality_error is not None:
        raise AgentBError(f"quality_gate_failed: {last_quality_error}") from last_quality_error
    raise AgentBError("Agent B returned empty text after 2 attempts")
