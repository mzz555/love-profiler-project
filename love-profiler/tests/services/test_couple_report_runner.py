import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.couple_session import CoupleSession
from app.services import couple_report_runner as runner


def _db(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    TS = sessionmaker(bind=eng)
    monkeypatch.setattr(runner, "SessionLocal", TS)
    return TS


def test_run_and_persist_success(monkeypatch):
    TS = _db(monkeypatch)

    async def fake_report(briefing, session_id=None):
        return {"opening": {"body": "x"}, "blindspot_cards": [{"dimension_id": "money"}]}
    monkeypatch.setattr(runner, "write_couple_report", fake_report)
    db = TS()
    db.add(CoupleSession(session_id="s1", pairing_token="t1", initiator_user_id=1,
                         status="generating", a_status="done", b_status="done"))
    db.commit()
    db.close()
    asyncio.run(runner.run_and_persist("s1", {"overview": {}, "dimensions": []}))
    db = TS()
    row = db.query(CoupleSession).filter_by(session_id="s1").first()
    assert row.status == "complete"
    assert json.loads(row.report_json)["blindspot_cards"][0]["dimension_id"] == "money"
    db.close()


def test_run_and_persist_failure_resets(monkeypatch):
    TS = _db(monkeypatch)
    from app.agents.couple_report_writer import CoupleReportWriterError

    async def boom(briefing, session_id=None):
        raise CoupleReportWriterError("x")
    monkeypatch.setattr(runner, "write_couple_report", boom)
    db = TS()
    db.add(CoupleSession(session_id="s2", pairing_token="t2", initiator_user_id=1, status="generating"))
    db.commit()
    db.close()
    asyncio.run(runner.run_and_persist("s2", {"overview": {}, "dimensions": []}))
    db = TS()
    assert db.query(CoupleSession).filter_by(session_id="s2").first().status == "analyzed"
    db.close()
