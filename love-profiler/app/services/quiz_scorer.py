"""
Quiz scorer — compute dimension scores from 30 user answers.
"""

import re


def _parse_score(score_str: str) -> dict:
    """Parse a score string into a structured result.

    '+2' / '+1' / '-1' / '-2'  →  {"numeric": int}
    'T1+2' / 'T2+1'            →  {"love_language": "T1", "value": int}
    """
    if not score_str:
        return {}
    m = re.match(r"(T\d)\+?(-?\d+)", score_str)
    if m:
        return {"love_language": m.group(1), "value": int(m.group(2))}
    try:
        return {"numeric": int(score_str.replace("+", ""))}
    except ValueError:
        return {}


def compute_scores(answers: list[dict], questions: list[dict]) -> dict:
    """Compute dimension scores from quiz answers.

    Args:
        answers: [{"question_id": str, "chosen_option": str}]
                 chosen_option is 'a'|'b'|'c'|'d'|'e' (lowercase)
        questions: full question list from Supabase

    Returns:
        {
            "attachment": int,           # -12 ~ +12
            "boundary": int,             # -12 ~ +12
            "conflict": int,             # -12 ~ +12
            "love_language": {
                "T1": int, "T2": int, "T3": int, "T4": int, "T5": int,
                "primary": str           # highest T key
            },
            "style": {
                "directness": int,       # S1: D5-Q01~03
                "sharing": int           # S2: D5-Q04~06
            }
        }
    """
    q_map = {q["question_id"]: q for q in questions}

    attachment = 0
    boundary = 0
    conflict = 0
    love_lang: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "T5": 0}
    directness = 0
    sharing = 0

    for answer in answers:
        qid = answer["question_id"]
        opt = answer["chosen_option"].lower()
        if qid not in q_map:
            continue
        q = q_map[qid]
        score_str = q.get(f"score_{opt}") or ""
        parsed = _parse_score(score_str)
        if not parsed:
            continue

        dimension = q["dimension"]
        signal_code = q.get("signal_code", "")

        if dimension == "依恋":
            attachment += parsed.get("numeric", 0)
        elif dimension == "边界":
            boundary += parsed.get("numeric", 0)
        elif dimension == "冲突":
            conflict += parsed.get("numeric", 0)
        elif dimension == "情感":
            t = parsed.get("love_language")
            v = parsed.get("value", 0)
            if t and t in love_lang:
                love_lang[t] += v
        elif dimension == "风格":
            val = parsed.get("numeric", 0)
            if signal_code == "S1":
                directness += val
            else:
                sharing += val

    primary = max(love_lang, key=lambda k: love_lang[k])
    return {
        "attachment": attachment,
        "boundary": boundary,
        "conflict": conflict,
        "love_language": {**love_lang, "primary": primary},
        "style": {"directness": directness, "sharing": sharing},
    }
