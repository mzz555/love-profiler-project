# tests/api/test_admin_api.py
"""Admin API 单元测试。

注意：测试环境使用 SQLite in-memory，Supabase 表（base_love_type 等）不存在。
      权限/字段校验逻辑不依赖表是否存在，可正常测试。
      业务表（users/assessments/orders/ai_call_logs）由 SQLAlchemy 自动建表，可正常查询。
"""
import os
import pytest


# ── 权限测试 ──────────────────────────────────────────
def test_overview_without_auth_returns_404(client, monkeypatch):
    """未认证请求应返回 404（隐藏管理面板存在性）。"""
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.get("/admin/api/overview")
    assert resp.status_code == 404


def test_table_list_without_auth_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.get("/admin/api/users")
    assert resp.status_code == 404


def test_table_update_without_auth_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.put("/admin/api/base_love_type/1", json={"type_name": "x"})
    assert resp.status_code == 404


# ── 表名校验 ──────────────────────────────────────────
def test_table_list_unknown_table_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/nonexistent_table")
    assert resp.status_code == 404


def test_table_detail_unknown_table_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/nonexistent_table/1")
    assert resp.status_code == 404


def test_table_update_unknown_table_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.put("/admin/api/nonexistent_table/1", json={"x": "y"})
    assert resp.status_code == 404


# ── 字段白名单校验 ────────────────────────────────────
def test_update_readonly_table_returns_403(client, monkeypatch):
    """users 表为只读，PUT 应返回 403。"""
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.put("/admin/api/users/1", json={"openid": "hacked"})
    assert resp.status_code == 403


def test_update_invalid_field_returns_400(client, monkeypatch):
    """base_love_type 不允许编辑 img_path。"""
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.put("/admin/api/base_love_type/1", json={"img_path": "hack.png"})
    assert resp.status_code == 400
    assert "img_path" in resp.json()["detail"]


# ── assessments 状态约束 ──────────────────────────────
def test_assessment_status_invalid_target_returns_422(client, monkeypatch):
    """只允许 generating → analyzed，其他目标值应返回 422。"""
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.put("/admin/api/assessments/999", json={"status": "complete"})
    assert resp.status_code == 422


def test_assessment_status_invalid_source_returns_422(client, db_session, monkeypatch):
    """status=pending 的记录不能重置为 analyzed。"""
    monkeypatch.setenv("DEV_MODE", "true")
    from app.models.user import User
    from app.models.assessment import Assessment

    u = User(openid="o_admin_test")
    db_session.add(u)
    db_session.commit()
    a = Assessment(user_id=u.id, session_id="sess_admin_test", status="pending",
                   signals="{}")
    db_session.add(a)
    db_session.commit()

    resp = client.put(f"/admin/api/assessments/{a.id}", json={"status": "analyzed"})
    assert resp.status_code == 422
    assert "pending" in resp.json()["detail"]


def test_update_empty_body_returns_400(client, monkeypatch):
    """空 body 应返回 400，不应导致 503。"""
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.put("/admin/api/base_love_type/1", json={})
    assert resp.status_code == 400


