"""Couple report runner — 后台调度报告 Agent 并落库（对标 report_writer_runner）。"""
from __future__ import annotations

import asyncio
import json
import logging

from app.agents.couple_report_writer import CoupleReportWriterError, run as write_couple_report
from app.database import SessionLocal
from app.models.couple_session import CoupleSession
from app.services.couple_report_quality_gate import CoupleQualityGateError
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)


async def run_and_persist(session_id: str, briefing: dict, *, log_prefix: str = "couple/bg") -> None:
    db = SessionLocal()
    try:
        report = await write_couple_report(briefing, session_id=session_id)
        updated = (db.query(CoupleSession)
                   .filter(CoupleSession.session_id == session_id, CoupleSession.status == "generating")
                   .update({"report_json": json.dumps(report, ensure_ascii=False), "status": "complete"},
                           synchronize_session=False))
        db.commit()
        logger.info("[%s] 完成 session=%s cards=%d updated=%d", log_prefix, session_id[:8],
                    len(report.get("blindspot_cards", [])), updated)
    except (CoupleReportWriterError, CoupleQualityGateError, LLMError) as exc:
        logger.error("[%s] 报告失败 session=%s: %s", log_prefix, session_id[:8], exc)
        (db.query(CoupleSession)
           .filter(CoupleSession.session_id == session_id, CoupleSession.status == "generating")
           .update({"status": "analyzed"}, synchronize_session=False))
        db.commit()
    finally:
        db.close()


def schedule(session_id: str, briefing: dict, *, log_prefix: str = "couple/bg") -> asyncio.Task:
    return asyncio.create_task(run_and_persist(session_id, briefing, log_prefix=log_prefix))
