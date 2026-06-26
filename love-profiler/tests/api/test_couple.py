from app.middleware.auth import create_access_token
from app.models.user import User


def _headers(db_session, openid):
    u = User(openid=openid)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return {"Authorization": f"Bearer {create_access_token(u.id)}"}


def _mock_q(monkeypatch):
    from app.api import couple

    async def fake_q():
        return [{"question_id": "A1-1"}]
    monkeypatch.setattr(couple, "fetch_couple_questions", fake_q)


def test_create_and_join(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    r = client.post("/couple/create", headers=a)
    assert r.status_code == 200
    token, sid = r.json()["pairing_token"], r.json()["session_id"]
    b = _headers(db_session, "uB")
    r2 = client.post("/couple/join", headers=b, json={"pairing_token": token})
    assert r2.status_code == 200 and r2.json()["session_id"] == sid


def test_self_pair_rejected(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    a = _headers(db_session, "uA")
    token = client.post("/couple/create", headers=a).json()["pairing_token"]
    assert client.post("/couple/join", headers=a, json={"pairing_token": token}).status_code == 409


def test_join_unknown_token_404(client, db_session, monkeypatch):
    _mock_q(monkeypatch)
    b = _headers(db_session, "uB")
    assert client.post("/couple/join", headers=b, json={"pairing_token": "nope"}).status_code == 404
