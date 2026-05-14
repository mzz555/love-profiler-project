"""
Shared pytest fixtures for the love-profiler test suite.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set required env vars before importing app modules
os.environ.setdefault("DOUBAO_API_KEY", "test-key")
os.environ.setdefault("DOUBAO_MODEL", "doubao-test")
os.environ.setdefault("DOUYIN_APP_ID", "test-appid")
os.environ.setdefault("DOUYIN_APP_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-long!!!")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.auth import create_access_token  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_supabase_caches():
    """Drop the in-process question cache between tests so per-test mocks take effect."""
    from app.services import supabase_client
    supabase_client.clear_questions_cache()
    yield
    supabase_client.clear_questions_cache()


@pytest.fixture(scope="function")
def db_engine():
    # StaticPool ensures all connections reuse the same SQLite in-memory DB,
    # which is required when TestClient runs async handlers in worker threads.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_engine):
    """FastAPI test client wired to an isolated in-memory database."""
    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(db_session) -> dict:
    """Return Authorization headers for a freshly created test user."""
    from app.models.user import User

    user = User(openid="o_test_user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_id(db_session) -> int:
    """Create a test user and return its id."""
    from app.models.user import User

    user = User(openid="o_test_user_id")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user.id
