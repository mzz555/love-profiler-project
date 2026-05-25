"""
Admin table configuration — TABLE_CONFIG + startup validation.

所有 SQL 标识符在启动时正则校验为安全字符，_query_table 等用 f-string
拼标识符进 SQL，靠这个不变量挡 SQL 注入。
"""

import re

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TABLE_CONFIG: dict[str, dict] = {
    "users": {
        "pk": "id",
        "search_cols": ["openid"],
        "editable_fields": [],
        "truncate_cols": [],
        "created_at_col": "created_at",
        "list_cols": ["id", "openid", "created_at"],
    },
    "assessments": {
        "pk": "id",
        "search_cols": ["personality_type", "status", "session_id"],
        "editable_fields": ["status"],
        "truncate_cols": ["signals", "diagnosis_json", "report_text",
                          "answers_json", "report_json", "dimension_scores", "summary"],
        "created_at_col": "created_at",
        "list_cols": ["id", "user_id", "session_id", "personality_type",
                      "status", "mode", "created_at"],
    },
    "orders": {
        "pk": "id",
        "search_cols": ["out_trade_no", "status"],
        "editable_fields": [],
        "truncate_cols": [],
        "created_at_col": "created_at",
        "list_cols": ["id", "user_id", "assessment_id", "out_trade_no",
                      "amount", "status", "created_at"],
    },
    "ai_call_logs": {
        "pk": "id",
        "search_cols": ["agent", "status", "session_id"],
        "editable_fields": [],
        "truncate_cols": ["messages_json", "response_preview"],
        "created_at_col": "ts",
        "list_cols": ["id", "ts", "agent", "session_id", "model",
                      "status", "duration_ms", "total_tokens", "retry_index"],
    },
    "report_quality_audit": {
        "pk": "id",
        "search_cols": ["judge_model", "prompt_version"],
        "editable_fields": [],
        "truncate_cols": ["raw_output", "summary"],
        "created_at_col": "created_at",
        "list_cols": ["id", "created_at", "assessment_id", "judge_model",
                      "prompt_version", "overall_score",
                      "coherence_score", "readability_score", "factual_score",
                      "duration_ms"],
    },
    "base_love_type": {
        "pk": "id",
        "search_cols": ["type_code", "type_name"],
        "editable_fields": ["type_name", "tagline"],
        "truncate_cols": [],
        "created_at_col": None,
        "list_cols": ["id", "type_code", "type_name", "tagline"],
    },
    "highlights": {
        "pk": "code",
        "search_cols": ["code", "name_cn"],
        "editable_fields": ["name_cn", "is_positive"],
        "truncate_cols": ["report_seed"],
        "created_at_col": None,
        "list_cols": ["code", "layer", "involved_dims",
                      "is_positive", "name_cn", "sort_order"],
    },
    "base_dimension_meta": {
        "pk": "code",
        "search_cols": ["code", "name_cn"],
        "editable_fields": ["name_cn", "description", "radar_label"],
        "truncate_cols": [],
        "created_at_col": None,
        "list_cols": ["code", "name_cn", "description", "score_model",
                      "radar_label", "sort_order"],
    },
    "base_segment_decode": {
        "pk": "id",
        "search_cols": ["dimension", "code", "label_cn"],
        "editable_fields": ["label_cn", "description", "score_range"],
        "truncate_cols": [],
        "created_at_col": None,
        "list_cols": ["id", "dimension", "code", "label_cn",
                      "score_range", "is_healthy"],
    },
    "base_D4_type": {
        "pk": "id",
        "search_cols": ["love_languages_code", "love_languages_name"],
        "editable_fields": ["love_languages_name", "love_languages_detail"],
        "truncate_cols": ["love_languages_detail"],
        "created_at_col": None,
        "list_cols": ["id", "love_languages_code", "love_languages_name"],
    },
    "base_D5_quadrant": {
        "pk": "quadrant",
        "search_cols": ["quadrant", "style_name"],
        "editable_fields": ["style_name", "description", "guide"],
        "truncate_cols": ["guide", "description"],
        "created_at_col": None,
        "list_cols": ["quadrant", "style_name", "sort_order"],
    },
    "questions": {
        "pk": "question_id",
        "search_cols": ["dimension", "signal_code", "stem"],
        "editable_fields": [],
        "truncate_cols": ["stem", "notes"],
        "created_at_col": None,
        "list_cols": ["question_id", "dimension", "signal_code",
                      "signal_name", "question_type", "sort_order"],
    },
}


def validate_config() -> None:
    """启动时校验所有表名/列名仅含安全字符。不安全标识符直接进程崩溃。"""
    for table, cfg in TABLE_CONFIG.items():
        if not _SAFE_IDENT.match(table):
            raise RuntimeError(f"TABLE_CONFIG 表名不安全: {table!r}")
        idents = [cfg["pk"]] + list(cfg.get("search_cols", [])) \
                 + list(cfg.get("editable_fields", [])) \
                 + list(cfg.get("list_cols", []))
        if cfg.get("created_at_col"):
            idents.append(cfg["created_at_col"])
        for ident in idents:
            if not _SAFE_IDENT.match(ident):
                raise RuntimeError(f"TABLE_CONFIG[{table!r}] 列名不安全: {ident!r}")


validate_config()
