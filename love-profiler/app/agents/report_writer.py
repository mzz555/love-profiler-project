"""
Report writer — diagnosis dict → plain-text personality report (formerly Agent B).
Temperature: 0.6 (warm, personalized narrative).

The system prompt is the verbatim docs file (no runtime mutation).
The user message is built from `diagnosis` as natural-language text;
all static knowledge (type-name dict, D4 language definitions, D5
quadrant guides) lives in DB tables and is injected per-request by
the enrich step in /quiz/submit, so the model only sees the slice
relevant to this user.

Phase C.1：run_stream 支持 resumed_sections — 上次中断时已落库的 section 字典；
非空时在 user message 末尾追加"接续生成"指令，要求 LLM 跳过已完成段。
"""

import logging
import pathlib
import re

from app.services.llm_client import chat_completion, stream_chat_completion
from app.services.report_quality_gate import QualityGateError, check_report

logger = logging.getLogger(__name__)

_PROMPT_FILE = pathlib.Path(__file__).parents[2] / "docs" / "agent-b-system-prompt.md"
_PROMPT_RAW = _PROMPT_FILE.read_text(encoding="utf-8")
REPORT_WRITER_SYSTEM_PROMPT = _PROMPT_RAW.split("\n## 版本记录")[0].rstrip()


def _parse_prompt_version(raw: str) -> str:
    """从 prompt 文件头的 <!-- prompt-version: x.y --> 注解抽取版本号。

    无注解时回退 "0"（保留 NULL 在 DB 那一层做，应用层永远是字符串）。
    """
    m = re.search(r"<!--\s*prompt-version:\s*([\w.\-]+)\s*-->", raw)
    return m.group(1) if m else "0"


PROMPT_VERSION: str = _parse_prompt_version(_PROMPT_RAW)
# 报告 Section 结构版本号；与 prompt-version 解耦，仅在 Section 拆分/重命名时升级
REPORT_VERSION: int = 1


class ReportWriterError(Exception):
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


# Section 名权威列表，与 docs/agent-b-system-prompt.md 输出格式段对齐。
# 顺序也是 prompt 要求的输出顺序。
SECTION_ORDER: tuple[str, ...] = (
    "Title", "Opening",
    "Attachment", "Boundary", "Conflict",
    "Language", "Style",
    "Highlight", "Suggestion",
)


def append_resume_directive(user_msg: str, resumed_sections: dict[str, str] | None) -> str:
    """根据已完成 sections 字典，在 user_msg 后追加接续生成指令。

    resumed_sections 为空或 None 时原样返回 user_msg。
    """
    if not resumed_sections:
        return user_msg
    # 按 SECTION_ORDER 找最后一个连续已完成的 section；下一段即接续起点
    completed = [s for s in SECTION_ORDER if s in resumed_sections]
    if not completed:
        return user_msg
    # 接续起点：第一个未完成的 section（如果都完成则不需要 resume）
    not_completed = [s for s in SECTION_ORDER if s not in resumed_sections]
    if not not_completed:
        return user_msg
    next_section = not_completed[0]

    lines = [
        user_msg.rstrip(),
        "",
        "# 接续生成（前面段落上次已成功生成，请跳过它们，不要重复）",
    ]
    for name in completed:
        body = (resumed_sections[name] or "").strip()
        snippet = body[:160] + ("…" if len(body) > 160 else "")
        lines.append(f"- {name}：{snippet}")
    lines.extend([
        "",
        f"现在请**从 --{next_section}-- 开始**输出，沿用上方风格和已有段落的衔接。"
        f"不要重新输出已生成段的内容。",
    ])
    return "\n".join(lines)


