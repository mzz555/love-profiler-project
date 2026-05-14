import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from sqlalchemy import create_engine, text
engine = create_engine("postgresql://postgres:postgres@127.0.0.1:54322/postgres")
with engine.connect() as conn:
    rows = conn.execute(text("SELECT id, type_code, type_name, tagline FROM base_love_type ORDER BY id")).fetchall()
    for r in rows:
        print(f"{r[0]:>2}. {r[1]:<12} {r[2]}  /  {r[3]}")
