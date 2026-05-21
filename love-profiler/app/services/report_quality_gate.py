"""report writer 报告输出质量门（Phase A.2）。

在 LLM 输出完毕后做一道硬校验：
- 必备 Section 是否齐全（缺一即 fail）
- 每段字数是否达标（防 LLM 应付式填充）

外加软警告（不 block，仅日志记录）：
- Title 段是否引用 type_name
- Highlight 段是否引用 report_seed 关键词
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Section 标记名来自 docs/agent-b-system-prompt.md 的"输出格式"段。
# D1-D5 五维度在 prompt 中以语义名出现（Attachment/Boundary/Conflict/Language/Style），
# 不是字面 D1/D2 — 切勿混淆。
REQUIRED_SECTIONS = [
    "Title", "Opening",
    "Attachment", "Boundary", "Conflict", "Language", "Style",
    "Suggestion",
]

# Highlight 段是可选必备：当 diagnosis.highlights 非空时必须存在，否则可省略

MIN_SECTION_CHARS: dict[str, int] = {
    "Title":       4,
    "Opening":     80,
    "Attachment":  80,
    "Boundary":    80,
    "Conflict":    80,
    # Language/Style 是 D4/D5 辅助维度，prompt 目标 80-120/80-100 字，
    # 质量门留 40 字弹性 ⇒ 阈值降到 40。参见 [[feedback-quality-gate-prompt-pair]]
    "Language":    40,
    "Style":       40,
    "Highlight":   100,
    "Suggestion":  60,
}


@dataclass
class QualityWarning:
    kind: str
    section: str
    detail: str = ""

    def __str__(self) -> str:
        base = f"{self.kind}/{self.section}"
        return f"{base}: {self.detail}" if self.detail else base


class QualityGateError(Exception):
    """硬质量门失败：section 缺失或字数不达标。"""

    def __init__(self, kind: str, section: str, value: Any = None) -> None:
        self.kind = kind
        self.section = section
        self.value = value
        if value is not None:
            super().__init__(f"{kind}: section={section} value={value}")
        else:
            super().__init__(f"{kind}: section={section}")


_SECTION_RE = re.compile(r"--([A-Za-z]+)--")


def parse_sections(text: str) -> dict[str, str]:
    """根据 --Section-- 标记拆分文本，返回 {section_name: body}。

    多次出现同名 section 会合并；首个标记前的内容被忽略。
    """
    parts: dict[str, list[str]] = {}
    current: str | None = None
    pos = 0

    for m in _SECTION_RE.finditer(text):
        if current is not None:
            parts.setdefault(current, []).append(text[pos:m.start()])
        current = m.group(1)
        pos = m.end()

    if current is not None:
        parts.setdefault(current, []).append(text[pos:])

    return {k: "\n".join(v).strip() for k, v in parts.items()}


def check_report(text: str, diagnosis: dict) -> list[QualityWarning]:
    """运行质量门校验。

    Args:
        text: report writer 输出的完整报告文本
        diagnosis: 富化后的 diagnosis 字典（用于关键词审计）

    Returns:
        软警告列表（不致命；调用方可写日志/指标）

    Raises:
        QualityGateError: section 缺失或字数不达标
    """
    if not text or not text.strip():
        raise QualityGateError("empty_report", "*")

    sections = parse_sections(text)

    for req in REQUIRED_SECTIONS:
        if req not in sections:
            raise QualityGateError("missing_section", req)
        body_len = len(sections[req])
        if body_len < MIN_SECTION_CHARS[req]:
            raise QualityGateError("too_short", req, body_len)

    highlights = diagnosis.get("highlights", []) or []
    if highlights:
        if "Highlight" not in sections:
            raise QualityGateError("missing_section", "Highlight")
        hl_len = len(sections["Highlight"])
        if hl_len < MIN_SECTION_CHARS["Highlight"]:
            raise QualityGateError("too_short", "Highlight", hl_len)

    warnings: list[QualityWarning] = []

    type_name = diagnosis.get("type_name", "")
    if type_name and type_name not in sections.get("Title", ""):
        warnings.append(QualityWarning(
            "type_name_missing_in_title", "Title",
            detail=f"期望出现 {type_name!r}",
        ))

    if highlights and "Highlight" in sections:
        hl_body = sections["Highlight"]
        missing = [
            h.get("name_cn") or h.get("code", "")
            for h in highlights
            if h.get("report_seed") and not _seed_appears(h["report_seed"], hl_body)
        ]
        if missing:
            warnings.append(QualityWarning(
                "seed_not_referenced", "Highlight",
                detail=f"未引用：{missing}",
            ))

    return warnings


def _seed_appears(seed: str, body: str) -> bool:
    """用 4 字滑窗判断 seed 关键词是否出现在 body 中。

    seed 通常是一句话，LLM 可能改写，所以只要任一 4 字子串命中即视为引用。
    """
    key = (seed or "").strip()
    if not key:
        return True
    if len(key) < 4:
        return key in body
    span = key[:8]
    for i in range(len(span) - 3):
        if span[i:i + 4] in body:
            return True
    return False
