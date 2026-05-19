import json
from unittest.mock import patch

import pytest


MOCK_QUESTIONS = [
    {
        "question_id": f"D{(i-1)//6 + 1}-Q{(i-1)%6 + 1:02d}",
        "dimension": ["依恋", "边界", "冲突", "情感", "风格"][(i-1)//6],
        "signal_code": "S1",
        "signal_name": "测试信号",
        "question_type": "强度型",
        "stem": f"题干{i}",
        "sort_order": i,
        "option_a": "选项A", "score_a": "+2",
        "option_b": "选项B", "score_b": "+1",
        "option_c": "选项C", "score_c": "-1",
        "option_d": "选项D", "score_d": "-2",
        "option_e": None, "score_e": None,
        "version": "V2", "notes": None,
    }
    for i in range(1, 31)
]


def test_quiz_start_returns_questions(client, auth_headers):
    with patch("app.services.supabase_client._fetch_questions_sync",
               return_value=MOCK_QUESTIONS):
        resp = client.post("/quiz/start", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "assessment_id" in data
    assert len(data["questions"]) == 30


def test_quiz_submit_runs_agent_a(client, auth_headers, db_session):
    with patch("app.services.supabase_client._fetch_questions_sync",
               return_value=MOCK_QUESTIONS):
        start = client.post("/quiz/start", headers=auth_headers)
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    answers = [
        {"question_id": q["question_id"], "chosen_option": "a"}
        for q in MOCK_QUESTIONS
    ]

    # quiz/submit 的 enrich 阶段需要从 base_* 表查类型名/D4 释义/D5 写作方向/highlights；
    # 内存 SQLite 没这些表，所以为四个 fetch_* 函数提供测试 mock。
    mock_love_type = {
        "type_code": "S-CL-H", "type_name": "稳重的航标",
        "img_path": "/img/scl-h.png",
        "detail": "你像一座稳重的航标，关系里给得出稳定。",  # ≥10 字符以满足 Diagnosis.type_anchor 校验
        "tagline": "副标题",
    }
    mock_d4_details = [
        {"code": "T1", "name": "言语肯定", "detail": "夸奖、认可"},
        {"code": "T2", "name": "精心时刻", "detail": "专注陪伴"},
    ]
    mock_d5_guide = {"quadrant": "高直接×高分享", "style_name": "直爽热情型",
                     "description": "s1>3 且 s2>3", "guide": "写作方向"}
    mock_segment_decode = [
        {"dimension": "D1", "code": "S",  "label_cn": "安全型依恋",   "is_healthy": True},
        {"dimension": "D2", "code": "CL", "label_cn": "清晰边界",     "is_healthy": True},
        {"dimension": "D3", "code": "H",  "label_cn": "健康冲突模式", "is_healthy": True},
    ]
    # all-positive 答案下 agent_a 可能输出 add-g-stable / add-g-pa-aware 等高光；
    # 用 side_effect 按入参 codes 动态生成行，避免漏覆盖任意 code 导致 502。
    def fake_highlights_by_codes(codes):
        return [{
            "code": c, "name_cn": f"mock-{c}", "severity": "info", "is_positive": False,
            "report_seed": "种子", "interp_path": "路径", "trigger_condition": "条件",
        } for c in codes]

    with patch("app.services.supabase_client._fetch_questions_sync", return_value=MOCK_QUESTIONS), \
         patch("app.services.supabase_client._fetch_love_type_sync", return_value=mock_love_type), \
         patch("app.services.supabase_client._fetch_d4_details_sync", return_value=mock_d4_details), \
         patch("app.services.supabase_client._fetch_d5_guide_sync", return_value=mock_d5_guide), \
         patch("app.services.supabase_client._fetch_segment_decode_sync", return_value=mock_segment_decode), \
         patch("app.services.supabase_client._fetch_highlights_by_codes_sync", side_effect=fake_highlights_by_codes):
        resp = client.post(
            "/quiz/submit",
            json={"session_id": session_id, "answers": answers},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "analyzed"

    from app.models.assessment import Assessment
    db_session.expire_all()
    assessment = db_session.query(Assessment).filter(
        Assessment.session_id == session_id
    ).first()
    assert assessment is not None
    assert assessment.status == "analyzed"
    assert assessment.answers_json is not None
    assert assessment.diagnosis_json is not None
    diagnosis = json.loads(assessment.diagnosis_json)
    assert diagnosis["type_code"] == "S-CL-H"
    assert "dimensions" in diagnosis
    assert "highlights" in diagnosis


def test_quiz_submit_wrong_session_returns_404(client, auth_headers):
    with patch("app.services.supabase_client._fetch_questions_sync",
               return_value=MOCK_QUESTIONS):
        resp = client.post(
            "/quiz/submit",
            json={"session_id": "nonexistent-session", "answers": []},
            headers=auth_headers,
        )
    assert resp.status_code == 404


def test_quiz_submit_schema_validation_fails_when_d5_guide_missing(
    client, auth_headers, db_session
):
    """enrich 阶段查不到 D5_guide（fetch_d5_guide 返回 None）→ Diagnosis 校验拒绝写库。"""
    with patch("app.services.supabase_client._fetch_questions_sync",
               return_value=MOCK_QUESTIONS):
        start = client.post("/quiz/start", headers=auth_headers)
    session_id = start.json()["session_id"]
    answers = [{"question_id": q["question_id"], "chosen_option": "a"} for q in MOCK_QUESTIONS]

    mock_love_type = {
        "type_code": "S-CL-H", "type_name": "稳重的航标",
        "img_path": "/img/scl-h.png",
        "detail": "你像一座稳重的航标，关系里给得出稳定。",
        "tagline": "",
    }
    mock_d4_details = [
        {"code": "T1", "name": "言语肯定", "detail": "夸奖、认可"},
        {"code": "T2", "name": "精心时刻", "detail": "专注陪伴"},
    ]
    mock_segment_decode = [
        {"dimension": "D1", "code": "S",  "label_cn": "安全型依恋",   "is_healthy": True},
        {"dimension": "D2", "code": "CL", "label_cn": "清晰边界",     "is_healthy": True},
        {"dimension": "D3", "code": "H",  "label_cn": "健康冲突模式", "is_healthy": True},
    ]
    def fake_highlights_by_codes(codes):
        return [{
            "code": c, "name_cn": f"mock-{c}", "severity": "info", "is_positive": False,
            "report_seed": "种子", "interp_path": "路径", "trigger_condition": "条件",
        } for c in codes]

    with patch("app.services.supabase_client._fetch_questions_sync", return_value=MOCK_QUESTIONS), \
         patch("app.services.supabase_client._fetch_love_type_sync", return_value=mock_love_type), \
         patch("app.services.supabase_client._fetch_d4_details_sync", return_value=mock_d4_details), \
         patch("app.services.supabase_client._fetch_d5_guide_sync", return_value=None), \
         patch("app.services.supabase_client._fetch_segment_decode_sync", return_value=mock_segment_decode), \
         patch("app.services.supabase_client._fetch_highlights_by_codes_sync", side_effect=fake_highlights_by_codes):
        resp = client.post(
            "/quiz/submit",
            json={"session_id": session_id, "answers": answers},
            headers=auth_headers,
        )

    assert resp.status_code == 502
    assert "诊断数据不完整" in resp.json()["detail"]

    from app.models.assessment import Assessment
    db_session.expire_all()
    assessment = db_session.query(Assessment).filter(
        Assessment.session_id == session_id
    ).first()
    assert assessment is not None
    assert assessment.status == "pending"
    assert assessment.diagnosis_json is None
