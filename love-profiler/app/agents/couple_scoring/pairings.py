"""组合配对规则（维度无关全局信号）。高摩擦来自组合而非差距大小。"""
from __future__ import annotations

HIGH = 60.0
_RULES = [("demand_withdraw", "confront", "withdraw"),
          ("anxious_avoidant", "attach_anxiety", "attach_avoid")]


def _cross(scores: dict, x: str, y: str) -> bool:
    a, b = scores.get("A", {}), scores.get("B", {})
    return (a.get(x, 0) > HIGH and b.get(y, 0) > HIGH) or \
           (b.get(x, 0) > HIGH and a.get(y, 0) > HIGH)


def pairings(scores: dict) -> list[str]:
    return [flag for flag, x, y in _RULES if _cross(scores, x, y)]
