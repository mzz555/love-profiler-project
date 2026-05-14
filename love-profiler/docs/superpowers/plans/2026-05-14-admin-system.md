# 后台管理系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 FastAPI 项目中新增覆盖全部 11 张表的后台管理系统，支持数据浏览、搜索、静态配置表在线编辑。

**Architecture:** Python 端扩展 `app/api/admin.py` 暴露通用 REST API，前端为单一 `static/admin/index.html` 文件，原生 JS 驱动，无框架依赖。两个数据库（业务表 SQLAlchemy ORM、Supabase 表 raw SQL）统一通过 `SessionLocal` 访问。

**Tech Stack:** FastAPI, SQLAlchemy (text()), pytest, 原生 HTML/CSS/JS

---

## 文件变更清单

```
新增：
  static/admin/index.html          — 前端单页应用（HTML + CSS + JS 合一）
  tests/api/test_admin_api.py      — 后端 API 单元测试

修改：
  app/api/admin.py                 — 新增 TABLE_CONFIG、helper 函数、5 个 API 端点
```

`app/main.py` 已挂载 `/static → static/`，无需修改。

---

## Task 1: TABLE_CONFIG + 通用 helper 函数

**Files:**
- Modify: `app/api/admin.py`
- Test: `tests/api/test_admin_api.py`

- [ ] **Step 1: 创建测试文件，写第一批失败测试（权限 + 配置校验）**

```python
# tests/api/test_admin_api.py
"""Admin API 单元测试。

注意：测试环境使用 SQLite in-memory，Supabase 表（base_love_type 等）不存在。
      权限/字段校验逻辑不依赖表是否存在，可正常测试。
      业务表（users/assessments/orders/ai_call_logs）由 SQLAlchemy 自动建表，可正常查询。
"""
import os
import pytest


# ── 权限测试 ──────────────────────────────────────────
def test_overview_without_auth_returns_404(client):
    """未认证请求应返回 404（隐藏管理面板存在性）。"""
    resp = client.get("/admin/api/overview")
    assert resp.status_code == 404


def test_table_list_without_auth_returns_404(client):
    resp = client.get("/admin/api/users")
    assert resp.status_code == 404


def test_table_update_without_auth_returns_404(client):
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
```

- [ ] **Step 2: 运行测试，确认全部失败**

```bash
pytest tests/api/test_admin_api.py -v
```

期望输出：所有测试 FAILED / ERROR（路由不存在）

- [ ] **Step 3: 在 admin.py 顶部添加 imports 和 TABLE_CONFIG**

在 `app/api/admin.py` 现有 import 区域末尾补充：

```python
from fastapi import Body
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import OperationalError
```

然后在 `router = APIRouter(...)` 下方添加：

```python
# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

# 每张表的访问规则：pk、可搜索列、可编辑字段、截断列（list 视图）
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
        "editable_fields": ["status"],  # 仅允许 generating→analyzed 重置
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
        "editable_fields": ["name_cn", "severity", "is_positive"],
        "truncate_cols": ["report_seed", "interp_path", "trigger_condition"],
        "created_at_col": None,
        "list_cols": ["code", "layer", "involved_dims", "severity",
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
```

- [ ] **Step 4: 在 TABLE_CONFIG 下方添加三个 helper 函数**

```python
# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _query_table(
    db: Session,
    table_name: str,
    config: dict,
    page: int,
    limit: int,
    q: str | None,
) -> dict:
    """通用分页查询，支持多列模糊搜索。表不存在时返回空结果而非 500。"""
    pk = config["pk"]
    offset = (page - 1) * limit
    params: dict = {}

    where_parts: list[str] = []
    if q and config.get("search_cols"):
        for i, col in enumerate(config["search_cols"]):
            where_parts.append(f'LOWER(CAST("{col}" AS TEXT)) LIKE LOWER(:q_{i})')
            params[f"q_{i}"] = f"%{q}%"
    where_clause = ("WHERE " + " OR ".join(where_parts)) if where_parts else ""

    try:
        total = db.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}" {where_clause}'), params
        ).scalar() or 0
        params["limit"] = limit
        params["offset"] = offset
        rows_raw = db.execute(
            text(f'SELECT * FROM "{table_name}" {where_clause} '
                 f'ORDER BY "{pk}" DESC LIMIT :limit OFFSET :offset'),
            params,
        ).fetchall()
    except OperationalError:
        # 表在测试环境（SQLite）不存在时优雅降级
        return {"total": 0, "page": page, "limit": limit, "rows": [],
                "error": "table_not_available"}

    truncate_cols = set(config.get("truncate_cols", []))
    rows = []
    for row in rows_raw:
        d = dict(row._mapping)
        for col in truncate_cols:
            if col in d and isinstance(d[col], str) and len(d[col]) > 100:
                d[col] = d[col][:100] + "…"
        rows.append(d)

    return {"total": total, "page": page, "limit": limit, "rows": rows}


def _get_row(db: Session, table_name: str, config: dict, record_id: str) -> dict:
    """按主键取单条完整记录（大字段不截断）。"""
    pk = config["pk"]
    try:
        row = db.execute(
            text(f'SELECT * FROM "{table_name}" WHERE "{pk}" = :pk_val'),
            {"pk_val": record_id},
        ).fetchone()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="数据库表不可用") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return dict(row._mapping)


def _update_row(
    db: Session,
    table_name: str,
    config: dict,
    record_id: str,
    update_data: dict,
) -> dict:
    """按字段白名单更新记录。assessments.status 有额外约束。"""
    editable = set(config.get("editable_fields", []))

    if not editable:
        raise HTTPException(status_code=403,
                            detail=f"表 {table_name} 为只读，不允许修改")

    invalid = set(update_data.keys()) - editable
    if invalid:
        raise HTTPException(status_code=400,
                            detail=f"不可编辑的字段: {', '.join(sorted(invalid))}")

    # assessments.status 只允许 generating → analyzed
    if table_name == "assessments" and "status" in update_data:
        if update_data["status"] != "analyzed":
            raise HTTPException(status_code=422,
                                detail="status 只允许重置为 analyzed")
        pk = config["pk"]
        try:
            current = db.execute(
                text(f'SELECT status FROM "{table_name}" WHERE "{pk}" = :pk_val'),
                {"pk_val": record_id},
            ).fetchone()
        except OperationalError as exc:
            raise HTTPException(status_code=503, detail="数据库表不可用") from exc
        if current is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if current.status != "generating":
            raise HTTPException(
                status_code=422,
                detail=f"当前 status={current.status}，只有 generating 状态可以重置",
            )

    pk = config["pk"]
    set_clause = ", ".join([f'"{k}" = :{k}' for k in update_data.keys()])
    params = {**update_data, "_pk_val": record_id}

    try:
        result = db.execute(
            text(f'UPDATE "{table_name}" SET {set_clause} WHERE "{pk}" = :_pk_val'),
            params,
        )
        db.commit()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="数据库表不可用") from exc

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="记录不存在")

    return {"ok": True, "updated": record_id}
```

