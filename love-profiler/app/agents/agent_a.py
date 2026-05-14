"""
Agent A — pure-Python scoring engine.
Processes answer_package (list[dict]) → structured diagnosis dict.
No LLM call; all computation is deterministic arithmetic.
"""

from __future__ import annotations

_D4_MAX: dict[str, int] = {"T1": 9, "T2": 8, "T3": 6, "T4": 9, "T5": 8}
_OPTION_TO_T: dict[str, str] = {"a": "T1", "b": "T2", "c": "T3", "d": "T4", "e": "T5"}


class AgentAError(Exception):
    """Raised when Agent A cannot complete scoring."""


def _intensity_interp(raw: int, dim: str) -> str:
    _hi  = {"D1": "secure",           "D2": "clear",           "D3": "healthy"}
    _mhi = {"D1": "moderate_secure",  "D2": "moderate_clear",  "D3": "moderate_healthy"}
    _mlo = {"D1": "moderate_anxious", "D2": "moderate_blurred","D3": "moderate_problematic"}
    _lo  = {"D1": "anxious",          "D2": "blurred",         "D3": "problematic"}
    if raw >= 6:  return _hi[dim]
    if raw >= 3:  return _mhi[dim]
    if raw >= -3: return "mixed"
    if raw >= -6: return _mlo[dim]
    return _lo[dim]


_D1_ABBR: dict[str, str] = {
    "secure": "S", "moderate_secure": "MS", "mixed": "MS",
    "moderate_anxious": "MA", "anxious": "A",
}
_D2_ABBR: dict[str, str] = {
    "clear": "CL", "moderate_clear": "CL", "mixed": "CL",
    "moderate_blurred": "BL", "blurred": "BL",
}
_D3_ABBR: dict[str, str] = {
    "healthy": "H", "moderate_healthy": "H", "mixed": "H",
    "moderate_problematic": "P", "problematic": "P",
}
_D1_ZH: dict[str, str] = {
    "secure": "安全型依恋", "moderate_secure": "中度安全依恋",
    "mixed": "混合型依恋", "moderate_anxious": "中度焦虑依恋", "anxious": "焦虑型依恋",
}
_D2_ZH: dict[str, str] = {
    "clear": "清晰边界", "moderate_clear": "中度清晰边界",
    "mixed": "混合边界", "moderate_blurred": "中度模糊边界", "blurred": "模糊边界",
}
_D3_ZH: dict[str, str] = {
    "healthy": "健康冲突", "moderate_healthy": "中度健康冲突",
    "mixed": "混合冲突", "moderate_problematic": "中度问题冲突", "problematic": "问题冲突",
}

_D5_CORNERS: dict[tuple[str, str], str] = {
    ("高直接", "高分享"): "直爽热情型",
    ("高直接", "低分享"): "清爽利落型",
    ("高含蓄", "高分享"): "碎碎念含蓄型",
    ("高含蓄", "低分享"): "安静含蓄型",
}

def _d5_quadrant(s1: int, s2: int) -> tuple[str, str, str, str]:
    """Return (S1_label, S2_label, quadrant, interpretation)."""
    s1_lbl = "高直接" if s1 > 3 else ("高含蓄" if s1 < -3 else "中直接")
    s2_lbl = "高分享" if s2 > 3 else ("低分享" if s2 < -3 else "中分享")
    if (s1_lbl, s2_lbl) in _D5_CORNERS:
        name = _D5_CORNERS[(s1_lbl, s2_lbl)]
        return s1_lbl, s2_lbl, f"{s1_lbl}×{s2_lbl}", name
    near_s1 = "高直接" if s1 >= 0 else "高含蓄"
    near_s2 = "高分享" if s2 >= 0 else "低分享"
    name = _D5_CORNERS[(near_s1, near_s2)]
    return s1_lbl, s2_lbl, f"{s1_lbl}×{s2_lbl}", f"{name}偏中"


