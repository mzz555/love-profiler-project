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
