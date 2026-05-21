"""Diagnosis pydantic schema 测试（Phase A.1）。

校验对象是 /quiz/submit enrich 之后、写库之前的 diagnosis 字典。
覆盖核心约束：必备字段、维度齐全、D4 top2 ↔ D4_details 一致、D5 quadrant ↔ guide 一致、
highlights 必须含 DB 富化字段。
"""

import pytest
from pydantic import ValidationError

from app.schemas.diagnosis import Diagnosis


def _valid_diagnosis() -> dict:
    """返回一份完整的 enriched diagnosis 字典，模拟 quiz/submit 写库前形态。"""
    return {
        "type_code": "MS-CL-H",
        "type_name": "中度安全·清晰边界·健康冲突",
        "type_tagline": "稳定友好的副标题",
        "type_detail": "你在亲密关系里通常表现得很稳定。",
        "dimensions": {
            "D1": {"interp": "moderate_secure", "raw": 4},
            "D2": {"interp": "clear", "raw": 7},
            "D3": {"interp": "healthy", "raw": 5, "pursue_avoid": "stable"},
            "D4": {
                "top2": ["T1", "T2"],
                "normalized": {"T1": 0.8, "T2": 0.6, "T3": 0.3, "T4": 0.5, "T5": 0.4},
                "declared": "T1",
                "aligned": True,
            },
            "D5": {
                "quadrant": "高直接×高分享",
                "style": "直爽热情型",
                "s1": "高直接",
                "s2": "高分享",
                "s1_raw": 5,
                "s2_raw": 6,
            },
        },
        "D4_details": [
            {"code": "T1", "name": "言语肯定", "detail": "T1 释义"},
            {"code": "T2", "name": "精心时刻", "detail": "T2 释义"},
        ],
        "D5_guide": "直爽热情型的写作示范：信息密度高，主动表达需求。",
        "D5_style_name": "直爽热情型",
        "segment_decode": [
            {"dimension": "D1", "code": "MS", "label_cn": "中度安全型依恋", "is_healthy": True},
            {"dimension": "D2", "code": "CL", "label_cn": "清晰边界",     "is_healthy": True},
            {"dimension": "D3", "code": "H",  "label_cn": "健康冲突模式", "is_healthy": True},
        ],
        "dimension_meta": {
            "D1": {"code": "D1", "name_cn": "依恋类型", "description": "遭遇关系不确定性时依恋系统的激活模式"},
            "D2": {"code": "D2", "name_cn": "边界意识", "description": "关系中保持独立自我、识别越界行为的能力"},
            "D3": {"code": "D3", "name_cn": "冲突处理", "description": "关系摩擦时的表达方式与修复主动性"},
            "D4": {"code": "D4", "name_cn": "情感需求", "description": "五种爱的语言的相对偏好排序"},
            "D5": {"code": "D5", "name_cn": "亲密风格", "description": "直接性与分享欲两个独立子面"},
        },
        "highlights": [
            {
                "code": "add-g-stable",
                "name_cn": "稳定型反应",
                "is_positive": True,
                "report_seed": "整体稳定的反应模式",
            }
        ],
        "question_set_version": "V2",
    }


def test_valid_diagnosis_passes():
    Diagnosis.model_validate(_valid_diagnosis())


def test_diagnosis_requires_type_code():
    data = _valid_diagnosis()
    data["type_code"] = ""
    with pytest.raises(ValidationError, match="type_code"):
        Diagnosis.model_validate(data)


def test_diagnosis_requires_type_name():
    data = _valid_diagnosis()
    data["type_name"] = ""
    with pytest.raises(ValidationError, match="type_name"):
        Diagnosis.model_validate(data)


def test_diagnosis_requires_type_detail_min_length():
    """type_detail 来自 base_love_type.detail，是开篇画像的"锚"，过短视为 enrich 失败。"""
    data = _valid_diagnosis()
    data["type_detail"] = "短"
    with pytest.raises(ValidationError, match="type_detail"):
        Diagnosis.model_validate(data)


@pytest.mark.parametrize("dim", ["D1", "D2", "D3", "D4", "D5"])
def test_diagnosis_requires_all_five_dimensions(dim):
    data = _valid_diagnosis()
    del data["dimensions"][dim]
    with pytest.raises(ValidationError, match=dim):
        Diagnosis.model_validate(data)


def test_d4_top2_must_match_d4_details():
    """top2=['T1','T2'] 但 D4_details 只覆盖 T1 → 校验失败。"""
    data = _valid_diagnosis()
    data["D4_details"] = [{"code": "T1", "name": "言语肯定", "detail": "T1 释义"}]
    with pytest.raises(ValidationError, match="T2"):
        Diagnosis.model_validate(data)


def test_d5_quadrant_must_have_guide():
    """D5.quadrant 非空时 D5_guide 不可为空（enrich 阶段没查到 base_D5_quadrant 行）。"""
    data = _valid_diagnosis()
    data["D5_guide"] = ""
    with pytest.raises(ValidationError, match="D5_guide"):
        Diagnosis.model_validate(data)


def test_d5_no_quadrant_skips_guide_check():
    """D5 quadrant 为空（Agent A 兜底）时 D5_guide 也可为空。"""
    data = _valid_diagnosis()
    data["dimensions"]["D5"]["quadrant"] = ""
    data["D5_guide"] = ""
    Diagnosis.model_validate(data)


def test_highlights_must_have_report_seed():
    data = _valid_diagnosis()
    data["highlights"][0].pop("report_seed")
    with pytest.raises(ValidationError, match="report_seed"):
        Diagnosis.model_validate(data)


def test_highlights_empty_list_allowed():
    """无 highlights 命中的稳定用户也算合法。"""
    data = _valid_diagnosis()
    data["highlights"] = []
    Diagnosis.model_validate(data)


def test_d4_details_must_be_non_empty():
    """D4 任何用户都至少有 top1，所以 D4_details 不应为空。"""
    data = _valid_diagnosis()
    data["D4_details"] = []
    with pytest.raises(ValidationError, match="D4_details"):
        Diagnosis.model_validate(data)


def test_extra_fields_allowed_for_forward_compat():
    """允许 enrich 阶段透传额外字段（如未来新增的 enriched 数据）。"""
    data = _valid_diagnosis()
    data["future_field"] = {"foo": "bar"}
    Diagnosis.model_validate(data)
