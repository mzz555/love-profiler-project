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

import asyncio
import logging
import pathlib
import re

from app.services.llm_client import (
    LLMError,
    TransientLLMError,
    chat_completion,
    stream_chat_completion,
)
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

# run_stream 流式韧性参数：
# - stream attempts：原调用 + 1 次重试 = 2（间隔 1s）
# - 仍失败且未 yield 任何 chunk → 降级到非流式 chat_completion（自带 3 次内置重试）
# - 降级路径模拟流式输出：每 8 字一段、间隔 40ms，前端体验上像稍慢的流式
_MAX_STREAM_ATTEMPTS = 2
_STREAM_RETRY_DELAY_SECONDS = 1.0
_FALLBACK_CHUNK_SIZE = 8
_FALLBACK_CHUNK_DELAY_SECONDS = 0.04

# T1-T5 中文名兜底映射（D4 自我认知盲区场景：declared 不在 top2 时，
# diagnosis.D4_details 只含 top2 两条，查不到 declared 的中文名，
# 会把 "T1" 这种内部代码原样塞进 prompt → LLM 把方括号占位符原样输出）。
# 这里的静态映射与 base_D4_type 表一致，但用于盲区兜底翻译。
_D4_FALLBACK_NAMES = {
    "T1": "言语肯定",
    "T2": "精心时刻",
    "T3": "用心小惊喜",
    "T4": "服务行动",
    "T5": "身体接触",
}


class ReportWriterError(Exception):
    """Raised when the report writer fails to return meaningful text."""


