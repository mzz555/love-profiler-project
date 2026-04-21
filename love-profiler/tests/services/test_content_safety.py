"""
Tests for content_safety — lightweight input/output content screening.
"""

import pytest

from app.services.content_safety import (
    is_safe,
    ContentSafetyError,
    BANNED_PATTERNS,
)


# ---------------------------------------------------------------------------
# is_safe — normal inputs
# ---------------------------------------------------------------------------


def test_is_safe_returns_true_for_normal_text():
    assert is_safe("我喜欢和朋友一起出去玩") is True


def test_is_safe_returns_true_for_empty_string():
    assert is_safe("") is True


def test_is_safe_returns_true_for_whitespace_only():
    assert is_safe("   ") is True


def test_is_safe_returns_true_for_english_text():
    assert is_safe("I love spending time with my partner.") is True


def test_is_safe_returns_true_for_emotional_content():
    assert is_safe("有时候我会感到很孤独，不知道该怎么办") is True


# ---------------------------------------------------------------------------
# is_safe — banned content
# ---------------------------------------------------------------------------


def test_is_safe_returns_false_for_self_harm_keyword():
    assert is_safe("我想自杀") is False


def test_is_safe_returns_false_for_violence_keyword():
    assert is_safe("我要杀了他") is False


def test_is_safe_returns_false_for_political_sensitive():
    assert is_safe("法轮功万岁") is False


def test_is_safe_case_insensitive():
    # Ensure detection is not bypassed by mixed case for ASCII keywords
    assert is_safe("KILL everyone") is False


def test_is_safe_returns_false_when_banned_pattern_is_substring():
    assert is_safe("今天我很郁闷，感觉想自杀一样") is False


# ---------------------------------------------------------------------------
# BANNED_PATTERNS is non-empty
# ---------------------------------------------------------------------------


def test_banned_patterns_is_non_empty():
    assert len(BANNED_PATTERNS) > 0


# ---------------------------------------------------------------------------
# ContentSafetyError is importable and is an Exception subclass
# ---------------------------------------------------------------------------


def test_content_safety_error_is_exception():
    err = ContentSafetyError("test")
    assert isinstance(err, Exception)
