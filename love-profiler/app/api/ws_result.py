"""
WebSocket result endpoint — streams Agent B report generation token by token.
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

from app.agents.agent_b import AgentBError, run_stream as agent_b_run_stream
from app.database import get_db
from app.middleware.auth import TOKEN_ALGORITHM, _jwt_secret
from app.models.assessment import Assessment
from app.services.access_control import is_unlocked
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)
router = APIRouter()

# Cached-replay tuning. The WS uses larger chunks than SSE because the protocol
# overhead per message is higher; net result is a smooth ~3s replay for a typical
# 2000-char report instead of the previous 10s.
_REPLAY_CHUNK = 32
_REPLAY_DELAY = 0.01


@router.websocket("/ws/result")
async def ws_result(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    """Accept WebSocket, stream Agent B portrait text token by token, then send full report."""
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
            await _stream_agent_b(websocket, db, assessment, session_id)
        elif assessment.status == "generating":
            # Another connection (or the polling endpoint) is already running Agent B.
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
    """Detects --Section-- markers in streaming text and sends typed WS messages."""

    def __init__(self, ws, send_fn):
        self._ws = ws
        self._send = send_fn
        self._buf = ""
        self._cur = None

    async def feed(self, text: str) -> None:
        self._buf += text
        await self._process()

    async def _process(self) -> None:
        while True:
            m = _SEC_RE.search(self._buf)
            if not m:
                safe = max(0, len(self._buf) - 20)
                if safe > 0 and self._cur:
                    chunk = self._buf[:safe]
                    if chunk:
                        await self._send(self._ws, {
                            "type": "section_chunk", "section": self._cur, "text": chunk,
                        })
                    self._buf = self._buf[safe:]
                break

            pre = self._buf[:m.start()]
            if pre and self._cur:
                await self._send(self._ws, {
                    "type": "section_chunk", "section": self._cur, "text": pre,
                })
            if self._cur:
                await self._send(self._ws, {"type": "section_end", "section": self._cur})
            self._cur = m.group(1)
            await self._send(self._ws, {"type": "section_start", "section": self._cur})
            self._buf = self._buf[m.end():]

    async def done(self) -> None:
        remaining = self._buf.strip()
        if remaining and self._cur:
            await self._send(self._ws, {
                "type": "section_chunk", "section": self._cur, "text": remaining,
            })
            await self._send(self._ws, {"type": "section_end", "section": self._cur})
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
    """从诊断结果提取 highlights 标题/严重度，随 meta 消息下发，无需等 Agent B。"""
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


async def _stream_agent_b(
    websocket: WebSocket,
    db: Session,
    assessment: Assessment,
    session_id: str,
) -> None:
    """Run Agent B with real LLM streaming, forward tokens, persist on completion."""
    diagnosis = json.loads(assessment.diagnosis_json)
    assessment_id = assessment.id

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
        "dim_chart": _dim_chart(diagnosis),
        "highlights_meta": _highlights_meta(diagnosis),
        "segment_decode": _all_labels(diagnosis),
    })

    full_text = ""
    final_report = None

    streamer = _SectionStreamer(websocket, _send)
    try:
        async for item in agent_b_run_stream(diagnosis, session_id=session_id):
            if isinstance(item, str):
                if t_first_token is None:
                    t_first_token = time.monotonic()
                full_text += item
                await streamer.feed(item)
            else:
                final_report = item
        await streamer.done()
    except (AgentBError, LLMError) as exc:
        logger.error("[ws/result] agent_b 流式失败 %.0fms: %s", (time.monotonic() - t0) * 1000, exc)
        _release_claim(db, assessment_id)
        await _send(websocket, {"type": "error", "code": 502, "message": "报告生成失败，请重试"})
        return

    if final_report is None:
        _release_claim(db, assessment_id)
        await _send(websocket, {"type": "error", "code": 502, "message": "报告生成失败"})
        return

    report_text = final_report.get("report_text", full_text.strip())

    rec = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if rec:
        rec.report_json = json.dumps({"raw_llm_output": report_text}, ensure_ascii=False)
        rec.personality_type = ptype
        rec.report_text = report_text
        rec.status = "complete"
        db.commit()

    ttft_ms  = int((t_first_token - t0) * 1000) if t_first_token else -1
    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[ws/result] agent_b 完成 type=%s chars=%d TTFT=%dms total=%dms",
        ptype, len(report_text), ttft_ms, total_ms,
    )

    await _send(websocket, {
        "type": "done",
        "personality_type": ptype,
        "report_json": {"raw_llm_output": report_text},
    })