def _compute_diagnosis(answers: list[dict], session_id: str | None = None) -> dict:
    q   = {a["question_id"]: a                for a in answers}
    sv  = {a["question_id"]: a["score_value"] for a in answers}
    opt = {a["question_id"]: a["selected_option"] for a in answers}

    def _s(qid: str) -> int: return sv.get(qid, 0)
    def _o(qid: str) -> str: return opt.get(qid, "")

    # ── D1 Attachment ──────────────────────────────────────────────────────────
    d1_raw = sum(_s(f"D1-Q{i:02d}") for i in range(1, 7))
    d1_interp = _intensity_interp(d1_raw, "D1")

    # ── D2 Boundary ────────────────────────────────────────────────────────────
    d2_raw = sum(_s(f"D2-Q{i:02d}") for i in range(1, 7))
    d2_interp = _intensity_interp(d2_raw, "D2")

    # ── D3 Conflict + pursue/avoid ─────────────────────────────────────────────
    d3_raw = sum(_s(f"D3-Q{i:02d}") for i in range(1, 7))
    d3_interp = _intensity_interp(d3_raw, "D3")
    pursue_avoid_subtype: str | None = q.get("D3-Q06", {}).get("score_meta", {}).get("pursue_avoid")

    # ── D4 Emotional Needs ────────────────────────────────────────────────────
    d4_raw: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "T5": 0}
    for qid in [f"D4-Q{i:02d}" for i in range(1, 7)]:
        a = q.get(qid)
        if a is None:
            continue
        ll = a.get("score_meta", {}).get("love_language")
        if ll in d4_raw:
            d4_raw[ll] += a["score_value"]

    d4_norm = {t: round(d4_raw[t] / _D4_MAX[t], 2) for t in d4_raw}
    top2 = sorted(d4_raw, key=lambda t: d4_norm[t], reverse=True)[:2]

    d4_q01 = q.get("D4-Q01", {})
    primary_choice: str | None = (
        d4_q01.get("score_meta", {}).get("love_language")
        or _OPTION_TO_T.get(_o("D4-Q01"))
    )
    alignment = bool(primary_choice and top2 and top2[0] == primary_choice)

    # ── D5 Expression Style ────────────────────────────────────────────────────
    s1_total = sum(_s(f"D5-Q{i:02d}") for i in range(1, 4))
    s2_total = sum(_s(f"D5-Q{i:02d}") for i in range(4, 7))
    s1_lbl, s2_lbl, quadrant, d5_interp = _d5_quadrant(s1_total, s2_total)

    # ── Cross-validation Layer 1 ───────────────────────────────────────────────
    q04, q05 = _s("D1-Q04"), _s("D1-Q05")
    imagination_reality_split = (q04 >= 1 and q05 <= -1) or (q04 <= -1 and q05 >= 1)
    cv_d1_s4 = "low" if imagination_reality_split else ("medium" if abs(q04 - q05) == 2 else "high")

    cv_d2_gap = _s("D2-Q01") >= 1 and _s("D2-Q05") <= -1

    d3q1, d3q5 = _s("D3-Q01"), _s("D3-Q05")
    if d3q1 >= 1 and d3q5 >= 1:
        cv_d3_res = "high"
    elif d3q1 >= 1 and d3q5 < 0:
        cv_d3_res = "low"
    else:
        cv_d3_res = "medium"

    # ── Cross-validation Layer 2 ───────────────────────────────────────────────
    cv_d2d3 = "aggressive_passive" if (_s("D2-Q01") == -2 and _s("D3-Q01") == -2) else "normal"
    cv_d1d5 = "anxious_avoidant_disguise" if (_s("D1-Q02") == -2 and _s("D5-Q05") == -2) else "normal"
    d5_s1_low_count = sum(1 for qid in ("D5-Q01", "D5-Q02", "D5-Q03") if _s(qid) <= -1)
    cv_d2d5 = "high" if (_s("D2-Q02") <= -1 and d5_s1_low_count >= 2) else "low"

    # ── Global Markers ────────────────────────────────────────────────────────
    d_flag_count = sum([_o("D1-Q01") == "d", _o("D2-Q05") == "d", _o("D3-Q03") == "d"])
    awareness_gap_global = d_flag_count >= 2

    pursue_avoid_role = {
        "a": "aware_breaker", "b": "stable", "c": "pursue", "d": "avoid",
    }.get(_o("D3-Q06"), "stable")

    d_non_d4 = [a for a in answers if not a["question_id"].startswith("D4-")]
    positive_count = sum(1 for a in d_non_d4 if a["score_value"] >= 1)
    stable_personality = positive_count / 24 >= 0.60
    love_lang_awareness = "aligned" if alignment else "misaligned"

    # ── Personality Typing ────────────────────────────────────────────────────
    # type_name / type_tagline 由 /quiz/submit 的 enrich 阶段从 base_love_type 表注入；
    # 这里仅给出非空兜底（轴名拼接），保证 agent_a 单独跑（如测试场景）也有可用值。
    type_code    = f"{_D1_ABBR[d1_interp]}-{_D2_ABBR[d2_interp]}-{_D3_ABBR[d3_interp]}"
    type_axis    = f"{_D1_ZH[d1_interp]} / {_D2_ZH[d2_interp]} / {_D3_ZH[d3_interp]}"
    type_name    = type_axis
    type_tagline = ""

    # ── Diagnostic Highlights ──────────────────────────────────────────────────
    highlights: list[dict] = []

    # Layer 1: 维度内交叉验证
    if imagination_reality_split:
        highlights.append({"code": "add-cv1-behavior-gap", "severity": "moderate",
            "finding": "想象情境题（Q04）与真实行为题（Q05）方向相反，存在社会期望偏差。"})
    if cv_d2_gap:
        highlights.append({"code": "add-cv1-pattern-blind", "severity": "high",
            "finding": "对单次越界事件能直接响应，但对持续性贬低选择忍耐，模式识别能力缺口明显。"})
    if cv_d3_res == "low":
        highlights.append({"code": "add-cv1-pressure-collapse", "severity": "moderate",
            "finding": "日常小摩擦能软启动表达，面对重大分歧时滑入指责，压力下表达带宽显著收窄。"})

    # Layer 2: 维度间交叉验证
    if cv_d2d3 == "aggressive_passive":
        highlights.append({"code": "add-cv2-aggr-passive", "severity": "high",
            "finding": "对真正越界事件无响应（边界模糊），却对低门槛小摩擦用攻击性语言开场——外强内弱。"})
    if cv_d1d5 == "anxious_avoidant_disguise":
        highlights.append({"code": "add-cv2-anxious-disguise", "severity": "moderate",
            "finding": "对对方不联系高度焦虑，但自己同样不主动——表面冷静独立，实为被迫傲娇。"})
    if cv_d2d5 == "high":
        highlights.append({"code": "add-cv2-self-dissolve", "severity": "high",
            "finding": "自我维持度低且表达含蓄，生活半径正向关系收缩，存在被关系吞噬的温水风险。"})

    # Layer 3: 全局复合诊断
    if awareness_gap_global:
        highlights.append({"code": "add-g-self-blame", "severity": "high",
            "finding": "在依恋、边界、冲突三个截然不同的情境中，均以自我归因作为第一反应，已是人格默认设置。"})
    if pursue_avoid_role == "pursue":
        highlights.append({"code": "add-g-pa-pursuer", "severity": "moderate",
            "finding": "在历史冲突中扮演追的角色——对方越冷越追，追的是即时安全感而非真正的答案。"})
    elif pursue_avoid_role == "avoid":
        highlights.append({"code": "add-g-pa-avoider", "severity": "moderate",
            "finding": "在历史冲突中扮演逃的角色——对方逼近时系统过载，用沉默或出走换缓冲时间。"})
    elif pursue_avoid_role == "aware_breaker":
        highlights.append({"code": "add-g-pa-aware", "severity": "info", "positive": True,
            "finding": "能识别追逃循环正在发生并主动喊停，是少数具备元认知观察力的稀缺特质。"})
    if stable_personality:
        highlights.append({"code": "add-g-stable", "severity": "info", "positive": True,
            "finding": f"D1/D2/D3/D5共24题中{positive_count}题得分≥+1（{round(positive_count / 24 * 100)}%），整体呈现稳定型反应模式。"})

    # D4: 爱的语言自我认知盲区
    if love_lang_awareness == "misaligned" and top2:
        highlights.append({"code": "add-g-love-blind", "severity": "moderate",
            "finding": f"主观首选爱的语言为 {primary_choice}，但场景题归一化后实际top1为 {top2[0]}，存在自我认知盲区。"})

    return {
        "type_code":    type_code,
        "type_name":    type_name,
        "type_tagline": type_tagline,
        "dimensions": {
            "D1": {"interp": d1_interp, "raw": d1_raw},
            "D2": {"interp": d2_interp, "raw": d2_raw},
            "D3": {"interp": d3_interp, "raw": d3_raw, "pursue_avoid": pursue_avoid_role},
            "D4": {
                "top2":       top2,
                "normalized": d4_norm,
                "declared":   primary_choice,
                "aligned":    alignment,
            },
            "D5": {
                "quadrant": quadrant,
                "style":    d5_interp,
                "s1":       s1_lbl,
                "s2":       s2_lbl,
                "s1_raw":   s1_total,
                "s2_raw":   s2_total,
            },
        },
        "highlights": highlights,
    }


async def run(
    answer_package: list[dict],
    session_id: str | None = None,
    question_set_version: str = "V2",
) -> dict:
    """Score answer package and return structured diagnosis dict.

    Raises:
        AgentAError: If answer_package is empty.
    """
    if not answer_package:
        raise AgentAError("Empty answer package")
    result = _compute_diagnosis(answer_package, session_id=session_id)
    result["question_set_version"] = question_set_version
    return result
