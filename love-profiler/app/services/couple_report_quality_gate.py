"""Couple 报告卡片质检门（对标 report_quality_gate 的硬失败/软警告双层）。"""
from __future__ import annotations

import re

BANNED = ("匹配度", "合适吗", "不合适", "注定", "分数低", "及格", "不及格", "般配")
_NEGATIVE = ("缺陷", "糟", "失败", "不足", "病态")


class CoupleQualityGateError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        super().__init__(f"{kind}: {detail}" if detail else kind)


def _all_text(cards: dict) -> str:
    op = cards.get("opening", {})
    parts = [op.get("headline", ""), op.get("body", "")]
    for k in ("how_to_read", "strengths", "next_steps", "closing"):
        parts.append(cards.get(k, {}).get("body", ""))
    parts += cards.get("next_steps", {}).get("invitations", [])
    for c in cards.get("blindspot_cards", []):
        parts += [c.get("title", ""), c.get("body", ""), c.get("talk_prompt", "")]
    for ls in cards.get("landscape", []):
        parts += [ls.get("title", ""), ls.get("body", "")]
    return "\n".join(parts)


def _fact_referenced(fact: str, body: str) -> bool:
    # 优先：narrative_fact 里「」内的语义锚点才是"忠实转述"的核心，
    # 而开头是字母 A/B + 模板词（LLM 本就该用昵称替换、不会逐字复现）。
    if (m := re.search(r"「(.+?)」", fact)):
        return m.group(1) in body
    # 无锚点的泛化 fact（如"存在明显落差"）：退回宽松的开头 4-gram 检查。
    key = fact.strip()
    if len(key) < 4:
        return key in body
    return any(key[i:i + 4] in body for i in range(min(len(key) - 3, 6)))


def check_cards(cards: dict, briefing: dict) -> list[str]:
    if (hit := [w for w in BANNED if w in _all_text(cards)]):
        raise CoupleQualityGateError("banned_word", str(hit))
    dims = {d["dimension_id"]: d for d in briefing.get("dimensions", [])}
    for c in cards.get("blindspot_cards", []):
        d = dims.get(c.get("dimension_id"), {})
        if d.get("complementary") and (neg := [w for w in _NEGATIVE if w in c.get("body", "")]):
            raise CoupleQualityGateError("negative_on_complementary", f"{c['dimension_id']}:{neg}")
    warnings: list[str] = []
    for c in cards.get("blindspot_cards", []):
        fact = (dims.get(c.get("dimension_id"), {}).get("blindspot") or {}).get("narrative_fact", "")
        if fact and not _fact_referenced(fact, c.get("body", "")):
            warnings.append(f"fact_not_referenced:{c.get('dimension_id')}")
    return warnings
