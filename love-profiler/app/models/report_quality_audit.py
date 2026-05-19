"""ReportQualityAudit — LLM-as-judge 报告质量审计（Phase D.2）。"""

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReportQualityAudit(Base):
    __tablename__ = "report_quality_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assessments.id"), nullable=False, index=True,
    )
    prompt_version:   Mapped[str | None]    = mapped_column(Text, nullable=True)
    report_version:   Mapped[int | None]    = mapped_column(SmallInteger, nullable=True)
    judge_model:      Mapped[str]           = mapped_column(Text, nullable=False)
    coherence_score:  Mapped[int]           = mapped_column(SmallInteger, nullable=False)
    readability_score:Mapped[int]           = mapped_column(SmallInteger, nullable=False)
    factual_score:    Mapped[int]           = mapped_column(SmallInteger, nullable=False)
    overall_score:    Mapped[int]           = mapped_column(SmallInteger, nullable=False, index=True)
    summary:          Mapped[str | None]    = mapped_column(Text, nullable=True)
    raw_output:       Mapped[str | None]    = mapped_column(Text, nullable=True)
    duration_ms:      Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens:    Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    completion_tokens:Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    created_at:       Mapped[datetime]      = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
