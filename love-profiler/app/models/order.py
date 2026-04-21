"""
Order model — tracks payment orders for assessment unlocks.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    # Merchant-generated unique trade number (idempotency key)
    out_trade_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Amount in fen (¥9.9 → 990)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # status: "pending" | "paid" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
