"""Tests for app/api/ws_result.py.

三大块：
1. _SectionStreamer 状态机（无 WS 依赖，纯逻辑）
2. helper 纯函数（_dim_chart / _all_labels / _highlights_meta）
3. WS endpoint 集成（JWT 校验 / 状态分流 / Agent B 流式）
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.api.ws_result import (
    _SectionStreamer,
    _all_labels,
    _dim_chart,
    _highlights_meta,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _SectionStreamer
# ─────────────────────────────────────────────────────────────────────────────

class _FakeWS:
    """占位对象——_SectionStreamer 只把它原样传给 send_fn，不调用其方法。"""


def _make_streamer():
    """返回 (streamer, send_mock)；send_mock 是 AsyncMock，按顺序收集所有调用。"""
    ws = _FakeWS()
    send = AsyncMock()
    return _SectionStreamer(ws, send), send


def _payloads(send_mock):
    """提取 send_mock 全部调用的 data 参数（第 2 个位置参数）。"""
    return [call.args[1] for call in send_mock.call_args_list]


@pytest.mark.asyncio
async def test_streamer_single_section_emits_start_and_chunks():
    streamer, send = _make_streamer()
    # 一段进入 Title 然后再灌入更长的文本（>20 字符的 lookback 安全区）
    await streamer.feed("--Title--稳重的航标，这是一段足够长的标题描述用于触发 chunk 输出")
    await streamer.done()

    msgs = _payloads(send)
    # 必有：section_start + 至少一个 section_chunk + section_end
    types = [m["type"] for m in msgs]
    assert "section_start" in types
    assert "section_chunk" in types
    assert types[-1] == "section_end"
    assert all(m.get("section") == "Title" for m in msgs)


@pytest.mark.asyncio
async def test_streamer_switches_between_sections():
    streamer, send = _make_streamer()
    await streamer.feed("--Title--稳重的航标用于触发足够长的 chunk 缓冲输出")
    await streamer.feed("--Opening--你是一个稳重的人，遇到危机时不慌张这是 opening")
    await streamer.done()

    msgs = _payloads(send)
    types_with_section = [(m["type"], m.get("section")) for m in msgs]
    # 检查切换顺序：Title 的 end 必须在 Opening 的 start 之前
    title_end_idx   = types_with_section.index(("section_end",   "Title"))
    opening_start   = types_with_section.index(("section_start", "Opening"))
    assert title_end_idx < opening_start


@pytest.mark.asyncio
async def test_streamer_text_before_any_marker_is_dropped():
    """Marker 出现前的文本不属于任何 section，应被丢弃（不会发 section_chunk）。"""
    streamer, send = _make_streamer()
    await streamer.feed("乱码前置内容--Title--标题")
    await streamer.done()

    msgs = _payloads(send)
    # 不应有 section==None 的 chunk
    chunks = [m for m in msgs if m["type"] == "section_chunk"]
    assert all(m["section"] == "Title" for m in chunks)


@pytest.mark.asyncio
async def test_streamer_handles_marker_split_across_chunks():
    """边界：marker 被拆到两个 feed 调用中间，状态机必须能在 buffer 里拼接出来。"""
    streamer, send = _make_streamer()
    await streamer.feed("--Tit")
    await streamer.feed("le--稳重")  # 此时累积 buffer 里 marker 才完整
    await streamer.feed("的航标内容这里足够长可以触发 chunk 缓冲安全区机制")
    await streamer.done()

    msgs = _payloads(send)
    types = [m["type"] for m in msgs]
    # 即使 marker 被切开，section_start 仍应出现
    assert ("section_start" in types)
    starts = [m for m in msgs if m["type"] == "section_start"]
    assert starts[0]["section"] == "Title"


@pytest.mark.asyncio
async def test_streamer_done_flushes_remaining_buffer():
    """流式结束时 buffer 里可能还有 <20 字符的尾部，done() 必须冲刷。"""
    streamer, send = _make_streamer()
    await streamer.feed("--Title--短尾巴")  # 不到 20 字符
    await streamer.done()

    msgs = _payloads(send)
    chunks = [m for m in msgs if m["type"] == "section_chunk"]
    end_msgs = [m for m in msgs if m["type"] == "section_end"]
    # done() 后必须把 "短尾巴" 冲出去并发 section_end
    assert any("短尾巴" in m["text"] for m in chunks)
    assert end_msgs and end_msgs[-1]["section"] == "Title"


@pytest.mark.asyncio
async def test_streamer_done_resets_state():
    """done() 后内部 buffer / current section 应清空，可以复用同一个 streamer。"""
    streamer, send = _make_streamer()
    await streamer.feed("--A--xxxxxxxxxxxxxxxxxxxxxxxx")
    await streamer.done()
    send.reset_mock()

    # 再喂新 marker，不该回到旧 section A
    await streamer.feed("--B--yyyyyyyyyyyyyyyyyyyyyyyy")
    await streamer.done()

    msgs = _payloads(send)
    sections = {m.get("section") for m in msgs}
    assert sections == {"B"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. helper 纯函数
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLE_DIAGNOSIS = {
    "type_code": "S-CL-H",
    "type_name": "稳重的航标",
    "type_tagline": "副标题",
    "dimensions": {
        "D1": {"raw": 9,  "interp": "secure"},
        "D2": {"raw": 6,  "interp": "clear"},
        "D3": {"raw": -3, "interp": "moderate_problematic"},
        "D4": {"top2": ["T1", "T2"],
               "normalized": {"T1": 0.9, "T2": 0.8, "T3": 0.5, "T4": 0.4, "T5": 0.3}},
        "D5": {"quadrant": "高直接×高分享", "s1": "高直接", "s2": "高分享",
               "s1_raw": 5, "s2_raw": 4},
    },
    "segment_decode": [
        {"dimension": "D1", "code": "S",  "label_cn": "安全型依恋", "is_healthy": True},
        {"dimension": "D2", "code": "CL", "label_cn": "清晰边界",   "is_healthy": True},
    ],
    "D4_details": [
        {"code": "T1", "name": "言语肯定", "detail": "x"},
        {"code": "T2", "name": "精心时刻", "detail": "y"},
    ],
    "D5_style_name": "直爽热情型",
    "highlights": [
        {"name_cn": "压力崩塌", "severity": "moderate", "is_positive": False},
        {"name_cn": "稳定锚",   "severity": "info",     "is_positive": True},
    ],
}


def test_dim_chart_returns_full_structure():
    chart = _dim_chart(_SAMPLE_DIAGNOSIS)
    assert {row["key"] for row in chart["d123"]} == {"D1", "D2", "D3"}
    # D1 raw=9 interp=secure 必须原样回传
    d1 = next(r for r in chart["d123"] if r["key"] == "D1")
    assert d1["raw"] == 9 and d1["interp"] == "secure"
    # D4 5 类归一化齐
    assert set(chart["d4"].keys()) == {"T1", "T2", "T3", "T4", "T5"}
    # D5 子段
    assert chart["d5"]["s1"] == "高直接"
    assert chart["d5"]["s2_raw"] == 4


def test_dim_chart_empty_diagnosis_fills_defaults():
    chart = _dim_chart({})
    # D1-D3 默认 raw=0 interp=mixed
    for row in chart["d123"]:
        assert row["raw"] == 0 and row["interp"] == "mixed"
    # D4 5 类全 0.0
    assert chart["d4"] == {"T1": 0.0, "T2": 0.0, "T3": 0.0, "T4": 0.0, "T5": 0.0}
    # D5 默认中段
    assert chart["d5"]["s1"] == "中直接"
    assert chart["d5"]["s2"] == "中分享"


def test_all_labels_includes_segment_decode_and_d4_d5():
    labels = _all_labels(_SAMPLE_DIAGNOSIS)
    by_dim = {l["dimension"]: l for l in labels}
    # segment_decode 原样保留
    assert by_dim["D1"]["label_cn"] == "安全型依恋"
    assert by_dim["D2"]["label_cn"] == "清晰边界"
    # D4 顶部爱语标签：top2 各一枚（多枚同 dimension）
    d4_labels = [l for l in labels if l["dimension"] == "D4"]
    assert {l["code"] for l in d4_labels} == {"T1", "T2"}
    assert all(l.get("is_neutral") for l in d4_labels)
    # D5 一枚 quadrant 标签
    d5 = by_dim["D5"]
    assert d5["label_cn"] == "直爽热情型"
    assert d5["is_neutral"] is True


def test_all_labels_omits_d5_when_no_quadrant_and_no_style():
    diag = {"segment_decode": []}
    labels = _all_labels(diag)
    assert labels == []


def test_highlights_meta_indexes_from_1():
    meta = _highlights_meta(_SAMPLE_DIAGNOSIS)
    assert len(meta) == 2
    assert meta[0]["idx"] == 1 and meta[0]["title"] == "压力崩塌"
    assert meta[1]["idx"] == 2 and meta[1]["is_positive"] is True


def test_highlights_meta_empty_returns_empty():
    assert _highlights_meta({}) == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. WS endpoint 集成测
# ─────────────────────────────────────────────────────────────────────────────

from fastapi.websockets import WebSocketDisconnect


def _make_assessment(db_session, user_id: int, status: str = "analyzed", *,
                    session_id: str = "ws-test-session",
                    diagnosis: dict | None = None,
                    report_text: str | None = None,
                    report_json: dict | None = None,
                    personality_type: str = "S-CL-H"):
    from app.models.assessment import Assessment

    diag = diagnosis if diagnosis is not None else {
        "type_code": "S-CL-H", "type_name": "稳重的航标", "type_tagline": "",
        "dimensions": {}, "highlights": [],
    }
    a = Assessment(
        user_id=user_id,
        session_id=session_id,
        status=status,
        answers_json="[]",
        diagnosis_json=json.dumps(diag, ensure_ascii=False),
        report_json=json.dumps(report_json, ensure_ascii=False) if report_json else None,
        report_text=report_text,
        personality_type=personality_type,
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _make_paid_order(db_session, user_id: int, assessment_id: int):
    """构造一个 paid order，让 access_control.is_unlocked() 返回 True。"""
    from app.models.order import Order

    o = Order(
        user_id=user_id,
        assessment_id=assessment_id,
        out_trade_no=f"unlock-{assessment_id}",
        amount=0,
        status="paid",
    )
    db_session.add(o)
    db_session.commit()


def _auth_token(user_id: int) -> str:
    from app.middleware.auth import create_access_token
    return create_access_token(user_id)


def test_ws_rejects_invalid_token(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/result?token=invalid") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4001


def test_ws_returns_error_when_session_not_found(client, user_id):
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "nonexistent"}))
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "error"
    assert msg["code"] == 404


def test_ws_returns_error_when_assessment_pending(client, db_session, user_id):
    _make_assessment(db_session, user_id, status="pending")
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "ws-test-session"}))
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "error" and msg["code"] == 400


def test_ws_returns_error_when_not_unlocked(client, db_session, user_id, monkeypatch):
    # 本地 .env 可能开了 DEV_MODE，access_control.is_unlocked 会直接放行；
    # 测试解锁逻辑必须显式关掉 DEV_MODE。
    monkeypatch.setenv("DEV_MODE", "false")
    _make_assessment(db_session, user_id, status="analyzed")
    # 不创建 paid order → is_unlocked 返回 False
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "ws-test-session"}))
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "error" and msg["code"] == 402


def test_ws_returns_error_when_generating_status(client, db_session, user_id):
    a = _make_assessment(db_session, user_id, status="generating")
    _make_paid_order(db_session, user_id, a.id)
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "ws-test-session"}))
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "error" and msg["code"] == 409


def test_ws_cached_path_replays_report_text(client, db_session, user_id):
    """status=complete + report_text 命中缓存重放路径。"""
    report = "--Title--稳重的航标用于触发缓冲--Opening--开篇画像放在这里的文本足够长"
    a = _make_assessment(
        db_session, user_id, status="complete",
        report_text=report,
        report_json={"raw_llm_output": report},
    )
    _make_paid_order(db_session, user_id, a.id)
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "ws-test-session"}))
        msgs = []
        while True:
            data = json.loads(ws.receive_text())
            msgs.append(data)
            if data["type"] == "done":
                break

    types = [m["type"] for m in msgs]
    assert types[0] == "meta"
    assert "section_start" in types  # 带 --Title-- 标记走 section 流
    assert types[-1] == "done"


def test_ws_cached_legacy_format_uses_portrait_chunk(client, db_session, user_id):
    """report_text 无 --Title-- 标记 → 走 portrait_chunk 兜底。"""
    a = _make_assessment(
        db_session, user_id, status="complete",
        report_text="一段没有标记的旧格式报告文字" * 5,
        report_json={"raw_llm_output": "legacy"},
    )
    _make_paid_order(db_session, user_id, a.id)
    token = _auth_token(user_id)
    with client.websocket_connect(f"/ws/result?token={token}") as ws:
        ws.send_text(json.dumps({"session_id": "ws-test-session"}))
        msgs = []
        while True:
            data = json.loads(ws.receive_text())
            msgs.append(data)
            if data["type"] == "done":
                break

    types = [m["type"] for m in msgs]
    assert "portrait_chunk" in types
    assert "section_start" not in types
    assert types[-1] == "done"


def test_ws_returns_429_when_quota_exceeded(client, db_session, user_id, monkeypatch):
    """B.1：当日 token quota 已用满 → 429 + 不进 Agent B 流。"""
    from datetime import date
    from app.models.user_token_quota import UserTokenQuota

    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "100")

    a = _make_assessment(db_session, user_id, status="analyzed")
    _make_paid_order(db_session, user_id, a.id)
    db_session.add(UserTokenQuota(
        user_id=user_id, usage_date=date.today(),
        prompt_tokens=70, completion_tokens=50, total_tokens=120,
    ))
    db_session.commit()

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream") as mock_stream:
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            msg = json.loads(ws.receive_text())
    assert msg["type"] == "error"
    assert msg["code"] == 429
    assert "今日测评次数已达上限" in msg["message"]
    # 不应该启动 Agent B
    mock_stream.assert_not_called()


def test_ws_analyzed_writes_token_quota_after_success(client, db_session, user_id, monkeypatch):
    """B.1：成功跑完 Agent B 后，token 用量应落到 user_token_quota。"""
    from datetime import date
    from app.models.user_token_quota import UserTokenQuota

    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("USER_DAILY_TOKEN_QUOTA", "100000")

    a = _make_assessment(
        db_session, user_id, status="analyzed",
        diagnosis={
            "type_code": "S-CL-H", "type_name": "稳重的航标",
            "type_tagline": "副", "dimensions": {}, "highlights": [],
        },
    )
    _make_paid_order(db_session, user_id, a.id)

    async def fake_run_stream(diagnosis, session_id=None):
        for piece in ("--Title--", "稳重的航标"):
            yield piece
        yield {
            "report_text": "--Title--稳重的航标",
            "quality_warnings": [],
            "prompt_tokens": 850,
            "completion_tokens": 420,
        }

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            while True:
                data = json.loads(ws.receive_text())
                if data["type"] == "done":
                    break

    db_session.expire_all()
    quota = (
        db_session.query(UserTokenQuota)
        .filter_by(user_id=user_id, usage_date=date.today())
        .one()
    )
    assert quota.prompt_tokens == 850
    assert quota.completion_tokens == 420
    assert quota.total_tokens == 1270


def test_ws_analyzed_runs_agent_b_and_writes_complete(client, db_session, user_id):
    """status=analyzed → 跑 Agent B 流式 → 写库 status=complete。"""
    a = _make_assessment(
        db_session, user_id, status="analyzed",
        diagnosis={
            "type_code": "S-CL-H", "type_name": "稳重的航标",
            "type_tagline": "副", "dimensions": {}, "highlights": [],
        },
    )
    _make_paid_order(db_session, user_id, a.id)

    # mock Agent B 流：先 yield 几段文本，最后 yield {"report_text": ...}
    async def fake_run_stream(diagnosis, session_id=None):
        for piece in ("--Title--", "稳重的航标这里需要够长", "--Opening--", "开篇画像也需要够长"):
            yield piece
        yield {"report_text": "--Title--稳重的航标--Opening--开篇画像"}

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            msgs = []
            while True:
                data = json.loads(ws.receive_text())
                msgs.append(data)
                if data["type"] == "done":
                    break

    types = [m["type"] for m in msgs]
    assert types[0] == "meta"
    assert "section_start" in types
    assert types[-1] == "done"

    # 验证落库
    from app.models.assessment import Assessment
    db_session.expire_all()
    saved = db_session.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "complete"
    assert saved.report_text and "稳重的航标" in saved.report_text


def test_ws_analyzed_agent_b_failure_releases_claim(client, db_session, user_id):
    """Agent B 抛 AgentBError → 发 502 + status 回滚到 analyzed。"""
    from app.agents.report_writer import ReportWriterError as AgentBError  # keep local alias for minimal test diff

    a = _make_assessment(db_session, user_id, status="analyzed")
    _make_paid_order(db_session, user_id, a.id)

    async def fake_run_stream(diagnosis, session_id=None):
        yield "--Title--"
        raise AgentBError("simulated failure")

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            msgs = []
            while True:
                data = json.loads(ws.receive_text())
                msgs.append(data)
                if data["type"] in ("error", "done"):
                    break

    err = [m for m in msgs if m["type"] == "error"]
    assert err and err[0]["code"] == 502

    # status 应回滚到 analyzed，允许重试
    from app.models.assessment import Assessment
    db_session.expire_all()
    saved = db_session.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "analyzed"


# ── Phase C.1 · Section 级断点续传 ────────────────────────────────

def test_ws_failure_preserves_partial_sections_for_resume(client, db_session, user_id):
    """Agent B 写到 Opening 段抛错 → partial_sections 应保留 Title。"""
    from app.agents.report_writer import ReportWriterError as AgentBError  # keep local alias for minimal test diff
    from app.models.assessment import Assessment

    a = _make_assessment(db_session, user_id, status="analyzed")
    _make_paid_order(db_session, user_id, a.id)

    async def fake_run_stream(diagnosis, session_id=None):
        # 完成 Title 段后崩；section_end 触发持久化
        yield "--Title--《稳》"
        yield "--Opening--"  # 进入 Opening，触发 Title 的 section_end
        raise AgentBError("crash mid-stream")

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            while True:
                data = json.loads(ws.receive_text())
                if data["type"] in ("error", "done"):
                    break

    db_session.expire_all()
    saved = db_session.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "analyzed"
    assert saved.partial_sections, "partial_sections 应保留供下次接续"
    partial = json.loads(saved.partial_sections)
    assert "Title" in partial
    assert "《稳》" in partial["Title"]


def test_ws_success_clears_partial_sections(client, db_session, user_id):
    """报告成功完成后，partial_sections 应清空。"""
    from app.models.assessment import Assessment

    a = _make_assessment(
        db_session, user_id, status="analyzed",
        diagnosis={
            "type_code": "S-CL-H", "type_name": "稳",
            "type_tagline": "", "dimensions": {}, "highlights": [],
        },
    )
    # 预置一份残留 partial（模拟上次中断遗留）
    a.partial_sections = json.dumps({"Title": "残留"})
    db_session.commit()
    _make_paid_order(db_session, user_id, a.id)

    async def fake_run_stream(diagnosis, **kwargs):
        # 假装 LLM 写完了完整报告
        for piece in ("--Title--", "《稳》", "--Opening--", "开篇"):
            yield piece
        yield {
            "report_text": "--Title--《稳》--Opening--开篇",
            "quality_warnings": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            while True:
                data = json.loads(ws.receive_text())
                if data["type"] == "done":
                    break

    db_session.expire_all()
    saved = db_session.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "complete"
    assert saved.partial_sections in (None, "", "{}"), "完成后应清空 partial_sections"


def test_ws_reconnect_replays_and_resumes(client, db_session, user_id):
    """重连：partial_sections 非空 → 给前端 replay 已完成段 + run_stream 收到 resumed_sections。"""
    from app.models.assessment import Assessment

    a = _make_assessment(
        db_session, user_id, status="analyzed",
        diagnosis={
            "type_code": "S-CL-H", "type_name": "稳",
            "type_tagline": "", "dimensions": {}, "highlights": [],
        },
    )
    # 模拟上次中断遗留：完成 Title + Opening
    a.partial_sections = json.dumps({
        "Title":   "《稳重的航标》",
        "Opening": "你的稳不需要被看见，遇事先解决再处理情绪。",
    })
    db_session.commit()
    _make_paid_order(db_session, user_id, a.id)

    captured = {}

    async def fake_run_stream(diagnosis, session_id=None, resumed_sections=None):
        captured["resumed_sections"] = resumed_sections
        for piece in ("--Attachment--", "稳稳在场"):
            yield piece
        yield {
            "report_text": "--Title--《稳重的航标》--Opening--…--Attachment--稳稳在场",
            "quality_warnings": [],
            "prompt_tokens": 200,
            "completion_tokens": 30,
        }

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            msgs = []
            while True:
                data = json.loads(ws.receive_text())
                msgs.append(data)
                if data["type"] == "done":
                    break

    # meta 消息应带 resumed_sections
    meta = next(m for m in msgs if m["type"] == "meta")
    assert sorted(meta.get("resumed_sections", [])) == ["Opening", "Title"]

    # run_stream 必须收到 resumed_sections
    assert captured["resumed_sections"] is not None
    assert "Title" in captured["resumed_sections"]
    assert "Opening" in captured["resumed_sections"]

    # 前端应先看到 Title/Opening 的 replay（在 LLM 新输出前）
    section_starts = [m for m in msgs if m["type"] == "section_start"]
    section_names = [m["section"] for m in section_starts]
    assert section_names.index("Title") < section_names.index("Attachment")


def test_ws_resume_disabled_by_env(client, db_session, user_id, monkeypatch):
    """RESUME_ENABLED=false 时即便有 partial_sections 也不接续，行为退回到全量重写。"""
    monkeypatch.setenv("RESUME_ENABLED", "false")

    a = _make_assessment(
        db_session, user_id, status="analyzed",
        diagnosis={
            "type_code": "S-CL-H", "type_name": "稳",
            "type_tagline": "", "dimensions": {}, "highlights": [],
        },
    )
    a.partial_sections = json.dumps({"Title": "上次残留"})
    db_session.commit()
    _make_paid_order(db_session, user_id, a.id)

    captured = {}

    async def fake_run_stream(diagnosis, **kwargs):
        captured["resumed_sections"] = kwargs.get("resumed_sections")
        for piece in ("--Title--", "全量"):
            yield piece
        yield {
            "report_text": "--Title--全量",
            "quality_warnings": [],
            "prompt_tokens": 50,
            "completion_tokens": 20,
        }

    token = _auth_token(user_id)
    with patch("app.api.ws_result.report_stream", side_effect=fake_run_stream):
        with client.websocket_connect(f"/ws/result?token={token}") as ws:
            ws.send_text(json.dumps({"session_id": "ws-test-session"}))
            while True:
                data = json.loads(ws.receive_text())
                if data["type"] == "done":
                    break

    assert captured["resumed_sections"] is None, "禁用接续后不应传 resumed_sections"
