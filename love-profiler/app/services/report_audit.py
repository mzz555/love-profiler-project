"""LLM-as-judge 报告质量审计（Phase D.2）。

主流程：
1. 报告写库 status=complete 后由调用方触发 schedule_audit；
2. 后台 task 读取 diagnosis_json + report_text，构造 user message；
3. 调 chat_completion（judge_model 与 the report writer 同款豆包，可由 JUDGE_MODEL 覆盖）；
4. 解析 JSON 输出 → 写入 report_quality_audit 表；
5. 任何环节失败仅记日志，不重试也不阻塞主流程。

环境变量：
- JUDGE_ENABLED：true 时启用审计；缺省 false（避免增加成本）
- JUDGE_MODEL：覆盖 DOUBAO_MODEL，可指向更便宜的小模型
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import time
from typing import Any

from app.config import settings
from app.database import SessionLocal
from app.models.assessment import Assessment
from app.models.report_quality_audit import ReportQualityAudit
from app.services.llm_client import LLMError, chat_completion

logger = logging.getLogger(__name__)

_PROMPT_FILE = pathlib.Path(__file__).parents[2] / "docs" / "judge-system-prompt.md"
_PROMPT_RAW = _PROMPT_FILE.read_text(encoding="utf-8")
JUDGE_SYSTEM_PROMPT = _PROMPT_RAW.rstrip()


def _parse_judge_prompt_version(raw: str) -> str:
    m = re.search(r"<!--\s*judge-prompt-version:\s*([\w.\-]+)\s*-->", raw)
    return m.group(1) if m else "0"


JUDGE_PROMPT_VERSION: str = _parse_judge_prompt_version(_PROMPT_RAW)


# Keep a strong reference to fire-and-forget audit tasks until they complete.
_pending_audit_tasks: set[asyncio.Task] = set()


def is_enabled() -> bool:
    return settings.judge_enabled


def _judge_model() -> str:
    return settings.judge_model or settings.doubao_model


def build_judge_user_message(diagnosis: dict, report_text: str) -> str:
    """把 diagnosis + 报告全文拼成 judge 的 user message。"""
    diag_json = json.dumps(diagnosis, ensure_ascii=False, indent=2)
    return (
        "# 诊断数据\n"
        f"```json\n{diag_json}\n```\n\n"
        "# 报告全文\n"
        f"{report_text}\n"
    )


def _parse_judge_output(raw: str) -> dict[str, Any]:
    """从 judge 输出中抽 JSON。

    宽松：先尝试整体 json.loads，失败则用正则抓最外层 {...} 再 loads。
    四个 score 字段强制 clamp 到 1-10 整数；summary 截断 200 字符。
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        # 去 markdown 代码围栏
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"judge output is not JSON: {text[:200]!r}")
        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise ValueError(f"judge output is not a JSON object: {type(data).__name__}")

    return {
        "coherence_score":   _clamp_score(data.get("coherence_score")),
        "readability_score": _clamp_score(data.get("readability_score")),
        "factual_score":     _clamp_score(data.get("factual_score")),
        "overall_score":     _clamp_score(data.get("overall_score")),
        "summary":           _truncate(str(data.get("summary") or ""), 200),
    }


def _clamp_score(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"score is not an integer: {v!r}") from None
    return max(1, min(10, n))


def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[:max_len].rstrip() + "…"


async def audit_assessment(
    assessment_id: int,
    *,
    session_id: str | None = None,
) -> ReportQualityAudit | None:
    """对一份已完成的 assessment 执行一次审计；返回写入的审计行（失败返回 None）。

    自带 DB session（与 report_writer_runner 同模式），方便从 background task 调用。
    JUDGE_ENABLED=false 时直接跳过返回 None。
    """
    if not is_enabled():
        return None

    t0 = time.monotonic()
    db = SessionLocal()
    try:
        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if assessment is None:
            logger.warning("[judge] assessment_id=%s 不存在，跳过审计", assessment_id)
            return None
        if not assessment.diagnosis_json or not assessment.report_text:
            logger.warning(
                "[judge] assessment_id=%s diagnosis/report_text 缺失，跳过审计",
                assessment_id,
            )
            return None

        try:
            diagnosis = json.loads(assessment.diagnosis_json)
        except json.JSONDecodeError as exc:
            logger.error("[judge] assessment_id=%s diagnosis_json 解析失败：%s",
                         assessment_id, exc)
            return None

        user_msg = build_judge_user_message(diagnosis, assessment.report_text)
        usage_sink: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

        try:
            raw = await chat_completion(
                system_prompt=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.0,  # 评分要求一致性，温度压到 0
                agent="judge",
                session_id=session_id,
                user_id=assessment.user_id,
                usage_sink=usage_sink,
            )
        except LLMError as exc:
            logger.error("[judge] assessment_id=%s LLM 调用失败：%s", assessment_id, exc)
            return None

        try:
            parsed = _parse_judge_output(raw)
        except ValueError as exc:
            logger.error(
                "[judge] assessment_id=%s 输出解析失败：%s\nraw: %s",
                assessment_id, exc, raw[:500],
            )
            return None

        duration_ms = int((time.monotonic() - t0) * 1000)
        audit = ReportQualityAudit(
            assessment_id=assessment_id,
            prompt_version=assessment.prompt_version,
            report_version=assessment.report_version,
            judge_model=_judge_model(),
            coherence_score=parsed["coherence_score"],
            readability_score=parsed["readability_score"],
            factual_score=parsed["factual_score"],
            overall_score=parsed["overall_score"],
            summary=parsed["summary"],
            raw_output=raw[:8000],
            duration_ms=duration_ms,
            prompt_tokens=usage_sink["prompt_tokens"],
            completion_tokens=usage_sink["completion_tokens"],
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        logger.info(
            "[judge] assessment_id=%s 审计完成 overall=%d coherence=%d readability=%d factual=%d "
            "tokens=%d+%d %.0fms",
            assessment_id,
            parsed["overall_score"], parsed["coherence_score"],
            parsed["readability_score"], parsed["factual_score"],
            usage_sink["prompt_tokens"], usage_sink["completion_tokens"],
            duration_ms,
        )
        return audit
    finally:
        db.close()


def schedule_audit(assessment_id: int, *, session_id: str | None = None) -> asyncio.Task | None:
    """fire-and-forget 触发一次审计。JUDGE_ENABLED=false 时返回 None。"""
    if not is_enabled():
        return None
    task = asyncio.create_task(audit_assessment(assessment_id, session_id=session_id))
    _pending_audit_tasks.add(task)
    task.add_done_callback(_pending_audit_tasks.discard)
    return task
