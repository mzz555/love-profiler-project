"""
Admin generic CRUD helpers — query / get / update for TABLE_CONFIG-driven tables.
"""

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session


def query_table(
    db: Session,
    table_name: str,
    config: dict,
    page: int,
    limit: int,
    q: str | None,
) -> dict:
    """通用分页查询，支持多列模糊搜索。表不存在时返回空结果而非 500。"""
    pk = config["pk"]
    offset = (page - 1) * limit
    params: dict = {}

    where_parts: list[str] = []
    if q and config.get("search_cols"):
        for i, col in enumerate(config["search_cols"]):
            where_parts.append(f'LOWER(CAST("{col}" AS TEXT)) LIKE LOWER(:q_{i})')
            params[f"q_{i}"] = f"%{q}%"
    where_clause = ("WHERE " + " OR ".join(where_parts)) if where_parts else ""

    list_cols = config.get("list_cols")
    select_clause = ", ".join(f'"{c}"' for c in list_cols) if list_cols else "*"

    try:
        total = db.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}" {where_clause}'), params
        ).scalar() or 0
        params["limit"] = limit
        params["offset"] = offset
        rows_raw = db.execute(
            text(f'SELECT {select_clause} FROM "{table_name}" {where_clause} '
                 f'ORDER BY "{pk}" DESC LIMIT :limit OFFSET :offset'),
            params,
        ).fetchall()
    except (OperationalError, ProgrammingError):
        return {"total": 0, "page": page, "limit": limit, "rows": [],
                "error": "table_not_available"}

    rows = [dict(row._mapping) for row in rows_raw]
    return {"total": total, "page": page, "limit": limit, "rows": rows}


def get_row(db: Session, table_name: str, config: dict, record_id: str) -> dict:
    """按主键取单条完整记录（大字段不截断）。"""
    pk = config["pk"]
    try:
        row = db.execute(
            text(f'SELECT * FROM "{table_name}" WHERE "{pk}" = :pk_val'),
            {"pk_val": record_id},
        ).fetchone()
    except (OperationalError, ProgrammingError) as exc:
        raise HTTPException(status_code=503, detail="数据库表不可用") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return dict(row._mapping)


def update_row(
    db: Session,
    table_name: str,
    config: dict,
    record_id: str,
    update_data: dict,
) -> dict:
    """按字段白名单更新记录。assessments.status 有额外约束。"""
    editable = set(config.get("editable_fields", []))

    if not editable:
        raise HTTPException(status_code=403,
                            detail=f"表 {table_name} 为只读，不允许修改")

    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供任何字段")

    invalid = set(update_data.keys()) - editable
    if invalid:
        raise HTTPException(status_code=400,
                            detail=f"不可编辑的字段: {', '.join(sorted(invalid))}")

    pk = config["pk"]
    is_status_reset = table_name == "assessments" and "status" in update_data

    if is_status_reset:
        if update_data["status"] != "analyzed":
            raise HTTPException(status_code=422,
                                detail="status 只允许重置为 analyzed")
        try:
            current = db.execute(
                text(f'SELECT status FROM "{table_name}" WHERE "{pk}" = :pk_val'),
                {"pk_val": record_id},
            ).fetchone()
        except (OperationalError, ProgrammingError) as exc:
            raise HTTPException(status_code=503, detail="数据库表不可用") from exc
        if current is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if current.status != "generating":
            raise HTTPException(
                status_code=422,
                detail=f"当前 status={current.status}，只有 generating 状态可以重置",
            )

    set_clause = ", ".join([f'"{k}" = :{k}' for k in update_data.keys()])
    params = {**update_data, "_pk_val": record_id}

    where_extra = ' AND "status" = \'generating\'' if is_status_reset else ""

    try:
        result = db.execute(
            text(f'UPDATE "{table_name}" SET {set_clause} WHERE "{pk}" = :_pk_val{where_extra}'),
            params,
        )
        db.commit()
    except (OperationalError, ProgrammingError) as exc:
        raise HTTPException(status_code=503, detail="数据库表不可用") from exc

    if result.rowcount == 0:
        if is_status_reset:
            raise HTTPException(status_code=422,
                                detail="记录不存在或状态已变更，无法重置")
        raise HTTPException(status_code=404, detail="记录不存在")

    return {"ok": True, "updated": record_id}
