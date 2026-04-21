"""
Tests for session_store — in-memory session storage with TTL expiry.
"""

import time

import pytest

from app.services.session_store import (
    SessionData,
    create_session,
    get_session,
    update_session,
    delete_session,
    is_session_expired,
    append_message,
    SESSION_TTL_SECONDS,
)


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


def test_create_session_returns_session_data():
    session = create_session(user_id="u1")
    assert isinstance(session, SessionData)


def test_create_session_sets_user_id():
    session = create_session(user_id="u42")
    assert session.user_id == "u42"


def test_create_session_starts_at_round_1():
    session = create_session(user_id="u1")
    assert session.round_num == 1


def test_create_session_starts_with_empty_history():
    session = create_session(user_id="u1")
    assert session.messages == []


def test_create_session_sets_created_at():
    before = time.time()
    session = create_session(user_id="u1")
    after = time.time()
    assert before <= session.created_at <= after


def test_create_session_sets_expires_at():
    session = create_session(user_id="u1")
    expected = session.created_at + SESSION_TTL_SECONDS
    assert abs(session.expires_at - expected) < 1


def test_create_session_generates_unique_session_ids():
    s1 = create_session(user_id="u1")
    s2 = create_session(user_id="u1")
    assert s1.session_id != s2.session_id


# ---------------------------------------------------------------------------
# get_session / store persistence
# ---------------------------------------------------------------------------


def test_get_session_returns_stored_session():
    session = create_session(user_id="u1")
    fetched = get_session(session.session_id)
    assert fetched is not None
    assert fetched.session_id == session.session_id


def test_get_session_returns_none_for_unknown_id():
    result = get_session("nonexistent-session-id")
    assert result is None


def test_get_session_returns_none_for_expired_session(monkeypatch):
    session = create_session(user_id="u1")
    # Force expiry by setting expires_at in the past
    expired = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=session.round_num,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=time.time() - 1,  # already expired
    )
    update_session(expired)
    result = get_session(session.session_id)
    assert result is None


# ---------------------------------------------------------------------------
# update_session
# ---------------------------------------------------------------------------


def test_update_session_persists_changes():
    session = create_session(user_id="u1")
    updated = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=3,
        messages=[{"role": "user", "content": "hello"}],
        created_at=session.created_at,
        expires_at=session.expires_at,
    )
    update_session(updated)
    fetched = get_session(session.session_id)
    assert fetched is not None
    assert fetched.round_num == 3
    assert len(fetched.messages) == 1


def test_update_session_does_not_mutate_original():
    session = create_session(user_id="u1")
    original_round = session.round_num
    updated = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=5,
        messages=session.messages,
        created_at=session.created_at,
        expires_at=session.expires_at,
    )
    update_session(updated)
    assert session.round_num == original_round  # original unchanged


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def test_delete_session_removes_from_store():
    session = create_session(user_id="u1")
    delete_session(session.session_id)
    assert get_session(session.session_id) is None


def test_delete_session_is_idempotent():
    session = create_session(user_id="u1")
    delete_session(session.session_id)
    delete_session(session.session_id)  # second call should not raise


# ---------------------------------------------------------------------------
# is_session_expired
# ---------------------------------------------------------------------------


def test_is_session_expired_false_for_fresh_session():
    session = create_session(user_id="u1")
    assert is_session_expired(session) is False


def test_is_session_expired_true_when_past_expiry():
    session = create_session(user_id="u1")
    old = SessionData(
        session_id=session.session_id,
        user_id=session.user_id,
        round_num=1,
        messages=[],
        created_at=session.created_at,
        expires_at=time.time() - 1,
    )
    assert is_session_expired(old) is True


# ---------------------------------------------------------------------------
# append_message
# ---------------------------------------------------------------------------


def test_append_message_returns_new_session_data():
    session = create_session(user_id="u1")
    msg = {"role": "user", "content": "hi"}
    new_session = append_message(session, msg)
    assert new_session is not session  # new object


def test_append_message_adds_to_messages():
    session = create_session(user_id="u1")
    msg = {"role": "user", "content": "hi"}
    new_session = append_message(session, msg)
    assert len(new_session.messages) == 1
    assert new_session.messages[0] == msg


def test_append_message_preserves_existing_messages():
    session = create_session(user_id="u1")
    msg1 = {"role": "user", "content": "first"}
    msg2 = {"role": "assistant", "content": "second"}
    s1 = append_message(session, msg1)
    s2 = append_message(s1, msg2)
    assert len(s2.messages) == 2
    assert s2.messages[0] == msg1
    assert s2.messages[1] == msg2


def test_append_message_does_not_modify_original_messages():
    session = create_session(user_id="u1")
    msg = {"role": "user", "content": "hi"}
    append_message(session, msg)
    assert session.messages == []  # original untouched