# ── Overview ──────────────────────────────────────────
def test_overview_returns_expected_shape(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "tables" in data
    for table in ("users", "assessments", "orders", "ai_call_logs"):
        assert table in data["tables"]
        assert "total" in data["tables"][table]
        assert "today" in data["tables"][table]
    assert "recent_assessments" in data


# ── Table list ────────────────────────────────────────
def test_table_list_users_returns_paginated(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/users?page=1&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "rows" in data
    assert data["page"] == 1
    assert data["limit"] == 10


def test_table_list_search(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from app.models.user import User
    u = User(openid="o_search_target_xyz")
    db_session.add(u)
    db_session.commit()

    resp = client.get("/admin/api/users?q=search_target_xyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("search_target_xyz" in r["openid"] for r in data["rows"])


# ── Table detail ──────────────────────────────────────
def test_table_detail_returns_full_record(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    from app.models.user import User
    u = User(openid="o_detail_test")
    db_session.add(u)
    db_session.commit()

    resp = client.get(f"/admin/api/users/{u.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == u.id
    assert data["openid"] == "o_detail_test"


def test_table_detail_missing_record_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/users/99999")
    assert resp.status_code == 404


# ── Table update ──────────────────────────────────────
def test_assessment_status_reset_success(client, db_session, monkeypatch):
    """generating → analyzed 应成功。"""
    monkeypatch.setenv("DEV_MODE", "true")
    from app.models.user import User
    from app.models.assessment import Assessment
    u = User(openid="o_reset_test")
    db_session.add(u)
    db_session.commit()
    a = Assessment(user_id=u.id, session_id="sess_reset_ok",
                   status="generating", signals="{}")
    db_session.add(a)
    db_session.commit()

    resp = client.put(f"/admin/api/assessments/{a.id}", json={"status": "analyzed"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    db_session.refresh(a)
    assert a.status == "analyzed"


# ── Admin root redirect ───────────────────────────────
def test_admin_root_redirects(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert "/static/admin/index.html" in resp.headers.get("location", "")


# ── X-Admin-Token 认证路径 ─────────────────────────────
def test_admin_token_header_grants_access(client, monkeypatch):
    """DEV_MODE 关闭时，正确的 X-Admin-Token 应放行。"""
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token-x")
    resp = client.get("/admin/api/overview", headers={"X-Admin-Token": "secret-token-x"})
    assert resp.status_code == 200


def test_admin_wrong_token_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("ADMIN_TOKEN", "secret-token-x")
    resp = client.get("/admin/api/overview", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 404


# ── AI 调用日志面板 ───────────────────────────────────
def _make_ai_log(db_session, **overrides):
    """构造一条 AiCallLog 用于日志面板测试。"""
    from app.models.ai_call_log import AiCallLog
    defaults = dict(
        agent="agent_a", model="doubao-test", temperature=0.1,
        session_id="log-test-sess", user_id=None,
        status="success", error_message=None, http_status_code=None,
        retry_index=0,
        system_prompt_len=100,
        messages_json='[{"role":"user","content":"hi"}]',
        response_preview='{"choices":[{"message":{"content":"hello"}}]}',
        response_len=50,
        duration_ms=120,
        prompt_tokens=42, completion_tokens=7, total_tokens=49,
    )
    defaults.update(overrides)
    log = AiCallLog(**defaults)
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


def test_log_detail_returns_parsed_messages_and_response(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    log = _make_ai_log(db_session)

    resp = client.get(f"/admin/logs/api/{log.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == log.id
    assert data["agent"] == "agent_a"
    # messages_json 是合法 JSON → 应被解析回 list
    assert isinstance(data["messages"], list)
    assert data["messages"][0]["role"] == "user"
    # response_preview 是合法 JSON → 也被解析
    assert isinstance(data["response"], dict)


def test_log_detail_handles_non_json_fields(client, db_session, monkeypatch):
    """messages_json / response_preview 非合法 JSON 时应原样字符串透传。"""
    monkeypatch.setenv("DEV_MODE", "true")
    log = _make_ai_log(
        db_session,
        messages_json="this is not json",
        response_preview="plain text response",
    )

    resp = client.get(f"/admin/logs/api/{log.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == "this is not json"
    assert data["response"] == "plain text response"


def test_log_detail_404_when_missing(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/logs/api/999999")
    assert resp.status_code == 404


def test_logs_api_returns_stats_and_rows(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    _make_ai_log(db_session, agent="agent_a", status="success", total_tokens=100)
    _make_ai_log(db_session, agent="agent_b", status="success", total_tokens=50)
    _make_ai_log(db_session, agent="agent_b", status="error",
                 error_message="boom", http_status_code=500, total_tokens=0)

    resp = client.get("/admin/logs/api")
    assert resp.status_code == 200
    data = resp.json()
    # 今天 3 条全在今日，success=2 / error=1
    assert data["stats"]["total"] == 3
    assert data["stats"]["success"] == 2
    assert data["stats"]["error"] == 1
    assert data["stats"]["total_tokens"] == 150
    assert len(data["rows"]) == 3


def test_logs_api_filters_by_agent_and_status(client, db_session, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    _make_ai_log(db_session, agent="agent_a", status="success")
    _make_ai_log(db_session, agent="agent_b", status="success")
    _make_ai_log(db_session, agent="agent_b", status="error")

    resp_a = client.get("/admin/logs/api?agent=agent_a")
    assert resp_a.status_code == 200
    assert all(r["agent"] == "agent_a" for r in resp_a.json()["rows"])
    assert len(resp_a.json()["rows"]) == 1

    resp_b_err = client.get("/admin/logs/api?agent=agent_b&status=error")
    assert resp_b_err.status_code == 200
    rows = resp_b_err.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["status"] == "error"


# ── 控制台日志读取 ─────────────────────────────────────
def test_console_logs_reads_recent_lines(client, tmp_path, monkeypatch):
    """logs/app.log 存在时应返回末 N 行。"""
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    log_file = tmp_path / "logs" / "app.log"
    log_file.write_text("\n".join(f"line-{i}" for i in range(1, 51)), encoding="utf-8")

    resp = client.get("/admin/console?lines=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert len(data["lines"]) == 10
    assert data["lines"][-1] == "line-50"


def test_console_logs_returns_empty_when_file_missing(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.chdir(tmp_path)  # tmp_path 下没有 logs/app.log

    resp = client.get("/admin/console")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["lines"] == []


def test_console_logs_handles_read_error(client, tmp_path, monkeypatch):
    """读取异常时应返回 exists=True + 错误信息（不抛 500）。"""
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    log_path = tmp_path / "logs" / "app.log"
    log_path.write_text("placeholder", encoding="utf-8")

    # 让 open() 抛非 FileNotFoundError 的异常，走 526 兜底
    import builtins
    real_open = builtins.open

    def boom_open(path, *args, **kwargs):
        if str(path).endswith("app.log"):
            raise PermissionError("simulated denial")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", boom_open)

    resp = client.get("/admin/console")
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["lines"] and "读取失败" in data["lines"][0]


# ── HTML 日志面板 ─────────────────────────────────────
def test_logs_dashboard_renders_html(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/logs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # 简单 sanity 检查：HTML 不应为空
    assert len(resp.text) > 100


# ── /admin/api/metrics/llm（Phase D.1） ───────────────
def test_metrics_llm_without_auth_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.get("/admin/api/metrics/llm")
    assert resp.status_code == 404


def test_metrics_llm_returns_all_sections(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/metrics/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_hours"] == 24
    assert "duration" in data
    assert "p95" in data["duration"]
    assert isinstance(data["hourly_trend"], list)
    assert len(data["hourly_trend"]) == 24
    assert isinstance(data["top_users"], list)
    assert isinstance(data["by_agent"], list)


def test_metrics_llm_respects_hours_query(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/metrics/llm?hours=6&top_n=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_hours"] == 6
    assert len(data["hourly_trend"]) == 6


def test_metrics_llm_rejects_invalid_hours(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    # hours=0 / hours>168 / negative 都应该被 Query validator 拒绝
    for bad in (0, -1, 999):
        resp = client.get(f"/admin/api/metrics/llm?hours={bad}")
        assert resp.status_code == 422


# ── /admin/api/audits（Phase D.2） ────────────────────
def test_audits_without_auth_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    resp = client.get("/admin/api/audits")
    assert resp.status_code == 404


def test_audits_empty_returns_zero_stats(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    resp = client.get("/admin/api/audits")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["total"] == 0
    assert data["stats"]["avg_overall"] is None
    assert data["rows"] == []


def test_audits_lists_rows_and_joins_personality_type(client, db_session, monkeypatch):
    """正常路径：插一条 audit + 关联 assessment，应能 join 出 personality_type。"""
    from datetime import datetime, timezone
    from app.models.assessment import Assessment
    from app.models.report_quality_audit import ReportQualityAudit
    from app.models.user import User

    monkeypatch.setenv("DEV_MODE", "true")

    u = User(openid="o_audits_join")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    a = Assessment(
        user_id=u.id, session_id="a-sess", status="complete",
        personality_type="MS-CL-H",
        diagnosis_json='{"type_code":"MS-CL-H"}', report_text="--Title--内容",
    )
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    db_session.add(ReportQualityAudit(
        assessment_id=a.id, judge_model="doubao-test",
        prompt_version="2.0", report_version=1,
        coherence_score=8, readability_score=9, factual_score=7,
        overall_score=8, summary="还行", duration_ms=1500,
        prompt_tokens=1000, completion_tokens=50,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    resp = client.get("/admin/api/audits")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["total"] == 1
    assert data["stats"]["avg_overall"] == 8.0
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["assessment_id"] == a.id
    assert row["personality_type"] == "MS-CL-H"
    assert row["overall_score"] == 8
    assert row["summary"] == "还行"


def test_audits_respects_limit(client, db_session, monkeypatch):
    from datetime import datetime, timezone
    from app.models.report_quality_audit import ReportQualityAudit

    monkeypatch.setenv("DEV_MODE", "true")
    for i in range(5):
        db_session.add(ReportQualityAudit(
            assessment_id=i + 1, judge_model="m",
            coherence_score=5, readability_score=5,
            factual_score=5, overall_score=5,
            summary=f"s{i}", duration_ms=100,
            created_at=datetime.now(timezone.utc),
        ))
    db_session.commit()

    resp = client.get("/admin/api/audits?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 3
