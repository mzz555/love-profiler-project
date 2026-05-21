"""Agent B 报告质量门测试（Phase A.2）。

覆盖：
- 完整报告通过
- 缺必备 section / 字数不达标 → QualityGateError
- highlights 非空时 Highlight 段必备；空时跳过
- 软警告：Title 缺 type_name、Highlight 段未引用 report_seed

Section 标记名以 docs/agent-b-system-prompt.md 为权威：
Title / Opening / Attachment / Boundary / Conflict / Language / Style / Highlight / Suggestion
"""

import pytest

from app.services.report_quality_gate import (
    MIN_SECTION_CHARS,
    REQUIRED_SECTIONS,
    QualityGateError,
    check_report,
    parse_sections,
)


def _diagnosis() -> dict:
    return {
        "type_code": "MS-CL-H",
        "type_name": "中度安全·清晰边界·健康冲突",
        "highlights": [
            {
                "code": "add-g-stable",
                "name_cn": "稳定型反应",
                "is_positive": True,
                "report_seed": "整体稳定的反应模式",
            }
        ],
    }


def _section(name: str, body_chars: int) -> str:
    return f"--{name}--\n" + ("内" * body_chars) + "\n"


def _full_report(diagnosis: dict, *, highlight_body: str | None = None) -> str:
    """拼一份满足所有硬约束的报告文本。"""
    title = f"--Title--\n《{diagnosis['type_name']}》\n"
    parts = [
        title,
        _section("Opening",    MIN_SECTION_CHARS["Opening"]),
        _section("Attachment", MIN_SECTION_CHARS["Attachment"]),
        _section("Boundary",   MIN_SECTION_CHARS["Boundary"]),
        _section("Conflict",   MIN_SECTION_CHARS["Conflict"]),
        _section("Language",   MIN_SECTION_CHARS["Language"]),
        _section("Style",      MIN_SECTION_CHARS["Style"]),
    ]
    hls = diagnosis.get("highlights") or []
    if highlight_body is None:
        if hls:
            seed_key = hls[0]["report_seed"][:4]
            highlight_body_text = seed_key + "扩写" + ("展" * (MIN_SECTION_CHARS["Highlight"] - len(seed_key) - 2))
        else:
            highlight_body_text = "占位" * 60
    else:
        highlight_body_text = highlight_body
    parts.append(f"--Highlight--\n{highlight_body_text}\n")
    parts.append(_section("Suggestion", MIN_SECTION_CHARS["Suggestion"]))
    return "".join(parts)


def test_parse_sections_extracts_all_markers():
    text = "--Title--\nA\n--Opening--\nB\n--Attachment--\nC"
    out = parse_sections(text)
    assert out["Title"]      == "A"
    assert out["Opening"]    == "B"
    assert out["Attachment"] == "C"


def test_parse_sections_handles_text_before_first_marker():
    """首个标记前的内容应被忽略。"""
    text = "前导垃圾\n--Title--\nA"
    out = parse_sections(text)
    assert "Title" in out
    assert out["Title"] == "A"


def test_check_report_passes_complete_report():
    d = _diagnosis()
    warnings = check_report(_full_report(d), d)
    assert warnings == []


def test_check_report_empty_text_raises():
    with pytest.raises(QualityGateError) as exc_info:
        check_report("", _diagnosis())
    assert exc_info.value.kind == "empty_report"


def test_check_report_whitespace_only_raises():
    with pytest.raises(QualityGateError) as exc_info:
        check_report("   \n  ", _diagnosis())
    assert exc_info.value.kind == "empty_report"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_check_report_missing_required_section(section):
    d = _diagnosis()
    full = _full_report(d)
    broken = full.replace(f"--{section}--", "--ZZZRemoved--")
    with pytest.raises(QualityGateError) as exc_info:
        check_report(broken, d)
    assert exc_info.value.kind == "missing_section"
    assert exc_info.value.section == section


def test_check_report_too_short_section_raises():
    d = _diagnosis()
    full = _full_report(d)
    short = full.replace(
        _section("Attachment", MIN_SECTION_CHARS["Attachment"]),
        "--Attachment--\n短\n",
    )
    with pytest.raises(QualityGateError) as exc_info:
        check_report(short, d)
    assert exc_info.value.kind == "too_short"
    assert exc_info.value.section == "Attachment"


def test_check_report_highlight_required_when_highlights_present():
    d = _diagnosis()
    full = _full_report(d)
    no_hl = full.replace("--Highlight--", "--ZZZSkip--")
    with pytest.raises(QualityGateError) as exc_info:
        check_report(no_hl, d)
    assert exc_info.value.section == "Highlight"


def test_check_report_highlight_optional_when_diagnosis_has_no_highlights():
    """diagnosis.highlights 为空 → Highlight 段缺失也通过。"""
    d = _diagnosis()
    d["highlights"] = []
    full = _full_report(d)
    no_hl = full.replace("--Highlight--", "--ZZZSkip--")
    check_report(no_hl, d)


def test_check_report_warns_when_title_missing_type_name():
    d = _diagnosis()
    full = _full_report(d)
    no_name = full.replace(f"《{d['type_name']}》", "无关标题")
    warnings = check_report(no_name, d)
    kinds = {w.kind for w in warnings}
    assert "type_name_missing_in_title" in kinds


def test_check_report_warns_when_highlight_seed_not_referenced():
    d = _diagnosis()
    text = _full_report(d, highlight_body="完全无关的填充内容" + ("X" * 200))
    warnings = check_report(text, d)
    kinds = {w.kind for w in warnings}
    assert "seed_not_referenced" in kinds


def test_check_report_no_warnings_when_seed_referenced():
    d = _diagnosis()
    text = _full_report(d)
    warnings = check_report(text, d)
    assert not any(w.kind == "seed_not_referenced" for w in warnings)
