"""CoupleSession — 一对情侣一次双人测评（异步配对 + 契约 + 报告）。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CoupleSession(Base):
    __tablename__ = "couple_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    pairing_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    initiator_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    partner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    a_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    b_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    a_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    b_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    briefing_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting_partner")
    question_set_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