def build_user_message(diagnosis: dict) -> str:
    """Render diagnosis as natural-language input for the LLM.

    All static knowledge (type-name dictionary, D4 language definitions, D5
    quadrant guides) lives in DB tables (base_love_type / base_D4_type /
    base_D5_quadrant) and is injected by the enrich step in /quiz/submit
    as `type_detail`, `D4_details`, `D5_guide`. We then render only the
    user's slice here, so the model spends its attention on the user's
    actual data instead of rescanning multi-row dictionaries every call.
    """
    lines: list[str] = []

    type_code    = diagnosis.get("type_code", "")
    type_name    = diagnosis.get("type_name", "")
    type_tagline = diagnosis.get("type_tagline", "")
    type_detail  = diagnosis.get("type_detail", "")

    lines.append("# 用户类型")
    lines.append(f"- 类型代码：{type_code}")
    lines.append(f"- 类型名（用作报告标题）：{type_name}")
    if type_tagline:
        lines.append(f"- 副标题：{type_tagline}")
    if type_detail:
        lines.append(f"- 类型锚定句（开篇画像必须以此为起点展开）：{type_detail}")
    lines.append("")

    dims = diagnosis.get("dimensions", {}) or {}
    dim_meta = diagnosis.get("dimension_meta", {}) or {}
    seg_decode = diagnosis.get("segment_decode", []) or []
    # 用 dimension 作 key 索引 segment_decode，让 D1/D2/D3 行能直接取到中文标签
    seg_by_dim = {s.get("dimension"): s for s in seg_decode}

    def _meta_line(code: str) -> str:
        m = dim_meta.get(code, {}) or {}
        name = m.get("name_cn", "")
        desc = m.get("description", "")
        if name and desc:
            return f"- {code} {name}（{desc}）"
        return f"- {code}"

    def _seg_line(code: str) -> str:
        seg = seg_by_dim.get(code, {}) or {}
        label = seg.get("label_cn", "")
        if not label:
            return ""
        healthy = "健康端" if seg.get("is_healthy") else "问题端"
        return f"    · 段落标签：{label}（{healthy}）"

    lines.append("# 五维度结果（D1-D5 全部展开）")

    # D1/D2/D3：去 interp 英文标签，用 label_cn 中文 + description
    lines.append(_meta_line("D1"))
    if (line := _seg_line("D1")):
        lines.append(line)

    lines.append(_meta_line("D2"))
    if (line := _seg_line("D2")):
        lines.append(line)

    lines.append(_meta_line("D3"))
    if (line := _seg_line("D3")):
        lines.append(line)
    d3 = dims.get("D3", {}) or {}
    pa = d3.get("pursue_avoid", "")
    if pa and pa != "stable":
        lines.append(f"    · 追逃角色：{pa}（须在该段融入追/逃视角）")

    # D4：把 T1/T2 代码替换成中文类型名，避免非中文进 prompt
    d4 = dims.get("D4", {}) or {}
    top2     = d4.get("top2", []) or []
    aligned  = d4.get("aligned", True)
    declared = d4.get("declared", "")
    d4_details = diagnosis.get("D4_details", []) or []
    d4_name_by_code = {d.get("code", ""): d.get("name", "") for d in d4_details}
    # 优先用 DB 注入的 D4_details（含 detail 描述），缺失时落静态映射兜底。
    # 关键：declared 在盲区场景下永远不在 top2，DB 详情不会含它 ⇒ 必走兜底。
    top2_names = [d4_name_by_code.get(c) or _D4_FALLBACK_NAMES.get(c, c) for c in top2]
    declared_name = d4_name_by_code.get(declared) or _D4_FALLBACK_NAMES.get(declared, declared)

    lines.append(_meta_line("D4"))
    # 用中文顿号拼接而非 Python list 字面量 ['x','y']，避免给 LLM 灌方括号/引号
    # （Python repr 形式会让 LLM 误以为占位符语法是允许的输出形式）
    lines.append(f"    · top2 偏好：{'、'.join(top2_names)}")
    for d in d4_details:
        lines.append(f"    · {d.get('name', '')}：{d.get('detail', '')}")
    if not aligned and declared_name and top2_names:
        lines.append(
            f"    · 注意自我认知盲区：用户主动选择的是「{declared_name}」，但行为得分指向「{top2_names[0]}」；"
            "必须在 D4 段后追加「自我认知盲区」子段"
        )

    # D5：加 description 保持一致；style/quadrant 已是中文
    d5 = dims.get("D5", {}) or {}
    style    = d5.get("style", "")
    quadrant = d5.get("quadrant", "")
    guide    = diagnosis.get("D5_guide", "")
    lines.append(_meta_line("D5"))
    if style or quadrant:
        lines.append(f"    · 风格象限：{style}（{quadrant}）")
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
                f"{i}. 标题：{h.get('name_cn', '')} | is_positive={h.get('is_positive', False)}"
            )
            lines.append(f"   写作种子：{h.get('report_seed', '')}")

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
    """Stream the report writer: yields text chunks in real time, then a final dict.

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
            "[report_writer/in] session=%s resume from skipping %d sections: %s",
            sid_short, len(resumed_sections), sorted(resumed_sections.keys()),
        )
    logger.info("[report_writer/in] session=%s user_msg=\n%s", sid_short, user_msg)
    all_text = ""
    usage_sink: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

    # ── 流式韧性：重试 1 次 + 降级到非流式（chat_completion 自带 3 次内置重试）─
    # 中途已 yield chunk 后失败：不能重试也不能降级（前端已收到部分文本，补不回去）。
    chunks_yielded = 0
    last_stream_exc: TransientLLMError | None = None
    for attempt in range(_MAX_STREAM_ATTEMPTS):
        try:
            async for chunk in stream_chat_completion(
                system_prompt=REPORT_WRITER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.6,
                usage_sink=usage_sink,
            ):
                chunks_yielded += 1
                all_text += chunk
                yield chunk
            last_stream_exc = None
            break
        except TransientLLMError as exc:
            last_stream_exc = exc
            if chunks_yielded > 0:
                logger.error(
                    "[report_writer/stream] session=%s 中途失败 attempt=%d 已 yield %d 字符 (%d chunks)，无法重试/降级：%s",
                    sid_short, attempt, len(all_text), chunks_yielded, exc,
                )
                raise
            if attempt + 1 < _MAX_STREAM_ATTEMPTS:
                logger.warning(
                    "[report_writer/stream] session=%s attempt=%d 流式失败，%.1fs 后重试：%s",
                    sid_short, attempt, _STREAM_RETRY_DELAY_SECONDS, exc,
                )
                await asyncio.sleep(_STREAM_RETRY_DELAY_SECONDS)
            # 否则跳出循环，外面走降级

    if last_stream_exc is not None:
        # 所有 stream attempts 都挂了且没 yield 任何 chunk → 降级到非流式
        logger.warning(
            "[report_writer/stream] session=%s stream 重试 %d 次全部失败，降级到非流式 chat_completion：%s",
            sid_short, _MAX_STREAM_ATTEMPTS, last_stream_exc,
        )
        try:
            raw = await chat_completion(
                system_prompt=REPORT_WRITER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.6,
                agent="agent_b",
                session_id=session_id,
                usage_sink=usage_sink,
            )
        except (TransientLLMError, LLMError) as exc2:
            logger.error(
                "[report_writer/stream] session=%s 降级 chat_completion 也失败：%s",
                sid_short, exc2,
            )
            raise
        if not raw.strip():
            raise ReportWriterError("fallback chat_completion empty") from last_stream_exc
        # 模拟流式输出：按固定切片 + 短 sleep，前端体验上像稍慢的流式
        for i in range(0, len(raw), _FALLBACK_CHUNK_SIZE):
            piece = raw[i:i + _FALLBACK_CHUNK_SIZE]
            all_text += piece
            yield piece
            await asyncio.sleep(_FALLBACK_CHUNK_DELAY_SECONDS)
        logger.info(
            "[report_writer/stream] session=%s 降级完成 chars=%d tokens=%d+%d",
            sid_short, len(raw),
            usage_sink["prompt_tokens"], usage_sink["completion_tokens"],
        )

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
        logger.error("[report_writer/quality] hard fail session=%s: %s", sid_short, exc)
        raise ReportWriterError(f"quality_gate_failed: {exc}") from exc
    for w in warnings:
        logger.warning("[report_writer/quality] soft warning session=%s: %s", sid_short, w)

    logger.info(
        "[report_writer/out] session=%s chars=%d warnings=%d tokens=%d+%d resume=%d report_text=\n%s",
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
    """Run the report writer: diagnosis dict → plain text report.

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
    logger.info("[report_writer/in] session=%s user_msg=\n%s", sid_short, base_msg)
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
                "[report_writer/quality] attempt=%d session=%s 质量门未通过：%s",
                attempt, sid_short, exc,
            )
            continue
        for w in warnings:
            logger.warning("[report_writer/quality] soft warning session=%s: %s", sid_short, w)
        logger.info(
            "[report_writer/out] session=%s chars=%d warnings=%d report_text=\n%s",
            sid_short, len(raw), len(warnings), raw,
        )
        return raw

    if last_quality_error is not None:
        raise ReportWriterError(f"quality_gate_failed: {last_quality_error}") from last_quality_error
    raise ReportWriterError("report writer returned empty text after 2 attempts")
