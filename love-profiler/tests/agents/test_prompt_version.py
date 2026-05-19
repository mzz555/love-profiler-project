"""Agent B prompt_version 解析测试（Phase A.3）。"""

from app.agents.agent_b import (
    PROMPT_VERSION,
    REPORT_VERSION,
    _parse_prompt_version,
)


def test_parse_prompt_version_picks_up_html_comment():
    raw = "<!-- prompt-version: 2.0 -->\n## 角色\n…"
    assert _parse_prompt_version(raw) == "2.0"


def test_parse_prompt_version_tolerates_extra_whitespace():
    raw = "<!--   prompt-version:   3.1-beta   -->\n…"
    assert _parse_prompt_version(raw) == "3.1-beta"


def test_parse_prompt_version_defaults_to_zero_when_missing():
    assert _parse_prompt_version("没有注解的纯 prompt 文本") == "0"


def test_module_constants_resolved_at_import():
    """PROMPT_VERSION 应在 import 时解析为非空字符串，REPORT_VERSION 是 int。"""
    assert isinstance(PROMPT_VERSION, str)
    assert PROMPT_VERSION != ""
    assert isinstance(REPORT_VERSION, int)
    assert REPORT_VERSION >= 1


def test_current_prompt_version_is_2():
    """守门测试：当前 docs/agent-b-system-prompt.md 的版本应为 2.0；
    改 prompt 时同步更新此处和文件头。"""
    assert PROMPT_VERSION == "2.0"
