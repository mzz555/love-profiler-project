import pytest
import app.services.session_store as ss


@pytest.fixture(autouse=True)
def tmp_sessions_dir(tmp_path, monkeypatch):
    """Redirect session file storage to a temp directory for each test."""
    monkeypatch.setattr(ss, "SESSIONS_DIR", tmp_path / "sessions")
