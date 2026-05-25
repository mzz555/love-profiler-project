"""
Admin dashboard — data browsing, AI call log monitor, metrics.

Endpoints:
  GET /admin                     Redirect to SPA
  GET /admin/api/overview        Business table stats
  GET /admin/api/audits          Report quality audit list
  GET /admin/api/metrics/*       LLM / business / quality metrics
  GET /admin/api/{table}         Paginated table list
  GET /admin/api/{table}/{id}    Single row detail
  PUT /admin/api/{table}/{id}    Update editable fields
  GET /admin/logs                HTML dashboard (AI call monitor)
  GET /admin/logs/api            JSON: stats + call log rows
  GET /admin/logs/api/{id}       JSON: full detail for one row
  GET /admin/console             JSON: last N lines from logs/app.log

Access: requires DEV_MODE=true OR ADMIN_TOKEN env var.
"""

import json
import os
import pathlib
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc, func, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.orm import defer

from app.database import get_db
from app.models.ai_call_log import AiCallLog
from app.models.assessment import Assessment
from app.models.report_quality_audit import ReportQualityAudit
from app.services.admin_metrics import (
    compute_business_metrics,
    compute_llm_metrics,
    compute_quality_score_distribution,
)
from app.api.admin_config import TABLE_CONFIG
from app.api.admin_helpers import get_row, query_table, update_row
from app.limiter import limiter


def _utc_today_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Access guard
# ---------------------------------------------------------------------------

def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if os.environ.get("DEV_MODE", "").lower() == "true":
        return
    expected = os.environ.get("ADMIN_TOKEN", "")
    if expected and x_admin_token == expected:
        return
    raise HTTPException(status_code=404)


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def admin_root(_: None = Depends(require_admin)) -> RedirectResponse:
    return RedirectResponse(url="/static/admin/index.html")


@router.get("/api/overview", include_in_schema=False)
@limiter.limit("30/minute")
async def admin_overview(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    today_start = _utc_today_start()
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
        except (OperationalError, ProgrammingError):
            result["tables"][table] = {"total": 0, "today": 0}

    for status_table in ("assessments", "orders"):
        try:
            rows = db.execute(
                text(f"SELECT status, COUNT(*) AS cnt FROM {status_table} GROUP BY status")
            ).fetchall()
            result["tables"][status_table]["by_status"] = {r.status: r.cnt for r in rows}
        except (OperationalError, ProgrammingError):
            pass

    try:
        rows = db.execute(
            text("SELECT id, session_id, personality_type, status, created_at "
                 "FROM assessments ORDER BY id DESC LIMIT 5")
        ).fetchall()
        result["recent_assessments"] = [dict(r._mapping) for r in rows]
    except (OperationalError, ProgrammingError):
        pass

    return result


@router.get("/api/audits", include_in_schema=False)
async def list_audits(
    limit:  int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    overall_stats = db.query(
        func.count(ReportQualityAudit.id),
        func.avg(ReportQualityAudit.overall_score),
        func.avg(ReportQualityAudit.coherence_score),
        func.avg(ReportQualityAudit.readability_score),
        func.avg(ReportQualityAudit.factual_score),
    ).one()

    rows = (
        db.query(
            ReportQualityAudit.id, ReportQualityAudit.created_at,
            ReportQualityAudit.assessment_id, ReportQualityAudit.judge_model,
            ReportQualityAudit.prompt_version, ReportQualityAudit.coherence_score,
            ReportQualityAudit.readability_score, ReportQualityAudit.factual_score,
            ReportQualityAudit.overall_score, ReportQualityAudit.summary,
            ReportQualityAudit.duration_ms, Assessment.personality_type,
        )
        .outerjoin(Assessment, Assessment.id == ReportQualityAudit.assessment_id)
        .order_by(desc(ReportQualityAudit.created_at))
        .limit(limit)
        .all()
    )

    def _avg(v):
        return round(float(v), 2) if v is not None else None

    return {
        "stats": {
            "total": overall_stats[0] or 0,
            "avg_overall": _avg(overall_stats[1]),
            "avg_coherence": _avg(overall_stats[2]),
            "avg_readability": _avg(overall_stats[3]),
            "avg_factual": _avg(overall_stats[4]),
        },
        "rows": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "assessment_id": r.assessment_id, "judge_model": r.judge_model,
                "prompt_version": r.prompt_version,
                "coherence_score": r.coherence_score, "readability_score": r.readability_score,
                "factual_score": r.factual_score, "overall_score": r.overall_score,
                "summary": r.summary, "duration_ms": r.duration_ms,
                "personality_type": r.personality_type,
            }
            for r in rows
        ],
    }


