"""
WebSocket helper utilities — SectionStreamer, dim_chart, label builders.

从 ws_result.py 提取的纯计算/流式辅助函数，不含路由逻辑。
"""

import json
import logging
import re

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_SEC_RE = re.compile(r'--([A-Za-z]+)--')



async def send(ws: WebSocket, data: dict) -> None:
    await ws.send_text(json.dumps(data, ensure_ascii=False))


class SectionStreamer:
    """Detects --Section-- markers in streaming text and sends typed WS messages."""

    def __init__(self, ws, send_fn, on_section_complete=None):
        self._ws = ws
        self._send = send_fn
        self._buf = ""
        self._cur = None
        self._cur_text = ""
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


def _aware_score(d4: dict) -> float:
    declared = d4.get("declared", "")
    normalized = d4.get("normalized", {}) or {}
    if not declared or not normalized:
        return 0.5
    max_val = max(normalized.values()) if normalized.values() else 0.0
    if max_val <= 0:
        return 0.5
    return min(1.0, max(0.0, normalized.get(declared, 0.0) / max_val))


def _style_clarity_score(d5: dict) -> float:
    s1 = d5.get("s1_raw", 0) or 0
    s2 = d5.get("s2_raw", 0) or 0
    return min(1.0, (abs(s1) + abs(s2)) / 12.0)


def dim_chart(diagnosis: dict) -> dict:
    """Convert diagnosis dimensions to structured chart data (三件套 + 兼容旧字段)."""
    dims = diagnosis.get("dimensions", {})

    _names = {"D1": "依恋安全", "D2": "边界清晰", "D3": "冲突健康"}
    d123 = [
        {"key": k, "name": _names[k],
         "raw": dims.get(k, {}).get("raw", 0),
         "interp": dims.get(k, {}).get("interp", "mixed")}
        for k in ("D1", "D2", "D3")
    ]
    d4_norm = dims.get("D4", {}).get("normalized", {t: 0.0 for t in ("T1", "T2", "T3", "T4", "T5")})
    d5 = dims.get("D5", {})

    d1_raw = dims.get("D1", {}).get("raw", 0) or 0
    d2_raw = dims.get("D2", {}).get("raw", 0) or 0
    d3_raw = dims.get("D3", {}).get("raw", 0) or 0
    health_radar = [
        {"key": "D1", "name": "依恋安全", "value": min(1.0, max(0.0, (d1_raw + 12) / 24))},
        {"key": "D2", "name": "边界清晰", "value": min(1.0, max(0.0, (d2_raw + 12) / 24))},
        {"key": "D3", "name": "冲突健康", "value": min(1.0, max(0.0, (d3_raw + 12) / 24))},
        {"key": "AWARE", "name": "自我认知", "value": _aware_score(dims.get("D4", {}))},
        {"key": "STYLE", "name": "表达成熟", "value": _style_clarity_score(d5)},
    ]

    d4_block = dims.get("D4", {}) or {}
    top2 = d4_block.get("top2", []) or []
    d4_details = diagnosis.get("D4_details", []) or []
    name_by_code = {d.get("code", ""): d.get("name", "") for d in d4_details}
    d4_preference = {
        "items": [
            {"code": code,
             "name": name_by_code.get(code, code),
             "value": float(d4_norm.get(code, 0.0) or 0.0), "is_top2": code in top2}
            for code in ("T1", "T2", "T3", "T4", "T5")
        ],
        "top2_names": [name_by_code.get(c, c) for c in top2],
    }

    d5_quadrant = {
        "s1_raw": d5.get("s1_raw", 0) or 0, "s2_raw": d5.get("s2_raw", 0) or 0,
        "s1_label": d5.get("s1", "中直接"), "s2_label": d5.get("s2", "中分享"),
        "quadrant": d5.get("quadrant", ""),
        "style_name": diagnosis.get("D5_style_name", "") or "",
    }

    return {
        "d123": d123, "d4": d4_norm,
        "d5": {"s1": d5.get("s1", "中直接"), "s2": d5.get("s2", "中分享"),
               "s1_raw": d5.get("s1_raw", 0), "s2_raw": d5.get("s2_raw", 0)},
        "health_radar": health_radar, "d4_preference": d4_preference,
        "d5_quadrant": d5_quadrant,
    }


def all_labels(diagnosis: dict) -> list:
    """组合 D1-D5 全部维度的人格卡展示标签。"""
    labels = list(diagnosis.get("segment_decode", []))
    for item in diagnosis.get("D4_details", []):
        labels.append({"dimension": "D4", "code": item.get("code", ""),
                       "label_cn": item.get("name", ""), "is_neutral": True})
    d5_style = diagnosis.get("D5_style_name", "")
    d5_quadrant = (diagnosis.get("dimensions", {}) or {}).get("D5", {}).get("quadrant", "")
    if d5_style or d5_quadrant:
        labels.append({"dimension": "D5", "code": d5_quadrant,
                       "label_cn": d5_style or d5_quadrant, "is_neutral": True})
    return labels


def highlights_meta(diagnosis: dict) -> list:
    """从诊断结果提取 highlights 标题与正负向。"""
    return [
        {"idx": i + 1, "title": h.get("name_cn", ""), "is_positive": h.get("is_positive", False)}
        for i, h in enumerate(diagnosis.get("highlights", []))
    ]
