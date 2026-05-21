"""
Answer package builder — assembles a structured answer package from raw quiz answers.

Each item in the returned list contains everything the scoring engine needs to perform
dimension scoring without re-querying the questions table.
"""

import re


_D3_Q06_PURSUE_AVOID = {
    "c": "pursue",
    "d": "avoid",
}


def _parse_score(score_str: str) -> tuple[int, dict]:
    """Parse a score string into (score_value, score_meta).

    '+2' / '-1'         →  (int, {})
    'T1+2' / 'T3+2'     →  (int, {"love_language": "T1"})
    Returns (0, {}) for empty or unrecognised strings.
    """
    if not score_str:
        return 0, {}
    m = re.match(r"(T\d)\+?(-?\d+)", score_str)
    if m:
        return int(m.group(2)), {"love_language": m.group(1)}
    try:
        return int(score_str.replace("+", "")), {}
    except ValueError:
        return 0, {}


def build_answer_package(
    answers: list[dict],
    questions: list[dict],
) -> list[dict]:
    """Build a list of enriched answer items from raw answers + questions.

    Args:
        answers:   [{"question_id": str, "chosen_option": str}]
                   chosen_option is 'a'|'b'|'c'|'d'|'e' (lowercase).
        questions: Full question list fetched from Supabase.

    Returns:
        List of dicts, one per valid answer::

            {
                "question_id":    str,    # e.g. "D1-Q01"
                "selected_option": str,   # e.g. "a"
                "score_value":    int,    # e.g. +2, -1
                "score_meta":     dict,   # e.g. {} or {"pursue_avoid": "pursue"}
            }

        Unknown question_ids are silently skipped.
    """
    q_map = {q["question_id"]: q for q in questions}
    package = []

    for answer in answers:
        qid = answer["question_id"]
        opt = answer.get("chosen_option", "").lower()
        q = q_map.get(qid)
        if q is None:
            continue

        score_str = q.get(f"score_{opt}") or ""
        score_value, score_meta = _parse_score(score_str)

        # D3-Q06 special rule: mark pursue/avoid subtype on options C and D
        if qid == "D3-Q06" and opt in _D3_Q06_PURSUE_AVOID:
            score_meta = {"pursue_avoid": _D3_Q06_PURSUE_AVOID[opt]}

        package.append({
            "question_id":    qid,
            "selected_option": opt,
            "score_value":    score_value,
            "score_meta":     score_meta,
        })

    return package
