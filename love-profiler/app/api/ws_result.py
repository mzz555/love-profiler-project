"""
WebSocket result endpoint — streams report writer report generation token by token.
GET /ws/result?ticket=<one-time-ticket>

Flow:
  1. POST /ws/ticket  (Bearer JWT) → {"ticket": "xxx"}  (30s 有效，一次性)
  2. WS   /ws/result?ticket=xxx    → stream

Protocol (server → client JSON messages):
  {"type": "meta",          "personality_type": "...", "type_name": "...", "type_detail": "...", "dim_chart": {...}}
  {"type": "section_start", "section": "Title"}            — new section begins
  {"type": "section_chunk", "section": "Title", "text": "..."} — text tokens
  {"type": "section_end",   "section": "Title"}            — section complete
  {"type": "portrait_chunk","text": "..."}                 — legacy fallback only
  {"type": "done",          "personality_type": "...", "report_json": {...}}
  {"type": "error",         "code": 4xx, "message": "..."}

Client → server (first message after connect):
  {"session_id": "xxxx"}
"""

import asyncio
import json
import logging
import re
import secrets
import time

import jwt
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.agents.report_writer import (
    ReportWriterError,
    PROMPT_VERSION,
    REPORT_VERSION,
    run_stream as report_stream,
)
from app.api.ws_helpers import (
    SectionStreamer,
    all_labels,
    dim_chart,
    highlights_meta,
    send as _send,
)
from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import TOKEN_ALGORITHM, _jwt_secret, get_current_user_id
from app.models.assessment import Assessment
from app.services.access_control import is_unlocked
from app.services.llm_client import LLMError
from app.services.report_audit import schedule_audit
from app.services.token_quota import (
    QuotaExceededError,
    add_usage as quota_add_usage,
    check_quota,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Cached-replay tuning. The WS uses larger chunks than SSE because the protocol
# overhead per message is higher; net result is a smooth ~3s replay for a typical
# 2000-char report instead of the previous 10s.
_REPLAY_CHUNK = 32
_REPLAY_DELAY = 0.01

_MAX_WS_CONCURRENT = 50
_ws_active = 0

_TICKET_TTL = 30
_tickets: dict[str, tuple[int, float]] = {}


def _cleanup_tickets() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _tickets.items() if now - ts > _TICKET_TTL]
    for k in expired:
        del _tickets[k]


def _consume_ticket(ticket: str) -> int | None:
    _cleanup_tickets()
    entry = _tickets.pop(ticket, None)
    if entry is None:
        return None
    user_id, created = entry
    if time.time() - created > _TICKET_TTL:
        return None
    return user_id


