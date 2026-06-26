import asyncio

from app.services import supabase_client as sc


def test_fetch_couple_questions_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(sc, "_fetch_couple_questions_sync",
                        lambda: (calls.append(1), [{"question_id": "A1-1"}])[1])
    sc.clear_couple_questions_cache()
    r1 = asyncio.run(sc.fetch_couple_questions())
    r2 = asyncio.run(sc.fetch_couple_questions())
    assert r1 == r2 == [{"question_id": "A1-1"}]
    assert len(calls) == 1     # 第二次命中缓存
