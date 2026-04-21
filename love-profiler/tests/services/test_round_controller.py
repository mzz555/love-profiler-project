"""
Tests for round_controller — pure functions, no I/O.
"""
import pytest
from app.services.round_controller import get_round_directive, is_final_round


class TestGetRoundDirective:
    def test_round_1_contains_ice_breaking_keyword(self):
        directive = get_round_directive(1)
        assert "破冰" in directive

    def test_round_7_contains_end_keyword(self):
        directive = get_round_directive(7)
        assert "结束" in directive

    def test_round_7_requires_json_output(self):
        directive = get_round_directive(7)
        assert "JSON" in directive

    def test_round_beyond_7_returns_round_7_directive(self):
        assert get_round_directive(8) == get_round_directive(7)
        assert get_round_directive(100) == get_round_directive(7)

    def test_all_rounds_1_to_7_return_nonempty_string(self):
        for r in range(1, 8):
            result = get_round_directive(r)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_round_3_contains_insight_keyword(self):
        directive = get_round_directive(3)
        assert "洞察" in directive or "性格" in directive

    def test_each_round_directive_is_unique(self):
        directives = [get_round_directive(r) for r in range(1, 7)]
        assert len(set(directives)) == len(directives), "Rounds 1-6 must each have unique directives"


class TestIsFinalRound:
    def test_round_7_is_final(self):
        assert is_final_round(7) is True

    def test_round_8_is_final(self):
        assert is_final_round(8) is True

    def test_round_6_is_not_final(self):
        assert is_final_round(6) is False

    def test_round_1_is_not_final(self):
        assert is_final_round(1) is False

    def test_round_0_is_not_final(self):
        assert is_final_round(0) is False