async def run_stream(
    diagnosis: dict,
    session_id: str | None = None,
    resumed_sections: dict[str, str] | None = None,
):
    """Stream Agent B: yields text chunks in real time, then a final dict.

    Args:
        resumed_sections: 上次已完成的 section 字典 {name: body}；非空时
                          在 user message 末尾加接续生成指令，LLM 仅输出剩余段。

    Yields:
        str  — text chunk (forwarded in real time from the LLM)
        dict — {"report_text": "..."} (exactly one item, at the end)

    Raises:
        ReportWriterError: if response is empty.
        LLMError:    if the API call fails.
    """
    user_msg = append_resume_directive(build_user_message(diagnosis), resumed_sections)
    sid_short = (session_id or "")[:8]
    if resumed_sections:
        logger.info(
            "[agent_b/in] session=%s resume from skipping %d sections: %s",
            sid_short, len(resumed_sections), sorted(resumed_sections.keys()),
        )
    logger.info("[agent_b/in] session=%s user_msg=\n%s", sid_short, user_msg)
    all_text = ""
    usage_sink: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    async for chunk in stream_chat_completion(
        system_prompt=REPORT_WRITER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.6,
        usage_sink=usage_sink,
    ):
        all_text += chunk
        yield chunk

    if not all_text.strip():
        raise ReportWriterError("run_stream: empty response")

    # Resume 模式：把已落库 section + LLM 新输出拼回完整 report，
    # 让 quality gate 仍能校验整体合规，写库也写完整版本。
    if resumed_sections:
        prefix_parts = [
            f"--{name}--\n{(resumed_sections[name] or '').strip()}\n"
            for name in SECTION_ORDER
            if name in resumed_sections
        ]
        combined_text = "".join(prefix_parts) + all_text
    else:
        combined_text = all_text

    try:
        warnings = check_report(combined_text, diagnosis)
    except QualityGateError as exc:
        logger.error("[agent_b/quality] hard fail session=%s: %s", sid_short, exc)
        raise ReportWriterError(f"quality_gate_failed: {exc}") from exc
    for w in warnings:
        logger.warning("[agent_b/quality] soft warning session=%s: %s", sid_short, w)

    logger.info(
        "[agent_b/out] session=%s chars=%d warnings=%d tokens=%d+%d resume=%d report_text=\n%s",
        sid_short, len(combined_text), len(warnings),
        usage_sink["prompt_tokens"], usage_sink["completion_tokens"],
        len(resumed_sections or {}),
        combined_text,
    )
    yield {
        "report_text": combined_text,
        "quality_warnings": [str(w) for w in warnings],
        "prompt_tokens": usage_sink["prompt_tokens"],
        "completion_tokens": usage_sink["completion_tokens"],
    }


async def run(
    diagnosis: dict,
    session_id: str | None = None,
    usage_sink: dict | None = None,
) -> str:
    """Run Agent B: diagnosis dict → plain text report.

    Args:
        usage_sink: 可选 dict — 若提供，会累加所有 attempt 的 token 用量到
                    {"prompt_tokens": int, "completion_tokens": int}。

    Returns:
        Full report text string.

    Raises:
        ReportWriterError: If response is empty after 2 attempts.
        LLMError:    If the API call itself fails.
    """
    base_msg = build_user_message(diagnosis)
    sid_short = (session_id or "")[:8]
    logger.info("[agent_b/in] session=%s user_msg=\n%s", sid_short, base_msg)
    retry_suffix = "\n\n【重试要求】请直接输出报告纯文本，不要输出 JSON 或代码围栏。"

    if usage_sink is not None:
        usage_sink.setdefault("prompt_tokens", 0)
        usage_sink.setdefault("completion_tokens", 0)

    last_quality_error: QualityGateError | None = None
    for attempt in range(2):
        content = base_msg if attempt == 0 else base_msg + retry_suffix
        per_call: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        raw = await chat_completion(
            system_prompt=REPORT_WRITER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            temperature=0.6,
            agent="agent_b",
            session_id=session_id,
            retry_index=attempt,
            usage_sink=per_call,
        )
        if usage_sink is not None:
            usage_sink["prompt_tokens"] += per_call["prompt_tokens"]
            usage_sink["completion_tokens"] += per_call["completion_tokens"]
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
        raise ReportWriterError(f"quality_gate_failed: {last_quality_error}") from last_quality_error
    raise ReportWriterError("Agent B returned empty text after 2 attempts")
