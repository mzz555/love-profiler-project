"""
Content safety — lightweight keyword-based screening for user input and LLM output.
Blocks obviously harmful content before it reaches the LLM or the user.
"""

import re

# Patterns that indicate content that must be blocked.
# Compiled at import time for performance.
BANNED_PATTERNS: list[str] = [
    "自杀",
    "自残",
    "杀了",
    "杀人",
    "法轮功",
    "天安门事件",
    r"\bkill\b",
    r"\bsuicide\b",
    r"\bterror\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]


class ContentSafetyError(Exception):
    """Raised when content fails safety screening."""


def is_safe(text: str) -> bool:
    """Return False if the text matches any banned pattern; True otherwise."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return False
    return True
