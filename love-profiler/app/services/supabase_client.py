"""
Supabase client — fetch questions from Supabase REST API using httpx.
"""

import os

import httpx

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


async def fetch_questions() -> list[dict]:
    """Fetch all 30 questions from Supabase ordered by sort_order.

    Returns:
        List of question dicts, each containing question_id, dimension, stem,
        option_a/b/c/d/e, score_a/b/c/d/e, signal_code, etc.

    Raises:
        httpx.HTTPError: If the Supabase request fails.
    """
    url = f"{_SUPABASE_URL}/rest/v1/questions"
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers, params={"order": "sort_order.asc"})
        resp.raise_for_status()
        return resp.json()
