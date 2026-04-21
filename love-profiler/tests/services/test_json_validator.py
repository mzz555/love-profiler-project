"""
Tests for json_validator — extract and validate Agent1's 5-dimension JSON output.
All test data uses synthetic values only.
"""
import pytest
from app.services.json_validator import (
    extract_and_validate,
    extract_json_block,
    clean_json,
    validate_shape,
    REQUIRED_FIELDS,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_JSON_TEXT = """\
感谢你今天的分享，祝你早日找到属于自己的幸福。
```json
{
  "separation_anxiety": {"signal": "high",          "weight": "strong", "evidence": "反复查看手机"},
  "intimacy_comfort":   {"signal": "low_avoidance",  "weight": "weak",   "evidence": "自然接受亲密"},
  "conflict_pattern":   {"signal": "attack",         "weight": "strong", "evidence": "用你总是开头"},
  "needs_expression":   {"signal": "implicit",       "weight": "weak",   "evidence": "通过冷战暗示"},
  "attribution":        {"signal": "self_blame",     "weight": "strong", "evidence": "觉得是自己不够好"}
}
```
"""

BARE_JSON_TEXT = (
    '测评结束了。\n'
    '{"separation_anxiety":{"signal":"low","weight":"weak","evidence":"不在意"},'
    '"intimacy_comfort":{"signal":"high_avoidance","weight":"strong","evidence":"越近越退"},'
    '"conflict_pattern":{"signal":"withdraw","weight":"weak","evidence":"沉默关机"},'
    '"needs_expression":{"signal":"explicit","weight":"weak","evidence":"直接说出"},'
    '"attribution":{"signal":"event","weight":"strong","evidence":"归因具体事件"}}'
)

_VALID_DICT = {
    "separation_anxiety": {"signal": "high", "weight": "strong", "evidence": "x"},
    "intimacy_comfort":   {"signal": "low_avoidance", "weight": "weak", "evidence": "x"},
    "conflict_pattern":   {"signal": "collaborative", "weight": "strong", "evidence": "x"},
    "needs_expression":   {"signal": "explicit", "weight": "weak", "evidence": "x"},
    "attribution":        {"signal": "event", "weight": "strong", "evidence": "x"},
}


# ---------------------------------------------------------------------------
# extract_and_validate
# ---------------------------------------------------------------------------

class TestExtractAndValidate:
    def test_valid_fenced_json_returns_dict_and_clean_text(self):
        summary, clean = extract_and_validate(VALID_JSON_TEXT)
        assert summary is not None
        assert "separation_anxiety" in summary
        assert "```" not in clean

    def test_valid_bare_json_returns_dict(self):
        summary, _ = extract_and_validate(BARE_JSON_TEXT)
        assert summary is not None

    def test_missing_field_returns_none(self):
        text = '```json\n{"separation_anxiety": {"signal":"high","weight":"strong","evidence":"x"}}\n```'
        summary, _ = extract_and_validate(text)
        assert summary is None

    def test_completely_missing_json_returns_none(self):
        summary, clean = extract_and_validate("没有任何JSON内容的纯文字回复。")
        assert summary is None
        assert clean == "没有任何JSON内容的纯文字回复。"

    def test_clean_text_excludes_json_block(self):
        summary, clean = extract_and_validate(VALID_JSON_TEXT)
        assert "separation_anxiety" not in clean
        assert "感谢你今天的分享" in clean

    def test_all_five_fields_present_in_result(self):
        summary, _ = extract_and_validate(VALID_JSON_TEXT)
        for field in REQUIRED_FIELDS:
            assert field in summary

    def test_malformed_json_returns_none(self):
        bad = "```json\n{bad json here,,,}\n```"
        summary, _ = extract_and_validate(bad)
        assert summary is None

    def test_invalid_weight_value_returns_none(self):
        bad = """\
```json
{
  "separation_anxiety": {"signal": "high",         "weight": "medium", "evidence": "x"},
  "intimacy_comfort":   {"signal": "low_avoidance","weight": "weak",   "evidence": "x"},
  "conflict_pattern":   {"signal": "attack",       "weight": "strong", "evidence": "x"},
  "needs_expression":   {"signal": "implicit",     "weight": "weak",   "evidence": "x"},
  "attribution":        {"signal": "event",        "weight": "strong", "evidence": "x"}
}
```"""
        summary, _ = extract_and_validate(bad)
        assert summary is None


# ---------------------------------------------------------------------------
# validate_shape
# ---------------------------------------------------------------------------

class TestValidateShape:
    def test_valid_dict_passes(self):
        assert validate_shape(_VALID_DICT) is True

    def test_missing_signal_key_fails(self):
        bad = {**_VALID_DICT, "separation_anxiety": {"weight": "strong", "evidence": "x"}}
        assert validate_shape(bad) is False

    def test_missing_evidence_key_fails(self):
        bad = {**_VALID_DICT, "intimacy_comfort": {"signal": "low_avoidance", "weight": "weak"}}
        assert validate_shape(bad) is False

    def test_invalid_weight_fails(self):
        bad = {**_VALID_DICT, "conflict_pattern": {"signal": "attack", "weight": "medium", "evidence": "x"}}
        assert validate_shape(bad) is False

    def test_non_dict_dimension_fails(self):
        bad = {**_VALID_DICT, "needs_expression": "implicit"}
        assert validate_shape(bad) is False


# ---------------------------------------------------------------------------
# extract_json_block
# ---------------------------------------------------------------------------

class TestExtractJsonBlock:
    def test_extracts_fenced_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_block(text)
        assert result == '{"key": "value"}'

    def test_extracts_bare_json_object(self):
        text = 'some text {"key": "value"} more text'
        result = extract_json_block(text)
        assert '{"key": "value"}' in result

    def test_returns_none_when_no_json(self):
        result = extract_json_block("pure text no json")
        assert result is None

    def test_fenced_takes_priority_over_bare(self):
        text = '{"bare": true}\n```json\n{"fenced": true}\n```'
        result = extract_json_block(text)
        assert '"fenced"' in result


# ---------------------------------------------------------------------------
# clean_json
# ---------------------------------------------------------------------------

class TestCleanJson:
    def test_removes_trailing_comma_before_brace(self):
        dirty = '{"key": "value",}'
        result = clean_json(dirty)
        assert result == '{"key": "value"}'

    def test_removes_trailing_comma_before_bracket(self):
        dirty = '{"arr": [1, 2,]}'
        result = clean_json(dirty)
        assert result == '{"arr": [1, 2]}'

    def test_valid_json_unchanged(self):
        valid = '{"key": "value"}'
        result = clean_json(valid)
        assert result == valid
