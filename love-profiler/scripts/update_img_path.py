"""一次性脚本：将 base_love_type.img_path 更新为新目录路径"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text

# base_love_type 在 Supabase PostgreSQL，不在 SQLite 业务库
engine = create_engine("postgresql://postgres:postgres@127.0.0.1:54322/postgres")

SQL_UPDATE = """
UPDATE base_love_type
SET img_path = '/static/addtional/character_' || LPAD(id::text, 2, '0') || '_lively.png'
"""

SQL_SELECT = "SELECT id, type_code, img_path FROM base_love_type ORDER BY id"

with engine.connect() as conn:
    conn.execute(text(SQL_UPDATE))
    conn.commit()
    rows = conn.execute(text(SQL_SELECT)).fetchall()
    print(f"{'id':>3}  {'type_code':<12}  img_path")
    print("-" * 60)
    for r in rows:
        print(f"{r[0]:>3}  {r[1]:<12}  {r[2]}")
    print(f"\n✓ 共更新 {len(rows)} 条记录")
