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
from app.services.token_quota import add_usage as quota_add_usage

logger = logging.getLogger(__name__)


async def run_and_persist(
    assessment_id: int,
    session_id: str,
    diagnosis: dict,
    *,
    log_prefix: str = "agent_b/bg",
    user_id: int | None = None,
) -> None:
    """Run Agent B; persist on success, reset to 'analyzed' on failure for the next poll to retry.

    user_id 传入时，调用结束会把 token 用量累加到 user_token_quota（B.1）。
    """
    t0 = time.monotonic()
    db = SessionLocal()
    try:
        usage_sink: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        report_text = await agent_b_run(diagnosis, session_id=session_id, usage_sink=usage_sink)
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
        if user_id is not None:
            try:
                quota_add_usage(
                    db, user_id=user_id,
                    prompt_tokens=usage_sink["prompt_tokens"],
                    completion_tokens=usage_sink["completion_tokens"],
                )
            except Exception as exc:
                logger.warning("[%s] quota_add_usage 失败 user_id=%s: %s", log_prefix, user_id, exc)
        logger.info(
            "[%s] 完成 assessment_id=%s type=%s chars=%d tokens=%d+%d updated=%d %.0fms",
            log_prefix, assessment_id, personality_type,
            len(report_text),
            usage_sink["prompt_tokens"], usage_sink["completion_tokens"],
            updated, (time.monotonic() - t0) * 1000,
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
    user_id: int | None = None,
) -> asyncio.Task:
    """Fire-and-forget kickoff — returns the task so callers can await it in tests if needed."""
    return asyncio.create_task(
        run_and_persist(
            assessment_id, session_id, diagnosis,
            log_prefix=log_prefix, user_id=user_id,
        )
    )