@router.get("/api/metrics/llm", include_in_schema=False)
async def metrics_llm(
    hours: int = Query(default=24, ge=1, le=168),
    top_n: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
):
    return compute_llm_metrics(db, hours=hours, top_n=top_n)


@router.get("/api/metrics/business", include_in_schema=False)
async def metrics_business(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
):
    return compute_business_metrics(db, days=days)


@router.get("/api/metrics/quality", include_in_schema=False)
async def metrics_quality(
    days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
):
    return compute_quality_score_distribution(db, days=days)


@router.get("/api/{table_name}", include_in_schema=False)
@limiter.limit("30/minute")
async def admin_table_list(
    request: Request,
    table_name: str = Path(...), page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200), q: str | None = Query(default=None),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return query_table(db, table_name, TABLE_CONFIG[table_name], page, limit, q)


@router.get("/api/{table_name}/{record_id}", include_in_schema=False)
async def admin_table_detail(
    table_name: str = Path(...), record_id: str = Path(...),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return get_row(db, table_name, TABLE_CONFIG[table_name], record_id)


@router.put("/api/{table_name}/{record_id}", include_in_schema=False)
@limiter.limit("30/minute")
async def admin_table_update(
    request: Request,
    table_name: str = Path(...), record_id: str = Path(...),
    body: dict = Body(...),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
) -> dict:
    if table_name not in TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"未知的表: {table_name}")
    return update_row(db, table_name, TABLE_CONFIG[table_name], record_id, body)


@router.get("/logs/api/{log_id}", include_in_schema=False)
async def log_detail(
    log_id: int = Path(...),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
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
        "id": row.id, "ts": row.ts.isoformat() if row.ts else None,
        "agent": row.agent, "session_id": row.session_id,
        "model": row.model, "temperature": row.temperature,
        "retry_index": row.retry_index, "status": row.status,
        "error_message": row.error_message, "http_status_code": row.http_status_code,
        "system_prompt_len": row.system_prompt_len,
        "messages": messages, "response": response_parsed,
        "response_len": row.response_len, "duration_ms": row.duration_ms,
        "prompt_tokens": row.prompt_tokens, "completion_tokens": row.completion_tokens,
        "total_tokens": row.total_tokens,
    }


@router.get("/logs/api", include_in_schema=False)
async def logs_api(
    agent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db), _: None = Depends(require_admin),
):
    today_start = _utc_today_start()
    stats_row = db.query(
        func.count(AiCallLog.id),
        func.sum(case((AiCallLog.status == "success", 1), else_=0)),
        func.avg(AiCallLog.duration_ms),
        func.sum(AiCallLog.total_tokens),
    ).filter(AiCallLog.ts >= today_start).one()

    q = db.query(AiCallLog).options(
        defer(AiCallLog.messages_json), defer(AiCallLog.response_preview),
    )
    if agent:
        q = q.filter(AiCallLog.agent == agent)
    if status:
        q = q.filter(AiCallLog.status == status)
    rows = q.order_by(desc(AiCallLog.ts)).limit(limit).all()

    return {
        "stats": {
            "total": stats_row[0] or 0, "success": stats_row[1] or 0,
            "error": (stats_row[0] or 0) - (stats_row[1] or 0),
            "avg_duration_ms": round(float(stats_row[2] or 0), 1),
            "total_tokens": stats_row[3] or 0,
        },
        "rows": [
            {
                "id": r.id, "ts": r.ts.isoformat() if r.ts else None,
                "agent": r.agent, "session_id": r.session_id,
                "model": r.model, "temperature": r.temperature,
                "status": r.status, "error_message": r.error_message,
                "http_status_code": r.http_status_code, "retry_index": r.retry_index,
                "duration_ms": r.duration_ms, "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens, "total_tokens": r.total_tokens,
                "response_len": r.response_len, "system_prompt_len": r.system_prompt_len,
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


_LOGS_HTML_PATH = pathlib.Path(__file__).parents[2] / "static" / "admin" / "logs.html"


@router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
async def logs_dashboard(_: None = Depends(require_admin)):
    return HTMLResponse(content=_LOGS_HTML_PATH.read_text(encoding="utf-8"))