@router.post("/ws/ticket")
@limiter.limit("10/minute")
async def create_ws_ticket(
    request: Request,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    _cleanup_tickets()
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = (user_id, time.time())
    return {"ticket": ticket}


@router.websocket("/ws/result")
async def ws_result(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    """Accept WebSocket, stream report writer portrait text token by token, then send full report."""
    global _ws_active
    if _ws_active >= _MAX_WS_CONCURRENT:
        await websocket.accept()
        await _send(websocket, {"type": "error", "code": 503, "message": "服务器繁忙，请稍后重试"})
        await websocket.close(code=1013)
        return
    _ws_active += 1

    try:
        ticket = websocket.query_params.get("ticket", "")
        token = websocket.query_params.get("token", "")
        user_id = None
        if ticket:
            user_id = _consume_ticket(ticket)
        if user_id is None and token:
            try:
                payload = jwt.decode(token, _jwt_secret(), algorithms=[TOKEN_ALGORITHM])
                user_id = int(payload["sub"])
            except Exception:
                pass
        if user_id is None:
            await websocket.accept()
            await websocket.close(code=4001)
            return

        await websocket.accept()
        logger.info("[ws/result] user_id=%s 连接建立", user_id)

        try:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            session_id = data.get("session_id", "")

            assessment = (
                db.query(Assessment)
                .filter(Assessment.session_id == session_id, Assessment.user_id == user_id)
                .first()
            )
            if assessment is None:
                await _send(websocket, {"type": "error", "code": 404, "message": "Assessment not found"})
                return

            if assessment.status == "pending":
                await _send(websocket, {"type": "error", "code": 400, "message": "Quiz not submitted"})
                return

            if not is_unlocked(db, assessment.id, user_id):
                await _send(websocket, {"type": "error", "code": 402, "message": "报告未解锁"})
                return

            if assessment.status == "complete" and assessment.report_text:
                await _stream_cached(websocket, assessment)
            elif assessment.status == "analyzed" and assessment.diagnosis_json:
                try:
                    check_quota(db, user_id=user_id)
                except QuotaExceededError as exc:
                    logger.warning("[ws/result] user_id=%s 配额超限 used=%d limit=%d",
                                   user_id, exc.used, exc.limit)
                    await _send(websocket, {
                        "type": "error", "code": 429,
                        "message": "今日测评次数已达上限，请明天再来",
                    })
                    return
                await _stream_agent_b(websocket, db, assessment, session_id, user_id=user_id)
            elif assessment.status == "generating":
                await _send(websocket, {"type": "error", "code": 409, "message": "报告正在生成中，请稍后重连"})
            else:
                await _send(websocket, {"type": "error", "code": 400, "message": "Diagnosis not available"})

        except WebSocketDisconnect:
            logger.info("[ws/result] user_id=%s 断开", user_id)
        except Exception as exc:
            logger.exception("[ws/result] 未预期错误: %s", exc)
            try:
                await _send(websocket, {"type": "error", "code": 500})
            except Exception:
                pass
    finally:
        _ws_active -= 1


_SectionStreamer = SectionStreamer


_dim_chart = dim_chart
_all_labels = all_labels
_highlights_meta = highlights_meta


def _release_claim(db: Session, assessment_id: int) -> None:
    """Reset status from 'generating' back to 'analyzed' so the user can retry on reconnect."""
    db.query(Assessment).filter(
        Assessment.id == assessment_id, Assessment.status == "generating",
    ).update({"status": "analyzed"}, synchronize_session=False)
    db.commit()


async def _stream_cached(websocket: WebSocket, assessment: Assessment) -> None:
    """Replay already-generated report_text char-by-char for consistent UX."""
    text = assessment.report_text or ""
    ptype = assessment.personality_type or ""
    diagnosis = json.loads(assessment.diagnosis_json) if assessment.diagnosis_json else {}
    type_name = diagnosis.get("type_name", "")

    await _send(websocket, {
        "type": "meta",
        "personality_type": ptype,
        "type_name": type_name,
        "type_tagline": diagnosis.get("type_tagline", ""),
        "type_detail": diagnosis.get("type_detail", ""),
        "img_path": diagnosis.get("img_path", ""),
        "dim_chart": _dim_chart(diagnosis),
        "highlights_meta": _highlights_meta(diagnosis),
        "segment_decode": _all_labels(diagnosis),
    })

    # 新格式（含 --Section-- 标记）用 section 流；旧格式用 portrait_chunk 兜底
    if '--Title--' in text:
        streamer = _SectionStreamer(websocket, _send)
        for i in range(0, len(text), _REPLAY_CHUNK):
            await streamer.feed(text[i:i + _REPLAY_CHUNK])
            await asyncio.sleep(_REPLAY_DELAY)
        await streamer.done()
    else:
        for i in range(0, len(text), _REPLAY_CHUNK):
            await _send(websocket, {"type": "portrait_chunk", "text": text[i:i + _REPLAY_CHUNK]})
            await asyncio.sleep(_REPLAY_DELAY)

    rj = json.loads(assessment.report_json) if assessment.report_json else {}
    await _send(websocket, {"type": "done", "personality_type": ptype, "report_json": rj})
    logger.info("[ws/result] 缓存流完成 type=%s chars=%d", ptype, len(text))


def _resume_enabled() -> bool:
    from app.config import settings as _s
    return _s.resume_enabled


def _load_partial_sections(rec: Assessment) -> dict[str, str]:
    """从 assessments.partial_sections 反序列化已落库 section dict。"""
    raw = rec.partial_sections
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items() if v}
    except (TypeError, ValueError):
        pass
    return {}


async def _stream_agent_b(
    websocket: WebSocket,
    db: Session,
    assessment: Assessment,
    session_id: str,
    user_id: int,
) -> None:
    """Run report writer with real LLM streaming, forward tokens, persist on completion."""
    diagnosis = json.loads(assessment.diagnosis_json)
    assessment_id = assessment.id

    # Phase C.1：读已落库的 partial_sections（上次中断时残留）
    resumed = _load_partial_sections(assessment) if _resume_enabled() else {}

    t0 = time.monotonic()
    t_first_token: float | None = None

    # Race guard — if two clients connect at once, only the first reservation wins
    # (analyzed → generating). The loser sees a 409 and can reconnect later.
    claimed = (
        db.query(Assessment)
        .filter(Assessment.id == assessment_id, Assessment.status == "analyzed")
        .update({"status": "generating"}, synchronize_session=False)
    )
    db.commit()
    if claimed == 0:
        await _send(websocket, {"type": "error", "code": 409, "message": "报告正在生成中，请稍后重连"})
        return

    ptype      = diagnosis.get("type_code", "")
    type_name  = diagnosis.get("type_name", "")
    type_tagline = diagnosis.get("type_tagline", "")

    type_detail = diagnosis.get("type_detail", "")

    # Send type metadata immediately — user sees their result while LLM writes
    await _send(websocket, {
        "type": "meta",
        "personality_type": ptype,
        "type_name": type_name,
        "type_tagline": type_tagline,
        "type_detail": type_detail,
        "img_path": diagnosis.get("img_path", ""),
        "dim_chart": _dim_chart(diagnosis),
        "highlights_meta": _highlights_meta(diagnosis),
        "segment_decode": _all_labels(diagnosis),
        # 把已恢复的段告知前端（用于 UI 上"接续生成中"提示）
        "resumed_sections": sorted(resumed.keys()) if resumed else [],
    })

    # 把已完成 sections replay 给前端，保证 UI 完整
    if resumed:
        replay_streamer = _SectionStreamer(websocket, _send)
        from app.agents.report_writer import SECTION_ORDER
        replay_text = "".join(
            f"--{name}--\n{resumed[name]}\n"
            for name in SECTION_ORDER
            if name in resumed
        )
        for i in range(0, len(replay_text), _REPLAY_CHUNK):
            await replay_streamer.feed(replay_text[i:i + _REPLAY_CHUNK])
        await replay_streamer.done()
        logger.info("[ws/result] 已 replay %d 个 resumed sections: %s",
                    len(resumed), sorted(resumed.keys()))

    # 主流：on_section_complete 回调把每段写入 partial_sections，下次中断可续
    partial_sections: dict[str, str] = dict(resumed)

    async def _persist_section(name: str, text: str) -> None:
        partial_sections[name] = text
        rec_now = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if rec_now is not None:
            rec_now.partial_sections = json.dumps(partial_sections, ensure_ascii=False)
            db.commit()

    full_text = ""
    final_report = None

    streamer = _SectionStreamer(websocket, _send, on_section_complete=_persist_section)
    # 只在确实有 resumed 时才传 kwarg，保持对老 report_writer.run_stream 签名（含测试 mock）兼容
    extra_kwargs = {"resumed_sections": resumed} if resumed else {}
    try:
        async for item in report_stream(
            diagnosis,
            session_id=session_id,
            **extra_kwargs,
        ):
            if isinstance(item, str):
                if t_first_token is None:
                    t_first_token = time.monotonic()
                full_text += item
                await streamer.feed(item)
            else:
                final_report = item
        await streamer.done()
    except (ReportWriterError, LLMError) as exc:
        logger.error("[ws/result] agent_b 流式失败 %.0fms: %s", (time.monotonic() - t0) * 1000, exc)
        # 保留 partial_sections 供下次接续，仅状态回滚到 analyzed
        _release_claim(db, assessment_id)
        await _send(websocket, {"type": "error", "code": 502, "message": "报告生成失败，请重试"})
        return

    if final_report is None:
        _release_claim(db, assessment_id)
        await _send(websocket, {"type": "error", "code": 502, "message": "报告生成失败"})
        return

    report_text = final_report.get("report_text", full_text.strip())
    prompt_tokens = int(final_report.get("prompt_tokens", 0) or 0)
    completion_tokens = int(final_report.get("completion_tokens", 0) or 0)

    rec = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if rec:
        rec.report_json = json.dumps({"raw_llm_output": report_text}, ensure_ascii=False)
        rec.personality_type = ptype
        rec.report_text = report_text
        rec.status = "complete"
        rec.prompt_version = PROMPT_VERSION
        rec.report_version = REPORT_VERSION
        # 完成后清空 partial_sections，避免占空间
        rec.partial_sections = None
        db.commit()

    try:
        quota_add_usage(
            db, user_id=user_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:  # 配额写失败不该阻塞已经成功的报告
        logger.warning("[ws/result] quota_add_usage 失败 user_id=%s: %s", user_id, exc)

    # D.2：异步触发审计（JUDGE_ENABLED=false 时是 no-op）
    schedule_audit(assessment_id, session_id=session_id)

    ttft_ms  = int((t_first_token - t0) * 1000) if t_first_token else -1
    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[ws/result] agent_b 完成 type=%s chars=%d tokens=%d+%d TTFT=%dms total=%dms",
        ptype, len(report_text),
        prompt_tokens, completion_tokens,
        ttft_ms, total_ms,
    )

    await _send(websocket, {
        "type": "done",
        "personality_type": ptype,
        "report_json": {"raw_llm_output": report_text},
    })