- [ ] **Step 5: 运行测试，确认权限/校验类测试通过**

```bash
pytest tests/api/test_admin_api.py -v
```

期望：所有权限测试 PASS（此时 API 端点未建，其他测试仍 FAIL/ERROR）

- [ ] **Step 6: Commit**

```bash
git add app/api/admin.py tests/api/test_admin_api.py
git commit -m "feat(admin): 新增 TABLE_CONFIG 和通用 helper 函数"
```

---

## Task 2: API 端点（overview + list + detail + update + root 重定向）

**Files:**
- Modify: `app/api/admin.py`
- Test: `tests/api/test_admin_api.py`

- [ ] **Step 1: 在测试文件末尾追加业务端点测试**

```python
# 追加到 tests/api/test_admin_api.py

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
```

- [ ] **Step 2: 运行测试，确认全部失败**

```bash
pytest tests/api/test_admin_api.py -v -k "overview or table_list or table_detail or table_update or admin_root"
```

期望：FAILED（路由不存在）

- [ ] **Step 3: 在 admin.py 的 `require_admin` 函数之后，现有 `log_detail` 之前，添加五个新端点**

```python
# ---------------------------------------------------------------------------
# New API endpoints
# ---------------------------------------------------------------------------

@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def admin_root(_: None = Depends(require_admin)) -> RedirectResponse:
    """管理面板入口，重定向到前端 SPA。"""
    return RedirectResponse(url="/static/admin/index.html")


@router.get("/api/overview", include_in_schema=False)
async def admin_overview(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    """各业务表统计数据 + 最近 5 条 assessments。"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result: dict = {"tables": {}, "recent_assessments": []}

    for table in ("users", "assessments", "orders", "ai_call_logs"):
        cfg = TABLE_CONFIG[table]
        ts_col = cfg["created_at_col"]
        try:
            total = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
            today_count = 0
            if ts_col:
                today_count = db.execute(
                    text(f'SELECT COUNT(*) FROM "{table}" WHERE "{ts_col}" >= :ts'),
                    {"ts": today_start},
                ).scalar() or 0
            result["tables"][table] = {"total": total, "today": today_count}
        except OperationalError:
            result["tables"][table] = {"total": 0, "today": 0}

    # assessments 状态分布
    try:
        rows = db.execute(
            text("SELECT status, COUNT(*) AS cnt FROM assessments GROUP BY status")
        ).fetchall()
        result["tables"]["assessments"]["by_status"] = {r.status: r.cnt for r in rows}
    except OperationalError:
        pass

    # orders 状态分布
    try:
        rows = db.execute(
            text("SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status")
        ).fetchall()
        result["tables"]["orders"]["by_status"] = {r.status: r.cnt for r in rows}
    except OperationalError:
        pass

    # 最近 5 条 assessments
    try:
        rows = db.execute(
            text("SELECT id, session_id, personality_type, status, created_at "
                 "FROM assessments ORDER BY id DESC LIMIT 5")
        ).fetchall()
        result["recent_assessments"] = [dict(r._mapping) for r in rows]
    except OperationalError:
        pass

    return result


@router.get("/api/{table_name}", include_in_schema=False)
async def admin_table_list(
    table_name: str = Path(...),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return _query_table(db, table_name, TABLE_CONFIG[table_name], page, limit, q)


@router.get("/api/{table_name}/{record_id}", include_in_schema=False)
async def admin_table_detail(
    table_name: str = Path(...),
    record_id: str = Path(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return _get_row(db, table_name, TABLE_CONFIG[table_name], record_id)


@router.put("/api/{table_name}/{record_id}", include_in_schema=False)
async def admin_table_update(
    table_name: str = Path(...),
    record_id: str = Path(...),
    body: dict = Body(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return _update_row(db, table_name, TABLE_CONFIG[table_name], record_id, body)
```

- [ ] **Step 4: 运行全部测试，确认全部通过**

```bash
pytest tests/api/test_admin_api.py -v
```

期望：全部 PASS

- [ ] **Step 5: 运行完整测试套件，确认无回归**

```bash
pytest -v
```

期望：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/admin.py tests/api/test_admin_api.py
git commit -m "feat(admin): 新增 overview/list/detail/update API 端点"
```

---

## Task 3: 创建前端静态文件目录

**Files:**
- Create: `static/admin/index.html`（骨架占位）

- [ ] **Step 1: 确认 static/ 目录存在**

```bash
ls static/
```

期望：目录存在（已有 `static/personalities/` 等子目录）

- [ ] **Step 2: 创建 static/admin/ 目录及占位 HTML**

创建 `static/admin/index.html`（内容在 Task 4 中替换为完整实现）：

```html
<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>管理后台</title></head>
<body><p>占位，Task 4 将替换为完整实现。</p></body>
</html>
```

- [ ] **Step 3: 验证静态文件可访问**

启动服务：
```bash
uvicorn app.main:app --reload --port 8000
```

浏览器访问 `http://localhost:8000/static/admin/index.html`，应看到「占位」文字。

