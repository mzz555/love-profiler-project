"""
Admin dashboard — AI call log monitor.

Endpoints:
  GET /admin/logs              HTML dashboard (2 tabs: AI调用 + 控制台)
  GET /admin/logs/api          JSON: stats + call log rows
  GET /admin/logs/api/{id}     JSON: full detail for one row (messages + response)
  GET /admin/console           JSON: last N lines from logs/app.log

Access: requires DEV_MODE=true OR ADMIN_TOKEN env var.
"""

import json
import os
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ai_call_log import AiCallLog

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Access guard
# ---------------------------------------------------------------------------

def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Allow when DEV_MODE is on, otherwise require X-Admin-Token to match ADMIN_TOKEN."""
    if os.environ.get("DEV_MODE", "").lower() == "true":
        return
    expected = os.environ.get("ADMIN_TOKEN", "")
    if expected and x_admin_token == expected:
        return
    # Hide the existence of the panel from unauthenticated callers.
    raise HTTPException(status_code=404)


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@router.get("/logs/api/{log_id}", include_in_schema=False)
async def log_detail(
    log_id: int = Path(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    row = db.query(AiCallLog).filter(AiCallLog.id == log_id).first()
    if row is None:
        raise HTTPException(status_code=404)

    messages = None
    if row.messages_json:
        try:
            messages = json.loads(row.messages_json)
        except Exception:
            messages = row.messages_json

    response_parsed = None
    if row.response_preview:
        try:
            response_parsed = json.loads(row.response_preview)
        except Exception:
            response_parsed = row.response_preview

    return {
        "id":                row.id,
        "ts":                row.ts.isoformat() if row.ts else None,
        "agent":             row.agent,
        "session_id":        row.session_id,
        "model":             row.model,
        "temperature":       row.temperature,
        "retry_index":       row.retry_index,
        "status":            row.status,
        "error_message":     row.error_message,
        "http_status_code":  row.http_status_code,
        "system_prompt_len": row.system_prompt_len,
        "messages":          messages,
        "response":          response_parsed,
        "response_len":      row.response_len,
        "duration_ms":       row.duration_ms,
        "prompt_tokens":     row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "total_tokens":      row.total_tokens,
    }


@router.get("/logs/api", include_in_schema=False)
async def logs_api(
    agent:  str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit:  int        = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Aggregate in SQL — earlier code loaded every row of today_rows just to len/sum/avg.
    stats_row = db.query(
        func.count(AiCallLog.id),
        func.sum(case((AiCallLog.status == "success", 1), else_=0)),
        func.avg(AiCallLog.duration_ms),
        func.sum(AiCallLog.total_tokens),
    ).filter(AiCallLog.ts >= today_start).one()
    total_today        = stats_row[0] or 0
    success_today      = stats_row[1] or 0
    avg_dur            = float(stats_row[2] or 0)
    total_tokens_today = stats_row[3] or 0

    q = db.query(AiCallLog)
    if agent:
        q = q.filter(AiCallLog.agent == agent)
    if status:
        q = q.filter(AiCallLog.status == status)
    rows = q.order_by(desc(AiCallLog.ts)).limit(limit).all()

    return {
        "stats": {
            "total":           total_today,
            "success":         success_today,
            "error":           total_today - success_today,
            "avg_duration_ms": round(avg_dur, 1),
            "total_tokens":    total_tokens_today,
        },
        "rows": [
            {
                "id":               r.id,
                "ts":               r.ts.isoformat() if r.ts else None,
                "agent":            r.agent,
                "session_id":       r.session_id,
                "model":            r.model,
                "temperature":      r.temperature,
                "status":           r.status,
                "error_message":    r.error_message,
                "http_status_code": r.http_status_code,
                "retry_index":      r.retry_index,
                "duration_ms":      r.duration_ms,
                "prompt_tokens":    r.prompt_tokens,
                "completion_tokens":r.completion_tokens,
                "total_tokens":     r.total_tokens,
                "response_len":     r.response_len,
                "system_prompt_len":r.system_prompt_len,
            }
            for r in rows
        ],
    }


@router.get("/console", include_in_schema=False)
async def console_logs(
    lines: int = Query(default=300, ge=10, le=2000),
    _: None = Depends(require_admin),
):
    log_path = os.path.join("logs", "app.log")
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            tail = list(deque(f, maxlen=lines))
        return {"lines": [ln.rstrip("\n") for ln in tail], "path": log_path, "exists": True}
    except FileNotFoundError:
        return {"lines": [], "path": log_path, "exists": False}
    except Exception as exc:
        return {"lines": [f"读取失败: {exc}"], "path": log_path, "exists": True}


# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 监控</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#0f1117;color:#e2e8f0;font-size:14px}
/* header */
.hdr{padding:16px 24px;border-bottom:1px solid #1e2535;display:flex;
     align-items:center;gap:12px}
.hdr h1{font-size:17px;font-weight:600;color:#f1f5f9}
.hdr .sub{color:#64748b;font-size:12px}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.btn{background:#1e40af;color:#fff;border:none;padding:5px 14px;
     border-radius:6px;cursor:pointer;font-size:13px}
.btn:hover{background:#1d4ed8}
.auto-lbl{color:#94a3b8;font-size:12px;display:flex;align-items:center;gap:5px}
.spin{width:16px;height:16px;border:2px solid #334155;border-top-color:#3b82f6;
      border-radius:50%;animation:sp .8s linear infinite;display:none}
.spin.on{display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
/* tabs */
.tabs{display:flex;gap:0;padding:0 24px;border-bottom:1px solid #1e2535}
.tab-btn{padding:10px 18px;cursor:pointer;color:#64748b;font-size:13px;
         border:none;background:none;border-bottom:2px solid transparent;
         transition:color .15s}
.tab-btn.active{color:#3b82f6;border-bottom-color:#3b82f6}
.tab-btn:hover{color:#94a3b8}
.tab-pane{display:none}.tab-pane.active{display:block}
/* stats */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;
       padding:16px 24px}
.sc{background:#161b27;border:1px solid #1e2535;border-radius:9px;
    padding:13px 15px}
.sc .lbl{color:#64748b;font-size:11px;text-transform:uppercase;
         letter-spacing:.05em;margin-bottom:5px}
.sc .val{font-size:22px;font-weight:700;color:#f1f5f9}
.sc.err .val{color:#f87171}.sc.ok .val{color:#4ade80}
/* filters */
.flt{padding:0 24px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.flt select,.flt input{background:#161b27;border:1px solid #1e2535;
  color:#e2e8f0;padding:5px 9px;border-radius:6px;font-size:13px;outline:none}
.flt select:focus,.flt input:focus{border-color:#3b82f6}
.flt label{color:#64748b;font-size:12px}
/* table */
.tbl-wrap{overflow-x:auto;padding:0 24px 40px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead tr{border-bottom:1px solid #1e2535}
th{text-align:left;padding:7px 11px;color:#64748b;font-weight:500;
   font-size:11px;text-transform:uppercase;letter-spacing:.04em}
td{padding:8px 11px;border-bottom:1px solid #131929;vertical-align:middle}
tr.data-row{cursor:pointer}
tr.data-row:hover td{background:#161b27}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;
       font-size:11px;font-weight:600}
.badge.success{background:#14532d;color:#4ade80}
.badge.error{background:#450a0a;color:#f87171}
.rc{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;
    background:#1e293b;color:#94a3b8}
.rc.r1{background:#422006;color:#fb923c}
.rc.r2{background:#450a0a;color:#f87171}
.mono{font-family:"SF Mono","Fira Code",monospace;font-size:12px}
.dim{color:#64748b}
.err-cell{color:#f87171;font-size:12px;max-width:220px;
          overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar{display:inline-block;height:3px;background:#1e40af;border-radius:2px;
     margin-left:5px;vertical-align:middle;opacity:.7}
.empty{text-align:center;padding:40px;color:#475569}
/* modal */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:100;
         display:flex;align-items:flex-start;justify-content:center;
         overflow-y:auto;padding:40px 20px}
.modal{background:#161b27;border:1px solid #1e2535;border-radius:12px;
       width:100%;max-width:900px;padding:0}
.modal-hdr{padding:16px 20px;border-bottom:1px solid #1e2535;
           display:flex;align-items:center;gap:10px}
.modal-hdr h3{font-size:15px;font-weight:600}
.modal-close{margin-left:auto;background:none;border:none;color:#64748b;
             font-size:20px;cursor:pointer;line-height:1}
.modal-body{padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.modal-full{grid-column:1/-1}
.panel{background:#0f1117;border:1px solid #1e2535;border-radius:8px;
       padding:14px}
.panel h4{font-size:11px;color:#64748b;text-transform:uppercase;
          letter-spacing:.05em;margin-bottom:10px}
.kv{display:grid;grid-template-columns:130px 1fr;gap:4px 8px;font-size:12px}
.kv .k{color:#64748b}
.kv .v{color:#e2e8f0;word-break:break-all}
pre.code{background:#0f1117;border:1px solid #1e2535;border-radius:6px;
         padding:12px;font-size:11px;font-family:"SF Mono","Fira Code",monospace;
         overflow-x:auto;white-space:pre-wrap;word-break:break-all;
         max-height:360px;overflow-y:auto;color:#a5f3fc}
.loading-txt{color:#64748b;font-size:13px;text-align:center;padding:20px}
/* console tab */
.console-bar{padding:12px 24px;display:flex;gap:8px;align-items:center}
.console-bar input{flex:1;background:#161b27;border:1px solid #1e2535;
  color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:13px;outline:none}
.console-bar input:focus{border-color:#3b82f6}
.log-box{margin:0 24px 40px;background:#0a0d14;border:1px solid #1e2535;
         border-radius:8px;overflow:auto;height:620px;padding:12px 14px;
         font-family:"SF Mono","Fira Code",monospace;font-size:12px;
         line-height:1.6}
.ll{white-space:pre-wrap;word-break:break-all}
.ll.info{color:#94a3b8}
.ll.warn{color:#fbbf24}
.ll.error{color:#f87171}
.ll.debug{color:#475569}
.ll.hi{background:#1e3a5f}
.last-upd{color:#475569;font-size:12px;margin-left:auto}
</style>
</head>
<body>

<div class="hdr">
  <div><h1>AI 监控</h1><div class="sub">love-profiler · ai_call_logs</div></div>
  <div id="spin" class="spin"></div>
  <div class="hdr-right">
    <label class="auto-lbl"><input type="checkbox" id="autoR" checked> 自动刷新 30s</label>
    <button class="btn" onclick="refreshAll()">立即刷新</button>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('calls',this)">📊 AI 调用</button>
  <button class="tab-btn" onclick="switchTab('console',this)">🖥 控制台日志</button>
</div>

<!-- ── Tab: AI Calls ─────────────────────────────────── -->
<div id="tab-calls" class="tab-pane active">
  <div class="stats">
    <div class="sc"><div class="lbl">今日调用</div><div class="val" id="s-tot">—</div></div>
    <div class="sc ok"><div class="lbl">成功</div><div class="val" id="s-ok">—</div></div>
    <div class="sc err"><div class="lbl">失败</div><div class="val" id="s-err">—</div></div>
    <div class="sc"><div class="lbl">平均耗时</div><div class="val" id="s-dur">—</div><div style="color:#64748b;font-size:11px">ms</div></div>
    <div class="sc"><div class="lbl">今日 Token</div><div class="val" id="s-tok">—</div></div>
  </div>
  <div class="flt">
    <label>Agent</label>
    <select id="fa" onchange="loadCalls()">
      <option value="">全部</option>
      <option value="agent_a">agent_a</option>
      <option value="agent_b">agent_b</option>
      <option value="agent1_chat">agent1_chat</option>
    </select>
    <label>状态</label>
    <select id="fs" onchange="loadCalls()">
      <option value="">全部</option>
      <option value="success">success</option>
      <option value="error">error</option>
    </select>
    <label>条数</label>
    <select id="fl" onchange="loadCalls()">
      <option value="50">50</option>
      <option value="100" selected>100</option>
      <option value="200">200</option>
    </select>
    <span id="lu1" class="last-upd"></span>
  </div>
  <div class="tbl-wrap">
  <table>
    <thead><tr>
      <th>时间</th><th>Agent</th><th>模型</th><th>Session</th><th>状态</th>
      <th>耗时</th><th>Prompt→Comp</th><th>重试</th>
      <th>System字符</th><th>响应字符</th><th>错误</th>
    </tr></thead>
    <tbody id="tbody"><tr><td colspan="11" class="empty">加载中…</td></tr></tbody>
  </table>
  </div>
</div>

<!-- ── Tab: Console ──────────────────────────────────── -->
<div id="tab-console" class="tab-pane">
  <div class="console-bar">
    <input id="search" placeholder="关键词过滤（支持正则）" oninput="filterConsole()">
    <label class="auto-lbl" style="white-space:nowrap">
      <input type="checkbox" id="autoScroll" checked> 滚动到底
    </label>
    <label>行数</label>
    <select id="cl" onchange="loadConsole()">
      <option value="200">200</option>
      <option value="500" selected>500</option>
      <option value="1000">1000</option>
    </select>
    <span id="lu2" class="last-upd"></span>
  </div>
  <div class="log-box" id="logbox"></div>
</div>

<!-- ── Detail Modal ──────────────────────────────────── -->
<div id="overlay" class="overlay" style="display:none" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-hdr">
      <h3 id="m-title">调用详情</h3>
      <span id="m-badge"></span>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body" id="m-body">
      <div class="loading-txt">加载中…</div>
    </div>
  </div>
</div>

<script>
// ── utils ──────────────────────────────────────────────
let _rawLines = [];

function fmtNum(n){
  if(n>=10000) return (n/1000).toFixed(1)+'k';
  return (n||0).toLocaleString();
}
function fmtTs(iso){
  const d=new Date(iso);
  const p=n=>String(n).padStart(2,'0');
  return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmt(ms){
  if(ms<1000) return ms+' ms';
  return (ms/1000).toFixed(2)+' s';
}
function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function prettyJson(v){
  if(typeof v==='string') return esc(v);
  try{ return esc(JSON.stringify(v,null,2)); }catch(e){ return esc(String(v)); }
}

// ── tabs ───────────────────────────────────────────────
function switchTab(name, btn){
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  btn.classList.add('active');
  if(name==='console') loadConsole();
}

// ── spinner ────────────────────────────────────────────
let _loading=0;
function startLoad(){ _loading++; document.getElementById('spin').classList.add('on'); }
function endLoad(){ if(--_loading<=0){ _loading=0; document.getElementById('spin').classList.remove('on'); } }

// ── AI Calls tab ───────────────────────────────────────
async function loadCalls(){
  const agent=document.getElementById('fa').value;
  const status=document.getElementById('fs').value;
  const limit=document.getElementById('fl').value;
  startLoad();
  try{
    const p=new URLSearchParams({limit});
    if(agent) p.set('agent',agent);
    if(status) p.set('status',status);
    const r=await fetch('/admin/logs/api?'+p);
    const data=await r.json();
    renderStats(data.stats);
    renderTable(data.rows);
    document.getElementById('lu1').textContent='更新于 '+new Date().toLocaleTimeString();
  }finally{ endLoad(); }
}

function renderStats(s){
  document.getElementById('s-tot').textContent=fmtNum(s.total);
  document.getElementById('s-ok').textContent=fmtNum(s.success);
  document.getElementById('s-err').textContent=fmtNum(s.error);
  document.getElementById('s-dur').textContent=s.avg_duration_ms?Math.round(s.avg_duration_ms):'—';
  document.getElementById('s-tok').textContent=fmtNum(s.total_tokens);
}

function renderTable(rows){
  const tb=document.getElementById('tbody');
  if(!rows.length){ tb.innerHTML='<tr><td colspan="11" class="empty">暂无数据</td></tr>'; return; }
  const maxDur=Math.max(...rows.map(r=>r.duration_ms),1);
  tb.innerHTML=rows.map(r=>{
    const badge=`<span class="badge ${r.status}">${r.status}</span>`;
    const rc=r.retry_index;
    const retry=`<span class="rc${rc>0?' r'+rc:''}">#${rc}</span>`;
    const err=r.error_message
      ?`<span class="err-cell" title="${esc(r.error_message)}">${esc(r.error_message)}</span>`
      :'<span class="dim">—</span>';
    const sess=r.session_id
      ?`<span class="mono dim" title="${r.session_id}">${r.session_id.slice(0,8)}</span>`
      :'<span class="dim">—</span>';
    const w=Math.min(50,Math.round(r.duration_ms/maxDur*50));
    const model=r.model?r.model.split('/').pop():'—';
    return `<tr class="data-row" onclick="openDetail(${r.id})">
      <td class="mono dim">${fmtTs(r.ts)}</td>
      <td><b>${esc(r.agent)}</b></td>
      <td class="mono dim" title="${esc(r.model||'')}">${esc(model)}</td>
      <td>${sess}</td>
      <td>${badge}</td>
      <td>${fmt(r.duration_ms)}<span class="bar" style="width:${w}px"></span></td>
      <td class="dim">${fmtNum(r.prompt_tokens)} → ${fmtNum(r.completion_tokens)}</td>
      <td>${retry}</td>
      <td class="dim">${fmtNum(r.system_prompt_len)}</td>
      <td class="dim">${fmtNum(r.response_len)}</td>
      <td>${err}</td>
    </tr>`;
  }).join('');
}

// ── Detail Modal ───────────────────────────────────────
async function openDetail(id){
  const ov=document.getElementById('overlay');
  const mb=document.getElementById('m-body');
  ov.style.display='flex';
  mb.innerHTML='<div class="loading-txt">加载中…</div>';
  startLoad();
  try{
    const r=await fetch(`/admin/logs/api/${id}`);
    const d=await r.json();
    document.getElementById('m-title').textContent=
      `#${d.id} · ${d.agent} · ${d.ts?fmtTs(d.ts):''}`;
    document.getElementById('m-badge').innerHTML=
      `<span class="badge ${d.status}">${d.status}</span>`;

    mb.innerHTML=`
      <div class="panel">
        <h4>基本信息</h4>
        <div class="kv">
          <span class="k">Agent</span><span class="v">${esc(d.agent)}</span>
          <span class="k">Session</span><span class="v mono">${esc(d.session_id||'—')}</span>
          <span class="k">Model</span><span class="v">${esc(d.model)}</span>
          <span class="k">Temperature</span><span class="v">${d.temperature}</span>
          <span class="k">Retry</span><span class="v">#${d.retry_index}</span>
          <span class="k">耗时</span><span class="v">${fmt(d.duration_ms)}</span>
          <span class="k">HTTP状态</span><span class="v">${d.http_status_code||'—'}</span>
        </div>
      </div>
      <div class="panel">
        <h4>Token 消耗</h4>
        <div class="kv">
          <span class="k">Prompt</span><span class="v">${fmtNum(d.prompt_tokens)}</span>
          <span class="k">Completion</span><span class="v">${fmtNum(d.completion_tokens)}</span>
          <span class="k">Total</span><span class="v"><b>${fmtNum(d.total_tokens)}</b></span>
          <span class="k">System Prompt</span><span class="v">${fmtNum(d.system_prompt_len)} 字符</span>
          <span class="k">响应长度</span><span class="v">${fmtNum(d.response_len)} 字符</span>
        </div>
        ${d.error_message?`<div style="margin-top:10px;color:#f87171;font-size:12px">错误: ${esc(d.error_message)}</div>`:''}
      </div>
      <div class="panel modal-full">
        <h4>请求 Messages（发送给 API 的用户消息）</h4>
        <pre class="code">${prettyJson(d.messages)}</pre>
      </div>
      <div class="panel modal-full">
        <h4>响应 Response（LLM 返回内容${d.response_len>2000?' — 仅显示前2000字':''}）</h4>
        <pre class="code">${prettyJson(d.response)}</pre>
      </div>
    `;
  }finally{ endLoad(); }
}

function closeModal(e){
  if(!e||e.target===document.getElementById('overlay'))
    document.getElementById('overlay').style.display='none';
}
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeModal(); });

// ── Console tab ────────────────────────────────────────
const LEVEL_RE=/\[(ERROR|WARNING|WARN|INFO|DEBUG)\]/i;

function colorLine(raw){
  const m=raw.match(LEVEL_RE);
  if(!m) return `<div class="ll info">${esc(raw)}</div>`;
  const lv=m[1].toUpperCase();
  const cls=lv==='ERROR'?'error':lv==='WARNING'||lv==='WARN'?'warn':lv==='DEBUG'?'debug':'info';
  return `<div class="ll ${cls}">${esc(raw)}</div>`;
}

function filterConsole(){
  const q=document.getElementById('search').value.trim();
  const box=document.getElementById('logbox');
  let lines=_rawLines;
  if(q){
    try{
      const re=new RegExp(q,'i');
      lines=lines.filter(l=>re.test(l));
    }catch(e){
      lines=lines.filter(l=>l.toLowerCase().includes(q.toLowerCase()));
    }
  }
  box.innerHTML=lines.map(colorLine).join('');
  if(document.getElementById('autoScroll').checked)
    box.scrollTop=box.scrollHeight;
}

async function loadConsole(){
  const lines=document.getElementById('cl').value;
  startLoad();
  try{
    const r=await fetch(`/admin/console?lines=${lines}`);
    const d=await r.json();
    _rawLines=d.lines||[];
    filterConsole();
    document.getElementById('lu2').textContent='更新于 '+new Date().toLocaleTimeString();
  }finally{ endLoad(); }
}

// ── auto refresh ───────────────────────────────────────
function refreshAll(){
  const tab=document.querySelector('.tab-pane.active');
  if(tab&&tab.id==='tab-calls') loadCalls();
  else loadConsole();
}

let _timer=null;
document.getElementById('autoR').addEventListener('change',function(){
  if(this.checked){ _timer=setInterval(refreshAll,30000); }
  else{ clearInterval(_timer); _timer=null; }
});

loadCalls();
_timer=setInterval(refreshAll,30000);
</script>
</body>
</html>"""


@router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
async def logs_dashboard(_: None = Depends(require_admin)):
    return HTMLResponse(content=_HTML)
