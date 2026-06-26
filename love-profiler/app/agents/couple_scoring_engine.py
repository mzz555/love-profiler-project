"""Couple scoring engine — 纯算入口。双方作答 → 契约 JSON（无 LLM/DB）。"""
from __future__ import annotations

from app.agents.couple_scoring.blindspot import blindspot
from app.agents.couple_scoring.normalize import aggregate_side
from app.agents.couple_scoring.pairings import pairings
from app.agents.couple_scoring.salience import assign_salience_ranks, gap_level, salience
from app.agents.couple_scoring.supercluster import supercluster_scores
from app.agents.couple_scoring.triplet import triplet
from app.schemas.couple_briefing import CoupleBriefing
from app.services import couple_registry as reg

_TOP_N = 3


class CoupleScoringError(Exception):
    """引擎无法完成计算时抛出。"""


def _build_dim(dim, s_A, s_B, p_A2B, p_B2A) -> dict:
    calib = reg.get_calibration(dim.id)
    t = triplet(s_A, s_B, dim)
    bs = (blindspot(s_A, s_B, p_A2B, p_B2A, dim)
          if dim.apply_prediction and p_A2B is not None and p_B2A is not None else None)
    return {
        "dimension_id": dim.id, "cluster": dim.cluster,
        "layer": "interpretation" if calib["calibrated_relevant"] else "topic_only",
        "calibrated_relevant": calib["calibrated_relevant"], "effect_size": calib["effect_size"],
        "complementary": dim.complementary, "level_only": dim.level_only,
        "apply_prediction": dim.apply_prediction,
        "gap": t["gap"], "gap_level": gap_level(t["gap"], calib["gap_thresholds"]),
        "direction": t["direction"], "levels": t["levels"],
        "blindspot": bs, "salience": salience(t["gap"], bs, calib), "salience_rank": -1,
    }


async def run(answer_pkg: dict, session_id: str | None = None, question_set_version: str = "v1") -> dict:
    if not answer_pkg or not answer_pkg.get("A") or not answer_pkg.get("B"):
        raise CoupleScoringError("empty package")
    A, B = answer_pkg["A"], answer_pkg["B"]
    sk = answer_pkg.get("skipped", {})
    skip = set(sk.get("A", [])) | set(sk.get("B", []))
    dims: list[dict] = []
    scores = {"A": {}, "B": {}}
    for dim in reg.all_dimensions():
        if dim.id in skip:
            continue
        s_A, s_B = aggregate_side(dim, A["self"]), aggregate_side(dim, B["self"])
        if s_A is None or s_B is None:
            continue
        scores["A"][dim.id], scores["B"][dim.id] = s_A, s_B
        p_A2B = aggregate_side(dim, A["predicted"]) if dim.apply_prediction else None
        p_B2A = aggregate_side(dim, B["predicted"]) if dim.apply_prediction else None
        dims.append(_build_dim(dim, s_A, s_B, p_A2B, p_B2A))
    assign_salience_ranks(dims)
    top = sorted((d for d in dims if d["blindspot"] and d["blindspot"]["exists"]),
                 key=lambda d: d["blindspot"]["accuracy_error"], reverse=True)
    briefing = {
        "session_id": session_id or "",
        "overview": {
            "top_blindspots": [d["dimension_id"] for d in top[:_TOP_N]],
            "supercluster_scores": supercluster_scores(dims),
            "high_friction_pairings": pairings(scores),
            "complementary_strengths": [d["dimension_id"] for d in dims
                                        if d["complementary"] and d["gap_level"] == "large"],
        },
        "dimensions": dims, "question_set_version": question_set_version,
    }
    CoupleBriefing.model_validate(briefing)
    return briefing
