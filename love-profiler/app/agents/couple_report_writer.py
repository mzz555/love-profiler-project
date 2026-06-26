"""Couple report writer — briefing(+names) → 7 段报告 JSON。盲区卡片 LLM，其余模板。"""
from __future__ import annotations

import json
import pathlib

from app.services.couple_report_quality_gate import check_cards
from app.services.llm_client import chat_completion

_PROMPT_FILE = pathlib.Path(__file__).parents[2] / "docs" / "couple-report-system-prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")
_DEFAULT_NAMES = {"a": "你", "b": "对方"}
_PAIRING_TEMPLATES = {
    "demand_withdraw": "你们可能出现「一个想立刻谈、一个想先躲开」的节奏差，值得各自说说舒服的方式。",
    "anxious_avoidant": "你们一个更需要靠近确认、一个更需要空间喘息，这不是对错，是不同的安全感来源。",
}


class CoupleReportWriterError(Exception):
    pass


def build_card_user_message(dim: dict, names: dict) -> str:
    bs = dim.get("blindspot") or {}
    return "\n".join([
        f"# 盲区维度：{dim['dimension_id']}",
        f"- 昵称：A={names.get('a')} B={names.get('b')}；本卡点名 who_misjudged={bs.get('who_misjudged', '')}",
        f"- 中性事实（必须忠实转述）：{bs.get('narrative_fact', '')}",
        f"- 落差档位：{dim.get('gap_level', '')}；方向：{dim.get('direction', {})}",
        '请按系统要求输出 JSON：{"title":"...","body":"...","talk_prompt":"..."}',
    ])


def _parse_card(raw: str, dim_id: str) -> dict:
    try:
        obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise CoupleReportWriterError(f"card parse failed: {dim_id}") from exc
    return {"dimension_id": dim_id, "title": obj.get("title", ""),
            "body": obj.get("body", ""), "talk_prompt": obj.get("talk_prompt", "")}


def _landscape(briefing: dict) -> list[dict]:
    out = []
    for sc, val in briefing["overview"].get("supercluster_scores", {}).items():
        if val is None:          # MVP 判决层全 None → 该项暂略
            continue
        out.append({"supercluster": sc, "title": sc, "body": f"这个方面你们的话题热度约为 {val}。"})
    return out


async def run(briefing: dict, session_id: str | None = None, names: dict | None = None) -> dict:
    names = names or _DEFAULT_NAMES
    ov = briefing["overview"]
    dims = {d["dimension_id"]: d for d in briefing["dimensions"]}
    cards = []
    for dim_id in ov["top_blindspots"]:
        if (dim := dims.get(dim_id)) is None:
            continue
        raw = await chat_completion(system_prompt=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_card_user_message(dim, names)}],
            temperature=0.6, agent="couple_report", session_id=session_id)
        cards.append(_parse_card(raw, dim_id))
    if not cards:
        raise CoupleReportWriterError("no blindspot cards generated")
    invitations = [c["talk_prompt"] for c in cards if c.get("talk_prompt")][:4]
    closing = "差异本身不是问题，几乎所有情侣都有。这份报告是对话的起点，不替代专业咨询。"
    if ov.get("high_friction_pairings"):
        closing = "\n".join(_PAIRING_TEMPLATES.get(f, "") for f in ov["high_friction_pairings"]) + "\n" + closing
    report = {
        "opening": {"headline": "这是你们俩一起读的一份对话指南",
                    "body": "下面挑出了你们最值得聊的几个地方，不做评判，只帮你们更懂彼此。"},
        "how_to_read": {"body": "它基于你们各自的作答和「互相猜对方」，看你们在哪不太一样、"
                                "以及哪些地方你们以为一样其实不一样。"},
        "blindspot_cards": cards,
        "landscape": _landscape(briefing),
        "strengths": {"body": "你们在一些方面的差异更像互补，是关系里的弹性来源。"
                      if ov.get("complementary_strengths") else ""},
        "next_steps": {"body": "找个轻松的时候，也许可以从下面这些聊起：", "invitations": invitations},
        "closing": {"body": closing},
    }
    report["quality_warnings"] = check_cards(report, briefing)
    return report