访问 `http://localhost:8000/admin`（DEV_MODE=true），应重定向到上述页面。

- [ ] **Step 4: Commit**

```bash
git add static/admin/index.html
git commit -m "feat(admin): 初始化静态管理面板目录"
```

---

## Task 4: 前端 HTML — 布局框架 + 概览页

**Files:**
- Modify: `static/admin/index.html`

用以下完整内容**替换** `static/admin/index.html`：

- [ ] **Step 1: 写 HTML shell（sidebar + 主区域 + CSS）**

将 `static/admin/index.html` 的全部内容替换为：

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Love Profiler · 管理后台</title>
<style>
/* ── Reset & Variables ─────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--card:#161b27;--border:#1e2535;--text:#e2e8f0;
  --muted:#64748b;--accent:#3b82f6;--green:#4ade80;--red:#f87171;
  --teal:#4FAFAF;--sidebar:220px;
}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:var(--bg);color:var(--text);font-size:14px;
     display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* ── Top bar ───────────────────────────────── */
.topbar{height:48px;border-bottom:1px solid var(--border);
        display:flex;align-items:center;padding:0 20px;gap:12px;flex-shrink:0}
.topbar h1{font-size:15px;font-weight:600;color:#f1f5f9}
.topbar .sub{color:var(--muted);font-size:12px}
.topbar-right{margin-left:auto;display:flex;gap:8px;align-items:center}
.btn{background:#1e40af;color:#fff;border:none;padding:5px 12px;
     border-radius:6px;cursor:pointer;font-size:12px;text-decoration:none}
.btn:hover{background:#1d4ed8}
.btn-sm{padding:3px 10px;font-size:11px}

/* ── Layout ────────────────────────────────── */
.layout{display:flex;flex:1;overflow:hidden}

/* ── Sidebar ───────────────────────────────── */
.sidebar{width:var(--sidebar);border-right:1px solid var(--border);
         overflow-y:auto;flex-shrink:0;padding:8px 0}
.nav-group-label{font-size:10px;color:var(--muted);text-transform:uppercase;
                 letter-spacing:.06em;padding:12px 16px 4px}
.nav-item{display:flex;align-items:center;gap:8px;padding:7px 16px;
          cursor:pointer;color:#94a3b8;font-size:13px;border-left:3px solid transparent;
          transition:background .1s,color .1s}
.nav-item:hover{background:rgba(255,255,255,.04);color:var(--text)}
.nav-item.active{background:rgba(59,130,246,.10);color:#93c5fd;
                 border-left-color:var(--accent)}
.nav-item .icon{font-size:14px;width:20px;text-align:center}
.nav-item a{color:inherit;text-decoration:none;display:flex;align-items:center;
            gap:8px;width:100%}
.nav-divider{height:1px;background:var(--border);margin:6px 8px}

/* ── Main content ──────────────────────────── */
.main{flex:1;overflow-y:auto;padding:24px}

/* ── Cards / Stats ─────────────────────────── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.stat-card{background:var(--card);border:1px solid var(--border);
           border-radius:10px;padding:16px}
.stat-label{font-size:11px;color:var(--muted);text-transform:uppercase;
            letter-spacing:.05em;margin-bottom:6px}
.stat-val{font-size:26px;font-weight:700;color:#f1f5f9}
.stat-sub{font-size:11px;color:var(--muted);margin-top:4px}
.stat-val.green{color:var(--green)}.stat-val.red{color:var(--red)}
.stat-val.teal{color:var(--teal)}

/* Status bar */
.status-bar{height:6px;background:var(--border);border-radius:3px;margin-top:8px;
            overflow:hidden;display:flex;gap:1px}
.status-seg{height:100%;border-radius:2px;transition:width .3s}
.seg-complete{background:#4ade80}.seg-analyzed{background:#3b82f6}
.seg-pending{background:#94a3b8}.seg-generating{background:#fbbf24}
.seg-paid{background:#4ade80}.seg-failed{background:#f87171}

/* ── Section title ─────────────────────────── */
.section-title{font-size:16px;font-weight:600;color:#f1f5f9;margin-bottom:16px}
.section-sub{font-size:12px;color:var(--muted);margin-bottom:16px;margin-top:-10px}

/* ── Table ─────────────────────────────────── */
.tbl-toolbar{display:flex;gap:8px;margin-bottom:12px;align-items:center}
.search-input{background:var(--card);border:1px solid var(--border);color:var(--text);
              padding:6px 12px;border-radius:6px;font-size:13px;outline:none;flex:1;
              max-width:300px}
.search-input:focus{border-color:var(--accent)}
.select-sm{background:var(--card);border:1px solid var(--border);color:var(--text);
           padding:5px 8px;border-radius:6px;font-size:12px;outline:none}
.tbl-count{color:var(--muted);font-size:12px;margin-left:auto}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead tr{border-bottom:1px solid var(--border)}
th{text-align:left;padding:8px 10px;color:var(--muted);font-weight:500;
   font-size:11px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid #0e1520;vertical-align:middle;
   max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr.clickable{cursor:pointer}
tr.clickable:hover td{background:#161b27}
tr.editing td{background:rgba(59,130,246,.06)}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600}
.badge-success,.badge-complete,.badge-paid,.badge-analyzed{background:#14532d;color:#4ade80}
.badge-error,.badge-failed{background:#450a0a;color:#f87171}
.badge-pending{background:#1e293b;color:#94a3b8}
.badge-generating{background:#422006;color:#fb923c}
.badge-high{background:#450a0a;color:#fca5a5}
.badge-moderate{background:#422006;color:#fdba74}
.badge-info{background:#0c2340;color:#7dd3fc}
.mono{font-family:"SF Mono","Fira Code",monospace;font-size:11px}
.dim{color:var(--muted)}
.bool-true{color:var(--green)}.bool-false{color:var(--red)}
.edit-input{background:#1e293b;border:1px solid var(--accent);color:var(--text);
            padding:3px 7px;border-radius:4px;font-size:13px;width:100%;outline:none}
.edit-textarea{background:#1e293b;border:1px solid var(--accent);color:var(--text);
               padding:4px 7px;border-radius:4px;font-size:12px;width:100%;
               min-height:60px;resize:vertical;outline:none}
.row-actions{display:flex;gap:6px;white-space:nowrap}
.btn-edit{background:#1e3a5f;color:#93c5fd;border:1px solid #1e40af;
          padding:2px 9px;border-radius:4px;cursor:pointer;font-size:11px}
.btn-edit:hover{background:#1e40af}
.btn-save{background:#14532d;color:#4ade80;border:1px solid #166534;
          padding:2px 9px;border-radius:4px;cursor:pointer;font-size:11px}
.btn-save:hover{background:#166534}
.btn-cancel{background:#1e293b;color:#94a3b8;border:1px solid #334155;
            padding:2px 9px;border-radius:4px;cursor:pointer;font-size:11px}
.btn-cancel:hover{background:#334155}

/* ── Pagination ────────────────────────────── */
.pagination{display:flex;gap:8px;align-items:center;margin-top:14px;font-size:12px}
.pagination button{background:var(--card);border:1px solid var(--border);
                   color:var(--text);padding:4px 12px;border-radius:5px;
                   cursor:pointer;font-size:12px}
.pagination button:hover:not(:disabled){background:#1e293b}
.pagination button:disabled{opacity:.4;cursor:default}
.pg-info{color:var(--muted)}

/* ── Detail panel ──────────────────────────── */
.detail-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:50;
                display:none;align-items:flex-start;justify-content:flex-end}
.detail-overlay.open{display:flex}
.detail-panel{width:480px;max-width:95vw;height:100vh;background:var(--card);
              border-left:1px solid var(--border);overflow-y:auto;
              display:flex;flex-direction:column}
.dp-hdr{padding:16px 20px;border-bottom:1px solid var(--border);
        display:flex;align-items:center;gap:10px;flex-shrink:0}
.dp-hdr h3{font-size:15px;font-weight:600;flex:1}
.dp-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer}
.dp-body{padding:20px;flex:1}
.dp-section{background:#0f1117;border:1px solid var(--border);
            border-radius:8px;padding:14px;margin-bottom:14px}
.dp-section h4{font-size:10px;color:var(--muted);text-transform:uppercase;
               letter-spacing:.05em;margin-bottom:10px}
.kv{display:grid;grid-template-columns:140px 1fr;gap:4px 8px;font-size:12px}
.kv .k{color:var(--muted)}.kv .v{color:var(--text);word-break:break-all}
details summary{cursor:pointer;color:var(--accent);font-size:12px;margin-bottom:6px}
pre.json{background:#0a0d14;border:1px solid var(--border);border-radius:6px;
         padding:10px;font-size:11px;font-family:"SF Mono","Fira Code",monospace;
         overflow-x:auto;white-space:pre-wrap;word-break:break-all;
         max-height:320px;overflow-y:auto;color:#a5f3fc;margin-top:6px}

/* ── Toast ─────────────────────────────────── */
.toast{position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:8px;
       font-size:13px;color:#fff;z-index:200;opacity:0;transition:opacity .2s;
       pointer-events:none}
.toast.show{opacity:1}
.toast.ok{background:#166534}.toast.err{background:#7f1d1d}

/* ── Reset button ──────────────────────────── */
.btn-reset{background:#422006;color:#fb923c;border:1px solid #78350f;
           padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;margin-top:12px}
.btn-reset:hover{background:#78350f}

/* ── Empty / Loading ───────────────────────── */
.empty{text-align:center;padding:40px;color:#475569;font-size:13px}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid var(--border);
         border-top-color:var(--accent);border-radius:50%;
         animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.flash-green{animation:flashG .6s ease}
.flash-red{animation:flashR .6s ease}
@keyframes flashG{0%,100%{background:transparent}50%{background:rgba(74,222,128,.15)}}
@keyframes flashR{0%,100%{background:transparent}50%{background:rgba(248,113,113,.15)}}
</style>
</head>
<body>

<!-- Top bar -->
<div class="topbar">
  <div><span class="topbar h1" style="font-size:15px;font-weight:600;color:#f1f5f9">Love Profiler 管理后台</span>
       <span class="sub" style="font-size:12px;color:#64748b;margin-left:10px">内部工具</span></div>
  <div class="topbar-right">
    <a href="/admin/logs" target="_blank" class="btn btn-sm">AI 监控 ↗</a>
    <button class="btn btn-sm" onclick="refreshCurrent()">刷新</button>
  </div>
</div>

<!-- Body -->
<div class="layout">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="nav-item active" data-view="overview" onclick="navigate('overview',this)">
      <span class="icon">📊</span>概览
    </div>
    <div class="nav-divider"></div>
    <div class="nav-group-label">业务数据</div>
    <div class="nav-item" data-view="users" onclick="navigate('users',this)">
      <span class="icon">👤</span>用户
    </div>
    <div class="nav-item" data-view="assessments" onclick="navigate('assessments',this)">
      <span class="icon">📋</span>测评记录
    </div>
    <div class="nav-item" data-view="orders" onclick="navigate('orders',this)">
      <span class="icon">💳</span>订单
    </div>
    <div class="nav-item" data-view="ai_call_logs" onclick="navigate('ai_call_logs',this)">
      <span class="icon">🤖</span>AI 调用日志
    </div>
    <div class="nav-divider"></div>
    <div class="nav-group-label">静态配置（可编辑）</div>
    <div class="nav-item" data-view="base_love_type" onclick="navigate('base_love_type',this)">
      <span class="icon">🎭</span>人格类型
    </div>
    <div class="nav-item" data-view="highlights" onclick="navigate('highlights',this)">
      <span class="icon">💡</span>深度洞察
    </div>
    <div class="nav-item" data-view="base_dimension_meta" onclick="navigate('base_dimension_meta',this)">
      <span class="icon">📐</span>维度元信息
    </div>
    <div class="nav-item" data-view="base_segment_decode" onclick="navigate('base_segment_decode',this)">
      <span class="icon">🔑</span>段落解码
    </div>
    <div class="nav-item" data-view="base_D4_type" onclick="navigate('base_D4_type',this)">
      <span class="icon">❤️</span>爱的语言
    </div>
    <div class="nav-item" data-view="base_D5_quadrant" onclick="navigate('base_D5_quadrant',this)">
      <span class="icon">🌐</span>表达象限
    </div>
    <div class="nav-divider"></div>
    <div class="nav-group-label">参考数据（只读）</div>
    <div class="nav-item" data-view="questions" onclick="navigate('questions',this)">
      <span class="icon">📝</span>题库
    </div>
  </div>

  <!-- Main -->
  <div class="main" id="main">
    <div class="empty"><span class="spinner"></span>加载中…</div>
  </div>
</div>

<!-- Detail panel -->
<div class="detail-overlay" id="detailOverlay" onclick="closeDetail(event)">
  <div class="detail-panel" onclick="event.stopPropagation()">
    <div class="dp-hdr">
      <h3 id="dpTitle">记录详情</h3>
      <button class="dp-close" onclick="closeDetail()">×</button>
    </div>
    <div class="dp-body" id="dpBody"></div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
// ═══════════════════════════════════════════════════════
// State & Navigation
// ═══════════════════════════════════════════════════════
let _curView = 'overview';
let _curPage = 1;
let _curLimit = 50;
let _curQ = '';
let _editingRow = null;

function navigate(view, el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  _curView = view;
  _curPage = 1;
  _curQ = '';
  if (view === 'overview') loadOverview();
  else loadTable(view, 1, _curLimit, '');
}

function refreshCurrent() {
  if (_curView === 'overview') loadOverview();
  else loadTable(_curView, _curPage, _curLimit, _curQ);
}

// ═══════════════════════════════════════════════════════
// Utils
// ═══════════════════════════════════════════════════════
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtNum(n) {
  if (n == null) return '—';
  if (n >= 10000) return (n/1000).toFixed(1)+'k';
  return Number(n).toLocaleString();
}
function fmtDate(v) {
  if (!v) return '—';
  const d = new Date(v);
  const p = n => String(n).padStart(2,'0');
  return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function badgeHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  const cls = String(val).toLowerCase().replace(/[^a-z]/g,'');
  return `<span class="badge badge-${cls}">${esc(val)}</span>`;
}
function boolHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  return val
    ? '<span class="bool-true">✓</span>'
    : '<span class="bool-false">✗</span>';
}
function cellHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  if (typeof val === 'boolean') return boolHtml(val);
  const s = String(val);
  if (['success','error','pending','paid','failed','complete','analyzed','generating',
       'high','moderate','info'].includes(s.toLowerCase())) return badgeHtml(s);
  return esc(s);
}
function showToast(msg, ok=true) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + (ok ? 'ok' : 'err');
  setTimeout(() => t.className = 'toast', 2500);
}
function setMain(html) {
  document.getElementById('main').innerHTML = html;
}

// ═══════════════════════════════════════════════════════
// Overview page
// ═══════════════════════════════════════════════════════
async function loadOverview() {
  setMain('<div class="empty"><span class="spinner"></span>加载中…</div>');
  const data = await apiFetch('/admin/api/overview');
  if (!data) return;

  const t = data.tables;
  const aStats = t.assessments || {};
  const oStats = t.orders || {};

  const totalA = aStats.total || 0;
  const byA = aStats.by_status || {};
  const completeA = byA.complete || 0;
  const analyzedA = byA.analyzed || 0;
  const pendingA  = byA.pending  || 0;
  const genA      = byA.generating || 0;

  const totalO = oStats.total || 0;
  const byO = oStats.by_status || {};
  const paidO   = byO.paid    || 0;
  const failedO = byO.failed  || 0;
  const pendO   = byO.pending || 0;

  const barA = totalA > 0 ? `
    <div class="status-bar">
      <div class="status-seg seg-complete" style="width:${completeA/totalA*100}%"></div>
      <div class="status-seg seg-analyzed" style="width:${analyzedA/totalA*100}%"></div>
      <div class="status-seg seg-pending"  style="width:${pendingA/totalA*100}%"></div>
      <div class="status-seg seg-generating" style="width:${genA/totalA*100}%"></div>
    </div>` : '';

  const barO = totalO > 0 ? `
    <div class="status-bar">
      <div class="status-seg seg-paid"   style="width:${paidO/totalO*100}%"></div>
      <div class="status-seg seg-failed" style="width:${failedO/totalO*100}%"></div>
      <div class="status-seg seg-pending" style="width:${pendO/totalO*100}%"></div>
    </div>` : '';

  const recentRows = (data.recent_assessments || []).map(a => `
    <tr>
      <td class="mono dim">#${a.id}</td>
      <td class="mono dim">${esc((a.session_id||'').slice(0,8))}</td>
      <td>${esc(a.personality_type||'—')}</td>
      <td>${badgeHtml(a.status)}</td>
      <td class="dim">${fmtDate(a.created_at)}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="empty">暂无数据</td></tr>';

  setMain(`
    <div class="section-title">概览</div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">用户总数</div>
        <div class="stat-val teal">${fmtNum((t.users||{}).total)}</div>
        <div class="stat-sub">今日 +${(t.users||{}).today || 0}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">测评记录</div>
        <div class="stat-val">${fmtNum(totalA)}</div>
        <div class="stat-sub">今日 +${aStats.today || 0}</div>
        ${barA}
      </div>
      <div class="stat-card">
        <div class="stat-label">订单</div>
        <div class="stat-val">${fmtNum(totalO)}</div>
        <div class="stat-sub">已付款 ${fmtNum(paidO)}</div>
        ${barO}
      </div>
      <div class="stat-card">
        <div class="stat-label">AI 调用（今日）</div>
        <div class="stat-val">${fmtNum((t.ai_call_logs||{}).today)}</div>
        <div class="stat-sub">总计 ${fmtNum((t.ai_call_logs||{}).total)}</div>
      </div>
    </div>

    <div class="section-title">最近 5 条测评</div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>ID</th><th>Session</th><th>类型</th><th>状态</th><th>时间</th>
        </tr></thead>
        <tbody>${recentRows}</tbody>
      </table>
    </div>
  `);
}

// ═══════════════════════════════════════════════════════
// Table browser
// ═══════════════════════════════════════════════════════

// 每张表的列配置（与后端 list_cols 对应）
const COL_CONFIG = {
  users:               ['id','openid','created_at'],
  assessments:         ['id','user_id','session_id','personality_type','status','mode','created_at'],
  orders:              ['id','user_id','assessment_id','out_trade_no','amount','status','created_at'],
  ai_call_logs:        ['id','ts','agent','session_id','model','status','duration_ms','total_tokens','retry_index'],
  base_love_type:      ['id','type_code','type_name','tagline'],
  highlights:          ['code','layer','involved_dims','severity','is_positive','name_cn','sort_order'],
  base_dimension_meta: ['code','name_cn','description','score_model','radar_label','sort_order'],
  base_segment_decode: ['id','dimension','code','label_cn','score_range','is_healthy'],
  base_D4_type:        ['id','love_languages_code','love_languages_name'],
  base_D5_quadrant:    ['quadrant','style_name','sort_order'],
  questions:           ['question_id','dimension','signal_code','signal_name','question_type','sort_order'],
};

// 可编辑字段（与后端白名单对应）
const EDITABLE = {
  assessments:         ['status'],
  base_love_type:      ['type_name','tagline'],
  highlights:          ['name_cn','severity','is_positive'],
  base_dimension_meta: ['name_cn','description','radar_label'],
  base_segment_decode: ['label_cn','description','score_range'],
  base_D4_type:        ['love_languages_name','love_languages_detail'],
  base_D5_quadrant:    ['style_name','description','guide'],
};

// 使用 <textarea> 的字段（长文本）
const TEXTAREA_FIELDS = ['tagline','description','guide','interp_path','report_seed',
                         'trigger_condition','love_languages_detail','radar_label'];

function getPk(table) {
  const pks = { highlights:'code', base_dimension_meta:'code',
                base_D5_quadrant:'quadrant', questions:'question_id' };
  return pks[table] || 'id';
}

async function loadTable(table, page, limit, q) {
  _curView = table; _curPage = page; _curLimit = limit; _curQ = q;
  setMain(`<div class="empty"><span class="spinner"></span>加载中…</div>`);

  const params = new URLSearchParams({ page, limit });
  if (q) params.set('q', q);
  const data = await apiFetch(`/admin/api/${table}?${params}`);
  if (!data) return;

  if (data.error === 'table_not_available') {
    setMain(`<div class="section-title">${table}</div>
             <div class="empty">此表在当前数据库不可用（可能需要 PostgreSQL 连接）</div>`);
    return;
  }

  const cols = COL_CONFIG[table] || Object.keys(data.rows[0] || {}).slice(0,8);
  const editable = EDITABLE[table] || [];
  const pk = getPk(table);
  const hasEdit = editable.length > 0;

  const theadCols = cols.map(c => `<th>${c}</th>`).join('');
  const tbodyRows = data.rows.length === 0
    ? `<tr><td colspan="${cols.length + (hasEdit?1:0)}" class="empty">暂无数据</td></tr>`
    : data.rows.map(row => renderRow(row, cols, editable, pk, table)).join('');

  setMain(`
    <div class="section-title">${table}
      <span style="font-size:12px;font-weight:400;color:var(--muted);margin-left:8px">
        共 ${fmtNum(data.total)} 条
      </span>
    </div>
    <div class="tbl-toolbar">
      <input class="search-input" id="searchQ" placeholder="搜索…"
             value="${esc(q)}" onkeydown="if(event.key==='Enter')doSearch()">
      <button class="btn btn-sm" onclick="doSearch()">搜索</button>
      <select class="select-sm" onchange="loadTable('${table}',1,this.value,'${esc(q)}')" >
        ${[20,50,100,200].map(n=>`<option value="${n}"${n==limit?' selected':''}>${n}条/页</option>`).join('')}
      </select>
      ${hasEdit ? '<span style="font-size:11px;color:var(--muted);margin-left:auto">✏️ 点击行末尾编辑</span>' : ''}
    </div>
    <div class="tbl-wrap">
      <table id="dataTable">
        <thead><tr>${theadCols}${hasEdit?'<th>操作</th>':''}</tr></thead>
        <tbody id="tbody">${tbodyRows}</tbody>
      </table>
    </div>
    <div class="pagination">
      <button onclick="loadTable('${table}',${page-1},${limit},'${esc(q)}')" ${page<=1?'disabled':''}>← 上一页</button>
      <span class="pg-info">第 ${page} / ${Math.ceil(data.total/limit)||1} 页</span>
      <button onclick="loadTable('${table}',${page+1},${limit},'${esc(q)}')"
        ${page >= Math.ceil(data.total/limit) ? 'disabled':''}>下一页 →</button>
    </div>
  `);
}

function renderRow(row, cols, editable, pk, table) {
  const pkVal = row[pk];
  const cells = cols.map(col => {
    const v = row[col];
    // 日期列格式化
    if (col === 'created_at' || col === 'ts') return `<td>${fmtDate(v)}</td>`;
    return `<td title="${esc(String(v??''))}">${cellHtml(v)}</td>`;
  }).join('');
  const editBtn = editable.length > 0
    ? `<td><div class="row-actions">
         <button class="btn-edit" onclick="event.stopPropagation();startEdit(this,'${table}','${pkVal}')">✏️ 编辑</button>
       </div></td>`
    : '';
  return `<tr class="clickable" data-pk="${pkVal}" onclick="openDetail('${table}','${pkVal}')">
    ${cells}${editBtn}
  </tr>`;
}

function doSearch() {
  const q = document.getElementById('searchQ')?.value || '';
  loadTable(_curView, 1, _curLimit, q);
}

// ═══════════════════════════════════════════════════════
// Inline editing
// ═══════════════════════════════════════════════════════
async function startEdit(btn, table, pkVal) {
  const row = btn.closest('tr');
  if (_editingRow && _editingRow !== row) cancelEdit(_editingRow, table);

  _editingRow = row;
  row.classList.add('editing');

  // 获取完整记录
  const record = await apiFetch(`/admin/api/${table}/${pkVal}`);
  if (!record) return;

  const editable = EDITABLE[table] || [];
  const pk = getPk(table);
  const cols = COL_CONFIG[table] || [];

  // 重建每列的 td
  let i = 0;
  for (const td of row.querySelectorAll('td:not(:last-child)')) {
    const col = cols[i++];
    if (!col) continue;
    if (editable.includes(col)) {
      const v = record[col] ?? '';
      const isLong = TEXTAREA_FIELDS.includes(col);
      if (typeof v === 'boolean' || v === true || v === false) {
        td.innerHTML = `<select class="edit-input" data-field="${col}">
          <option value="true"${v?'selected':''}>true</option>
          <option value="false"${!v?'selected':''}>false</option>
        </select>`;
      } else if (isLong) {
        td.innerHTML = `<textarea class="edit-textarea" data-field="${col}">${esc(v)}</textarea>`;
      } else {
        td.innerHTML = `<input class="edit-input" data-field="${col}" value="${esc(v)}">`;
      }
    }
  }

  // 操作列
  const actionTd = row.querySelector('td:last-child');
  if (actionTd) {
    actionTd.innerHTML = `<div class="row-actions">
      <button class="btn-save" onclick="saveEdit(this,'${table}','${pkVal}')">保存</button>
      <button class="btn-cancel" onclick="cancelEditByBtn(this,'${table}','${pkVal}')">取消</button>
    </div>`;
  }

  // assessments.status 特殊：如果是 generating，显示重置按钮
  if (table === 'assessments' && record.status === 'generating') {
    row.insertAdjacentHTML('afterend',
      `<tr id="reset-hint-${pkVal}"><td colspan="10" style="padding:8px 10px;">
        <button class="btn-reset"
          onclick="resetAssessmentStatus('${pkVal}',this)">
          ⚠️ 重置 generating → analyzed
        </button>
        <span style="font-size:11px;color:var(--muted);margin-left:8px">仅在卡死时使用</span>
      </td></tr>`
    );
  }
}

async function saveEdit(btn, table, pkVal) {
  const row = btn.closest('tr');
  const inputs = row.querySelectorAll('[data-field]');
  const body = {};
  inputs.forEach(inp => {
    const f = inp.dataset.field;
    let v = inp.value;
    if (inp.tagName === 'SELECT' && (v === 'true' || v === 'false')) {
      v = v === 'true';
    }
    body[f] = v;
  });

  const result = await apiFetch(`/admin/api/${table}/${pkVal}`, 'PUT', body);
  if (!result) return;

  row.classList.remove('editing');
  _editingRow = null;
  showToast('保存成功');
  row.classList.add('flash-green');
  setTimeout(() => row.classList.remove('flash-green'), 700);

  // 移除 reset hint row if exists
  document.getElementById(`reset-hint-${pkVal}`)?.remove();

  // 重新加载当前页
  setTimeout(() => loadTable(table, _curPage, _curLimit, _curQ), 500);
}

function cancelEdit(row, table) {
  row.classList.remove('editing');
  const pkVal = row.dataset.pk;
  document.getElementById(`reset-hint-${pkVal}`)?.remove();
  loadTable(table, _curPage, _curLimit, _curQ);
}

function cancelEditByBtn(btn, table, pkVal) {
  const row = btn.closest('tr');
  _editingRow = null;
  document.getElementById(`reset-hint-${pkVal}`)?.remove();
  loadTable(table, _curPage, _curLimit, _curQ);
}

// ═══════════════════════════════════════════════════════
// Assessments status reset
// ═══════════════════════════════════════════════════════
async function resetAssessmentStatus(pkVal, btn) {
  if (!confirm(`确认将 assessment #${pkVal} 的状态从 generating 重置为 analyzed？`)) return;
  btn.disabled = true;
  const result = await apiFetch(`/admin/api/assessments/${pkVal}`, 'PUT',
                                { status: 'analyzed' });
  if (result?.ok) {
    showToast('重置成功');
    loadTable('assessments', _curPage, _curLimit, _curQ);
  }
}

// ═══════════════════════════════════════════════════════
// Detail panel
// ═══════════════════════════════════════════════════════
async function openDetail(table, pkVal) {
  if (_editingRow) return; // 编辑中不弹详情
  document.getElementById('dpTitle').textContent = `${table} · ${pkVal}`;
  document.getElementById('dpBody').innerHTML =
    '<div class="empty"><span class="spinner"></span>加载中…</div>';
  document.getElementById('detailOverlay').classList.add('open');

  const data = await apiFetch(`/admin/api/${table}/${pkVal}`);
  if (!data) return;

  // 大字段折叠展示
  const BIG_FIELDS = ['diagnosis_json','report_text','answers_json','report_json',
                      'dimension_scores','summary','signals','messages_json',
                      'response_preview','trigger_condition','interp_path',
                      'report_seed','guide','description'];

  let basicKvs = '', bigKvs = '';
  for (const [k, v] of Object.entries(data)) {
    if (BIG_FIELDS.includes(k)) {
      let content;
      try { content = JSON.stringify(JSON.parse(v), null, 2); }
      catch { content = String(v ?? ''); }
      bigKvs += `<details style="margin-bottom:8px">
        <summary>${esc(k)} (${String(v??'').length} 字符)</summary>
        <pre class="json">${esc(content)}</pre>
      </details>`;
    } else {
      const disp = typeof v === 'boolean' ? boolHtml(v)
                 : ['status','severity'].includes(k) ? badgeHtml(v)
                 : `<span class="v">${esc(String(v??'—'))}</span>`;
      basicKvs += `<span class="k">${esc(k)}</span>${disp}`;
    }
  }

  // assessments reset button in detail panel
  const resetBtn = table === 'assessments' && data.status === 'generating'
    ? `<button class="btn-reset" onclick="resetAssessmentStatus('${pkVal}',this)">
         ⚠️ 重置 generating → analyzed
       </button>` : '';

  document.getElementById('dpBody').innerHTML = `
    <div class="dp-section">
      <h4>基本字段</h4>
      <div class="kv">${basicKvs}</div>
      ${resetBtn}
    </div>
    ${bigKvs ? `<div class="dp-section"><h4>大字段（展开查看）</h4>${bigKvs}</div>` : ''}
  `;
}

function closeDetail(e) {
  if (!e || e.target === document.getElementById('detailOverlay')) {
    document.getElementById('detailOverlay').classList.remove('open');
  }
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

// ═══════════════════════════════════════════════════════
// API helper
// ═══════════════════════════════════════════════════════
async function apiFetch(url, method='GET', body=null) {
  const token = new URLSearchParams(location.search).get('token') || '';
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json',
               ...(token ? { 'X-Admin-Token': token } : {}) },
  };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      showToast(`错误 ${res.status}: ${err.detail || res.statusText}`, false);
      return null;
    }
    return await res.json();
  } catch (e) {
    showToast(`网络错误: ${e.message}`, false);
    return null;
  }
}

// ═══════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════
loadOverview();
</script>
</body>
</html>
```

- [ ] **Step 2: 启动服务手动验证**

```bash
DEV_MODE=true uvicorn app.main:app --reload --port 8000
```

打开 `http://localhost:8000/admin`，逐项验证：
- [ ] 重定向到 `/static/admin/index.html` 并正常显示
- [ ] 侧边栏所有分组和导航项可见
- [ ] 概览页加载 4 张统计卡片（数字正确）
- [ ] 点击「用户」显示 users 表格（空也可以，有列头）
- [ ] 点击「测评记录」显示 assessments 表格
- [ ] 点击「人格类型」显示 base_love_type 表格（需 PostgreSQL 连接）
- [ ] 搜索框输入并回车，URL 参数变化、表格重新加载
- [ ] 分页按钮正常工作
- [ ] 点击行展开详情面板，大字段可折叠
- [ ] 可编辑表格行末有「✏️ 编辑」按钮，点击后变为输入框
- [ ] 保存后行闪绿、toast 提示「保存成功」
- [ ] 取消后恢复原值
- [ ] 将某 assessment 状态手动改为 generating，打开编辑时出现橙色重置按钮
- [ ] 点击「AI 监控 ↗」在新标签打开 `/admin/logs`

- [ ] **Step 3: Commit**

```bash
git add static/admin/index.html
git commit -m "feat(admin): 完成后台管理 SPA（概览 + 表格浏览 + 内联编辑 + 详情面板）"
```

---

## Task 5: 运行完整测试套件并做最终验证

**Files:**
- No file changes — regression check only

- [ ] **Step 1: 运行全套测试**

```bash
pytest -v
```

期望：所有测试 PASS，无新增失败。

- [ ] **Step 2: 检查 admin.py 路由顺序（避免参数路由遮挡）**

FastAPI 按注册顺序匹配路由。确认 `admin.py` 中路由注册顺序如下（精确路由在参数路由之前）：

```
GET  /admin                          ← 精确，先注册
GET  /admin/logs                     ← 已有，先注册
GET  /admin/logs/api/{log_id}        ← 已有
GET  /admin/logs/api                 ← 已有
GET  /admin/console                  ← 已有
GET  /admin/api/overview             ← 精确，先注册
GET  /admin/api/{table_name}         ← 参数路由，后注册
GET  /admin/api/{table_name}/{id}    ← 参数路由，后注册
PUT  /admin/api/{table_name}/{id}    ← 参数路由，后注册
```

若顺序不对，调整 `admin.py` 中端点的定义顺序并重新测试。

- [ ] **Step 3: 最终 Commit**

```bash
git add app/api/admin.py tests/api/test_admin_api.py static/admin/index.html
git commit -m "feat: 后台管理系统完整实现（API + SPA 前端）"
```

---

## 附录：生产环境访问

生产环境需在服务器设置：

```bash
ADMIN_TOKEN=your-secret-token
```

访问时在请求头携带 `X-Admin-Token: your-secret-token`，或在 URL 中带 `?token=your-secret-token`。
