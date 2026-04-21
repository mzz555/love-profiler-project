"""
Integration tests for SQLAlchemy models using an in-memory SQLite database.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
from app.models.assessment import Assessment
from app.models.order import Order


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Provide a fresh in-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


def test_user_can_be_created(db):
    user = User(openid="o_abc123")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.id is not None


def test_user_openid_is_unique(db):
    from sqlalchemy.exc import IntegrityError

    db.add(User(openid="o_dup"))
    db.commit()
    db.add(User(openid="o_dup"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_user_created_at_is_set(db):
    user = User(openid="o_time_test")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.created_at is not None


# ---------------------------------------------------------------------------
# Assessment model
# ---------------------------------------------------------------------------


def _make_user(db, openid: str = "o_user") -> User:
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_assessment_can_be_created(db):
    user = _make_user(db)
    a = Assessment(user_id=user.id, session_id="sess-001", signals="{}")
    db.add(a)
    db.commit()
    db.refresh(a)
    assert a.id is not None


def test_assessment_default_status_is_pending(db):
    user = _make_user(db, "o_a2")
    a = Assessment(user_id=user.id, session_id="sess-002", signals="{}")
    db.add(a)
    db.commit()
    db.refresh(a)
    assert a.status == "pending"


def test_assessment_session_id_is_unique(db):
    from sqlalchemy.exc import IntegrityError

    user = _make_user(db, "o_a3")
    db.add(Assessment(user_id=user.id, session_id="sess-dup", signals="{}"))
    db.commit()
    db.add(Assessment(user_id=user.id, session_id="sess-dup", signals="{}"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_assessment_stores_personality_type(db):
    user = _make_user(db, "o_a4")
    a = Assessment(
        user_id=user.id,
        session_id="sess-003",
        signals="{}",
        personality_type="安全型",
        status="complete",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    assert a.personality_type == "安全型"
    assert a.status == "complete"


# ---------------------------------------------------------------------------
# Order model
# ---------------------------------------------------------------------------


def _make_assessment(db, user: User, session_id: str = "sess-ord") -> Assessment:
    a = Assessment(user_id=user.id, session_id=session_id, signals="{}")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_order_can_be_created(db):
    user = _make_user(db, "o_ord1")
    assessment = _make_assessment(db, user)
    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-001",
        amount=990,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    assert order.id is not None


def test_order_default_status_is_pending(db):
    user = _make_user(db, "o_ord2")
    assessment = _make_assessment(db, user, "sess-ord2")
    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-002",
        amount=990,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    assert order.status == "pending"


def test_order_out_trade_no_is_unique(db):
    from sqlalchemy.exc import IntegrityError

    user = _make_user(db, "o_ord3")
    a1 = _make_assessment(db, user, "sess-ord3a")
    a2 = _make_assessment(db, user, "sess-ord3b")
    db.add(Order(user_id=user.id, assessment_id=a1.id, out_trade_no="trade-dup", amount=990))
    db.commit()
    db.add(Order(user_id=user.id, assessment_id=a2.id, out_trade_no="trade-dup", amount=990))
    with pytest.raises(IntegrityError):
        db.commit()


def test_order_amount_stored_in_fen(db):
    user = _make_user(db, "o_ord4")
    assessment = _make_assessment(db, user, "sess-ord4")
    order = Order(
        user_id=user.id,
        assessment_id=assessment.id,
        out_trade_no="trade-003",
        amount=990,  # ¥9.90
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    assert order.amount == 990
