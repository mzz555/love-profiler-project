"""
WebSocket result endpoint — streams report writer report generation token by token.
GET /ws/result?token=<jwt>

Protocol (server → client JSON messages):
  {"type": "meta",          "personality_type": "...", "type_name": "...", "dim_chart": {...}}
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
import time

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.agents.report_writer import (
    ReportWriterError,
    PROMPT_VERSION,
    REPORT_VERSION,
    run_stream as report_stream,
)
from app.database import get_db
from app.middleware.auth import TOKEN_ALGORITHM, _jwt_secret
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


@router.websocket("/ws/result")
async def ws_result(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    """Accept WebSocket, stream report writer portrait text token by token, then send full report."""
    token = websocket.query_params.get("token", "")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[TOKEN_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
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
            # Another connection (or the polling endpoint) is already running report writer.
            # The frontend should reconnect once it sees a "complete" via /result.
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


async def _send(ws: WebSocket, data: dict) -> None:
    await ws.send_text(json.dumps(data, ensure_ascii=False))


_SEC_RE = re.compile(r'--([A-Za-z]+)--')


class _SectionStreamer:
    """Detects --Section-- markers in streaming text and sends typed WS messages.

    Phase C.1：可选 ``on_section_complete`` 回调在每个 section_end 触发，
    入参 (section_name, full_text)；ws_result 用它把段文本写入
    assessments.partial_sections 实现断点续传。
    """

    def __init__(self, ws, send_fn, on_section_complete=None):
        self._ws = ws
        self._send = send_fn
        self._buf = ""
        self._cur = None
        self._cur_text = ""  # 当前 section 累积文本，用于 on_section_complete
        self._on_section_complete = on_section_complete

    async def feed(self, text: str) -> None:
        self._buf += text
        await self._process()

    async def _emit_chunk(self, section: str, text: str) -> None:
        await self._send(self._ws, {
            "type": "section_chunk", "section": section, "text": text,
        })
        self._cur_text += text

    async def _finish_current_section(self) -> None:
        if not self._cur:
            return
        await self._send(self._ws, {"type": "section_end", "section": self._cur})
        if self._on_section_complete is not None:
            try:
                await self._on_section_complete(self._cur, self._cur_text)
            except Exception as exc:
                logger.warning("[ws/result] on_section_complete 回调失败 section=%s: %s",
                               self._cur, exc)
        self._cur_text = ""

    async def _process(self) -> None:
        while True:
            m = _SEC_RE.search(self._buf)
            if not m:
                safe = max(0, len(self._buf) - 20)
                if safe > 0 and self._cur:
                    chunk = self._buf[:safe]
                    if chunk:
                        await self._emit_chunk(self._cur, chunk)
                    self._buf = self._buf[safe:]
                break

            pre = self._buf[:m.start()]
            if pre and self._cur:
                await self._emit_chunk(self._cur, pre)
            await self._finish_current_section()
            self._cur = m.group(1)
            await self._send(self._ws, {"type": "section_start", "section": self._cur})
            self._buf = self._buf[m.end():]

    async def done(self) -> None:
        remaining = self._buf.strip()
        if remaining and self._cur:
            await self._emit_chunk(self._cur, remaining)
        await self._finish_current_section()
        self._buf = ""
        self._cur = None


def _dim_chart(diagnosis: dict) -> dict:
    """Convert diagnosis dimensions to structured chart data for 3 separate canvas charts."""
    dims = diagnosis.get("dimensions", {})

    # D1/D2/D3 — raw score (-12 to +12) + interp label
    _names = {"D1": "依恋安全", "D2": "边界清晰", "D3": "冲突健康"}
    d123 = [
        {
            "key": k,
            "name": _names[k],
            "raw": dims.get(k, {}).get("raw", 0),
            "interp": dims.get(k, {}).get("interp", "mixed"),
        }
        for k in ("D1", "D2", "D3")
    ]

    # D4 — all 5 normalized love-language scores (0.0-1.0)
    d4_norm = dims.get("D4", {}).get("normalized", {t: 0.0 for t in ("T1","T2","T3","T4","T5")})

    # D5 — s1/s2 labels for quadrant grid
    d5 = dims.get("D5", {})

    return {
        "d123": d123,
        "d4": d4_norm,
        "d5": {
            "s1":     d5.get("s1", "中直接"),
            "s2":     d5.get("s2", "中分享"),
            "s1_raw": d5.get("s1_raw", 0),
            "s2_raw": d5.get("s2_raw", 0),
        },
    }


def _all_labels(diagnosis: dict) -> list:
    """
    组合 D1-D5 全部维度的人格卡展示标签，随 meta 消息下发。
    - D1/D2/D3: 来自 segment_decode，带 is_healthy（健康/问题端配色）
    - D4:       top2 爱的语言名称，is_neutral=True（蓝色调，无健康属性）
    - D5:       亲密风格象限名，is_neutral=True
    """
    labels = list(diagnosis.get("segment_decode", []))

    # D4: top2 爱的语言，各显示一枚标签
    for item in diagnosis.get("D4_details", []):
        labels.append({
            "dimension":  "D4",
            "code":       item.get("code", ""),
            "label_cn":   item.get("name", ""),
            "is_neutral": True,
        })

    # D5: 一枚象限风格标签
    d5_style = diagnosis.get("D5_style_name", "")
    d5_quadrant = (diagnosis.get("dimensions", {}) or {}).get("D5", {}).get("quadrant", "")
    if d5_style or d5_quadrant:
        labels.append({
            "dimension":  "D5",
            "code":       d5_quadrant,
            "label_cn":   d5_style or d5_quadrant,
            "is_neutral": True,
        })

    return labels


def _highlights_meta(diagnosis: dict) -> list:
    """从诊断结果提取 highlights 标题/严重度，随 meta 消息下发，无需等 report writer。"""
    return [
        {
            "idx":         i + 1,
            "title":       h.get("name_cn", ""),
            "severity":    h.get("severity", "medium"),
            "is_positive": h.get("is_positive", False),
        }
        for i, h in enumerate(diagnosis.get("highlights", []))
    ]


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
    """Phase C.1 接续生成总开关；默认开。豆包效果不好时可设 false 临时回退。"""
    import os
    return os.environ.get("RESUME_ENABLED", "true").lower() != "false"


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

    # Send type metadata immediately — user sees their result while LLM writes
    await _send(websocket, {
        "type": "meta",
        "personality_type": ptype,
        "type_name": type_name,
        "type_tagline": type_tagline,
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
