"""
AiCallLog — one row per LLM API call.
Covers both success and error cases for all agents.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiCallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # When & who
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    agent: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Model config
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    retry_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Outcome
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # success | error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Payload (system_prompt is fixed per agent, store length only to avoid huge rows)
    system_prompt_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_preview: Mapped[str | None] = mapped_column(Text, nullable=True)  # first 2000 chars
    response_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Performance
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
