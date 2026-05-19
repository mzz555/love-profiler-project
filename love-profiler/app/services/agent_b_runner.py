"""Background runner for Agent B — shared by /quiz/submit and /result polling."""

import asyncio
import json
import logging
import time

from app.agents.agent_b import (
    AgentBError,
    PROMPT_VERSION,
    REPORT_VERSION,
    run as agent_b_run,
)
from app.database import SessionLocal
from app.models.assessment import Assessment
from app.services.llm_client import LLMError

logger = logging.getLogger(__name__)


async def run_and_persist(
    assessment_id: int,
    session_id: str,
    diagnosis: dict,
    *,
    log_prefix: str = "agent_b/bg",
) -> None:
    """Run Agent B; persist on success, reset to 'analyzed' on failure for the next poll to retry."""
    t0 = time.monotonic()
    db = SessionLocal()
    try:
        report_text = await agent_b_run(diagnosis, session_id=session_id)
        personality_type = diagnosis.get("type_code", "")

        # Conditional update — single statement avoids the read-then-write race when
        # multiple endpoints could kick off Agent B for the same assessment.
        updated = (
            db.query(Assessment)
            .filter(Assessment.id == assessment_id, Assessment.status == "generating")
            .update(
                {
                    "report_json": json.dumps(
                        {"raw_llm_output": report_text}, ensure_ascii=False
                    ),
                    "personality_type": personality_type,
                    "report_text": report_text,
                    "status": "complete",
                    "prompt_version": PROMPT_VERSION,
                    "report_version": REPORT_VERSION,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        logger.info(
            "[%s] 完成 assessment_id=%s type=%s chars=%d updated=%d %.0fms",
            log_prefix, assessment_id, personality_type,
            len(report_text), updated, (time.monotonic() - t0) * 1000,
        )
    except (AgentBError, LLMError) as exc:
        logger.error(
            "[%s] agent_b 失败 assessment_id=%s %.0fms: %s",
            log_prefix, assessment_id, (time.monotonic() - t0) * 1000, exc,
        )
        db.query(Assessment).filter(
            Assessment.id == assessment_id, Assessment.status == "generating",
        ).update({"status": "analyzed"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def schedule(
    assessment_id: int,
    session_id: str,
    diagnosis: dict,
    *,
    log_prefix: str = "agent_b/bg",
) -> asyncio.Task:
    """Fire-and-forget kickoff — returns the task so callers can await it in tests if needed."""
    return asyncio.create_task(
        run_and_persist(assessment_id, session_id, diagnosis, log_prefix=log_prefix)
    )
