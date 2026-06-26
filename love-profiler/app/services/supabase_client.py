"""
Questions fetcher — reads questions table directly via SQLAlchemy.

The Supabase REST API (Kong gateway) may reject newer publishable key formats.
Using the direct PostgreSQL connection is more reliable for local development.
"""

from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal

# Questions table is read-only at runtime (managed via supabase migrations);
# cache the 30-row result in-process to skip a DB round-trip on every quiz_submit.
_questions_cache: list[dict] | None = None


def clear_questions_cache() -> None:
    """Reset the in-process cache. Tests with their own DB swap should call this."""
    global _questions_cache
    _questions_cache = None


def _fetch_questions_sync() -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(
            text("SELECT * FROM questions ORDER BY sort_order ASC")
        )
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_questions() -> list[dict]:
    """Fetch all questions ordered by sort_order (cached after first call)."""
    global _questions_cache
    if _questions_cache is None:
        _questions_cache = await run_in_threadpool(_fetch_questions_sync)
    return _questions_cache


_couple_questions_cache: list[dict] | None = None


def clear_couple_questions_cache() -> None:
    global _couple_questions_cache
    _couple_questions_cache = None


def _fetch_couple_questions_sync() -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM couple_questions ORDER BY sort_order ASC"))
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_couple_questions() -> list[dict]:
    """Fetch 双人题库题干（首次后进程内缓存）。"""
    global _couple_questions_cache
    if _couple_questions_cache is None:
        _couple_questions_cache = await run_in_threadpool(_fetch_couple_questions_sync)
    return _couple_questions_cache


def _fetch_love_type_sync(type_code: str) -> dict | None:
    db = SessionLocal()
    try:
        result = db.execute(
            text("SELECT type_code, type_name, img_path, detail, tagline FROM base_love_type WHERE type_code = :tc"),
            {"tc": type_code},
        )
        row = result.fetchone()
        if row is None:
            return None
        return dict(row._mapping)
    finally:
        db.close()


async def fetch_love_type(type_code: str) -> dict | None:
    """Look up type_code → {type_name, img_path, detail (anchor sentence), tagline (副标题)}.

    Returns:
        Dict with type_code, type_name, img_path, detail, tagline; or None if not found.
    """
    return await run_in_threadpool(_fetch_love_type_sync, type_code)


_all_love_types_cache: list[dict] | None = None


def _fetch_all_love_types_sync() -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "SELECT id, type_code, type_name, img_path "
                "FROM base_love_type ORDER BY id ASC"
            )
        )
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_all_love_types() -> list[dict]:
    """按 id ASC 拉取全部 16 类恋爱人格的展示字段（首页轮播用，进程内缓存）。

    Returns:
        [{id, type_code, type_name, img_path}, ...] 共 16 条。img_path 为逗号分隔
        的 "man路径,woman路径"，与 loading.js 现有解析方式保持一致。
    """
    global _all_love_types_cache
    if _all_love_types_cache is None:
        _all_love_types_cache = await run_in_threadpool(_fetch_all_love_types_sync)
    return _all_love_types_cache


def _fetch_d4_details_sync(codes: list[str]) -> list[dict]:
    if not codes:
        return []
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                'SELECT love_languages_code AS code, love_languages_name AS name, '
                'love_languages_detail AS detail FROM "base_D4_type" '
                'WHERE love_languages_code = ANY(:codes)'
            ),
            {"codes": codes},
        )
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_d4_details(codes: list[str]) -> list[dict]:
    """Look up love-language records for the user's D4 top2 codes.

    Returns:
        List of dicts with code (T1-T5), name, detail.
    """
    return await run_in_threadpool(_fetch_d4_details_sync, codes)


def _fetch_d5_guide_sync(quadrant: str) -> dict | None:
    if not quadrant:
        return None
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                'SELECT quadrant, style_name, description, guide '
                'FROM "base_D5_quadrant" WHERE quadrant = :q'
            ),
            {"q": quadrant},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None
    finally:
        db.close()


async def fetch_d5_guide(quadrant: str) -> dict | None:
    """Look up D5 quadrant → writing-direction guide.

    Returns:
        Dict with quadrant, style_name, description (打分算法), guide;
        or None if quadrant not in 9-grid.
    """
    return await run_in_threadpool(_fetch_d5_guide_sync, quadrant)


def _fetch_highlights_by_codes_sync(codes: list[str]) -> list[dict]:
    if not codes:
        return []
    db = SessionLocal()
    try:
        result = db.execute(
            text("SELECT * FROM highlights WHERE code = ANY(:codes) ORDER BY sort_order"),
            {"codes": codes},
        )
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


def _fetch_dimension_meta_sync() -> list[dict]:
    """读取 5 个维度的中文名 + description，供 enrich 注入 prompt context。"""
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "SELECT code, name_cn, description "
                "FROM base_dimension_meta ORDER BY sort_order"
            )
        )
        return [dict(row._mapping) for row in result]
    finally:
        db.close()


async def fetch_dimension_meta() -> list[dict]:
    """异步包装；返回 5 行（D1-D5）维度元信息列表。"""
    return await run_in_threadpool(_fetch_dimension_meta_sync)


def _fetch_segment_decode_sync(type_code: str) -> list[dict]:
    """
    解析 type_code（如 'MS-CL-P'）中的三段代码，
    逐一查 base_segment_decode，返回有序的解码列表。
    列表固定 3 项，对应 D1 / D2 / D3；查无记录时保留占位空字典。
    """
    parts = type_code.split("-") if type_code else []
    dims = ["D1", "D2", "D3"]
    pairs = list(zip(dims, parts))  # [("D1","MS"), ("D2","CL"), ("D3","P")]
    if not pairs:
        return []
    db = SessionLocal()
    try:
        # 构建 OR 条件，避免不同 DB 方言的 row-value 兼容问题
        conditions = " OR ".join(
            [f"(dimension = :d{i} AND code = :c{i})" for i in range(len(pairs))]
        )
        params = {}
        for i, (dim, code) in enumerate(pairs):
            params[f"d{i}"] = dim
            params[f"c{i}"] = code
        result = db.execute(
            text(
                f"SELECT dimension, code, label_cn, is_healthy "
                f"FROM base_segment_decode WHERE {conditions} ORDER BY dimension"
            ),
            params,
        )
        rows = {row.dimension: dict(row._mapping) for row in result}
        # 按 D1→D2→D3 顺序返回，保证前端渲染顺序稳定
        return [rows[d] for d in dims if d in rows]
    finally:
        db.close()


async def fetch_segment_decode(type_code: str) -> list[dict]:
    """查 D1/D2/D3 三段解码，随 meta 消息下发给前端展示人格卡标签。

    Returns:
        [{"dimension":"D1","code":"MS","label_cn":"中度安全型依恋","is_healthy":true}, ...]
    """
    return await run_in_threadpool(_fetch_segment_decode_sync, type_code)


async def fetch_highlights_by_codes(codes: list[str]) -> list[dict]:
    """Look up highlight records by code list from highlights table.

    Returns:
        List of highlight dicts. DB 仍保留 severity/interp_path/trigger_condition 列，
        但 enrich 仅取 code/name_cn/is_positive/report_seed 注入 diagnosis。
    """
    return await run_in_threadpool(_fetch_highlights_by_codes_sync, codes)
