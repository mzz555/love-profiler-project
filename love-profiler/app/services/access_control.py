"""Payment / unlock gating shared by /result, /result/stream and /ws/result."""

import os

from sqlalchemy.orm import Session

from app.models.order import Order


def is_unlocked(db: Session, assessment_id: int, user_id: int) -> bool:
    """Return True iff the assessment is unlocked for this user.

    DEV_MODE=true bypasses the check entirely; otherwise a paid Order is required.
    """
    if os.environ.get("DEV_MODE", "").lower() == "true":
        return True
    return (
        db.query(Order)
        .filter(
            Order.assessment_id == assessment_id,
            Order.user_id == user_id,
            Order.status == "paid",
        )
        .first()
        is not None
    )
