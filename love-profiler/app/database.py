"""
Database — SQLAlchemy engine, declarative base, and session factory.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./love_profiler.db")

_is_dev = os.environ.get("DEV_MODE", "").lower() == "true"
if DATABASE_URL.startswith("sqlite") and not _is_dev:
    raise RuntimeError(
        "生产环境禁止使用 sqlite。请设置 DATABASE_URL 为 PostgreSQL 连接串，"
        "或设置 DEV_MODE=true 以允许 sqlite（仅限开发）。"
    )

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Yield a database session, ensuring it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables defined on Base. Called once at startup."""
    Base.metadata.create_all(bind=engine)
