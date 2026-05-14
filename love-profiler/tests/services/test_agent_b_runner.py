"""Tests for app/services/agent_b_runner.py.

run_and_persist 用全局 SessionLocal 写库，跟 conftest 的 per-test
engine 是两个 DB。测试里把模块级 SessionLocal 替换为返回测试 db_session
的 wrapper，让落库可见。
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.agent_b import AgentBError
from app.models.assessment import Assessment
from app.services import agent_b_runner
from app.services.llm_client import LLMError


def _make_generating_assessment(db_session, *, user_id: int = 1,
                                 session_id: str = "runner-test",
                                 diagnosis_json: str | None = None):
    a = Assessment(
        user_id=user_id, session_id=session_id, status="generating",
        answers_json="[]",
        diagnosis_json=diagnosis_json or json.dumps({"type_code": "S-CL-H"}),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


class _NonClosingSession:
    """把 db_session 包一层：__call__ 返回自身、close() 是 no-op，
    避免 run_and_persist 调 db.close() 把测试 fixture session 关掉。"""
    def __init__(self, real):
        self._real = real

    def __call__(self):
        return self

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        pass


@pytest.fixture
def shared_session_local(db_session, monkeypatch):
    """让 agent_b_runner.SessionLocal() 返回测试 db_session。"""
    wrapper = _NonClosingSession(db_session)
    monkeypatch.setattr(agent_b_runner, "SessionLocal", wrapper)
    return db_session


# ─────────────────────────────────────────────────────────────────────────────
# run_and_persist 成功路径
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_and_persist_success_updates_status_and_text(shared_session_local):
    a = _make_generating_assessment(shared_session_local)
    fake_text = "稳重的航标这是 Agent B 写出来的报告"

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(return_value=fake_text)):
        await agent_b_runner.run_and_persist(
            a.id, a.session_id,
            diagnosis={"type_code": "S-CL-H"},
        )

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "complete"
    assert saved.report_text == fake_text
    assert saved.personality_type == "S-CL-H"
    # report_json 应该是 {"raw_llm_output": fake_text}
    rj = json.loads(saved.report_json)
    assert rj == {"raw_llm_output": fake_text}


@pytest.mark.asyncio
async def test_run_and_persist_skips_update_when_status_not_generating(shared_session_local):
    """已经 complete 的 assessment 不应被 runner 覆盖（条件更新保护）。"""
    a = _make_generating_assessment(shared_session_local, session_id="already-complete")
    # 提前改成 complete
    a.status = "complete"
    a.report_text = "原报告"
    a.personality_type = "X-X-X"
    shared_session_local.commit()

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(return_value="新报告，不应覆盖")):
        await agent_b_runner.run_and_persist(
            a.id, a.session_id,
            diagnosis={"type_code": "S-CL-H"},
        )

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    # 数据未被覆盖
    assert saved.report_text == "原报告"
    assert saved.personality_type == "X-X-X"
    assert saved.status == "complete"


# ─────────────────────────────────────────────────────────────────────────────
# run_and_persist 失败路径
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_and_persist_agent_b_error_resets_to_analyzed(shared_session_local):
    a = _make_generating_assessment(shared_session_local, session_id="ab-fail")

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(side_effect=AgentBError("simulated"))):
        await agent_b_runner.run_and_persist(
            a.id, a.session_id, diagnosis={"type_code": "S-CL-H"},
        )

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "analyzed"
    # 失败时不应写 report_*
    assert saved.report_text is None or saved.report_text == ""


@pytest.mark.asyncio
async def test_run_and_persist_llm_error_resets_to_analyzed(shared_session_local):
    a = _make_generating_assessment(shared_session_local, session_id="llm-fail")

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(side_effect=LLMError("upstream 500"))):
        await agent_b_runner.run_and_persist(
            a.id, a.session_id, diagnosis={"type_code": "S-CL-H"},
        )

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "analyzed"


@pytest.mark.asyncio
async def test_run_and_persist_failure_does_not_revert_non_generating(shared_session_local):
    """assessment 已 complete（被另一路径完成）时，本次失败不应回滚状态。"""
    a = _make_generating_assessment(shared_session_local, session_id="race-fail")
    a.status = "complete"
    a.report_text = "已完成"
    shared_session_local.commit()

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(side_effect=AgentBError("late failure"))):
        await agent_b_runner.run_and_persist(
            a.id, a.session_id, diagnosis={"type_code": "S-CL-H"},
        )

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "complete"  # 仍是 complete
    assert saved.report_text == "已完成"


# ─────────────────────────────────────────────────────────────────────────────
# schedule()
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_returns_task_and_runs_in_background(shared_session_local):
    a = _make_generating_assessment(shared_session_local, session_id="scheduled")

    with patch("app.services.agent_b_runner.agent_b_run",
               new=AsyncMock(return_value="后台任务产出")):
        task = agent_b_runner.schedule(
            a.id, a.session_id, diagnosis={"type_code": "S-CL-H"},
        )
        assert isinstance(task, asyncio.Task)
        await task  # 显式 await 让测试等到任务完成再断言

    shared_session_local.expire_all()
    saved = shared_session_local.query(Assessment).filter_by(id=a.id).first()
    assert saved.status == "complete"
    assert saved.report_text == "后台任务产出"
