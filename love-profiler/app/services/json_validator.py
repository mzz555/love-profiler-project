"""
JSON validator — extract and validate Agent1's final-round 5-dimension JSON summary.
Handles common LLM formatting mistakes with regex-based cleanup.
"""

import json
import re

REQUIRED_FIELDS = [
    "separation_anxiety",
    "intimacy_comfort",
    "conflict_pattern",
    "needs_expression",
    "attribution",
]

_VALID_WEIGHTS = {"strong", "weak"}

_FALLBACK_REPLY = "测评完成，正在为你生成专属报告..."


def extract_and_validate(text: str) -> tuple[dict | None, str]:
    """Extract JSON from model reply text and validate 5-dimension nested structure.

    Returns:
        (validated_dict, clean_text) on success.
        (None, original_text) on failure.
    """
    json_str = extract_json_block(text)
    if not json_str:
        return None, text

    json_str = clean_json(json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None, text

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return None, text

    if not validate_shape(data):
        return None, text

    clean_text = remove_json_block(text)
    return data, clean_text


def validate_shape(data: dict) -> bool:
    """Verify each dimension has signal, weight (strong|weak), and evidence."""
    for field in REQUIRED_FIELDS:
        dim = data.get(field)
        if not isinstance(dim, dict):
            return False
        if "signal" not in dim or "weight" not in dim or "evidence" not in dim:
            return False
        if dim["weight"] not in _VALID_WEIGHTS:
            return False
    return True


def extract_json_block(text: str) -> str | None:
    """Extract a JSON object from fenced code block or bare object.

    Fenced ```json ... ``` blocks take priority over bare objects.
    """
    match = re.search(r"```json?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0).strip()

    return None


def clean_json(json_str: str) -> str:
    """Fix common LLM JSON formatting errors (trailing commas)."""
    json_str = re.sub(r",\s*}", "}", json_str)
    json_str = re.sub(r",\s*]", "]", json_str)
    return json_str


def remove_json_block(text: str) -> str:
    """Strip JSON block from text, returning the conversational part."""
    cleaned = re.sub(r"```json?\s*[\s\S]*?```", "", text).strip()
    if cleaned != text.strip():
        return cleaned if cleaned else _FALLBACK_REPLY
    cleaned = re.sub(r"\{[\s\S]*\}", "", text).strip()
    return cleaned if cleaned else _FALLBACK_REPLY
