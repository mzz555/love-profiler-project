import sys
import io
import openpyxl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

wb = openpyxl.load_workbook(r'C:\Users\Administrator\Desktop\恋爱侧写项目_V1题库_v0草稿.xlsx')
ws = wb['全题汇总']

rows = []
for row in ws.iter_rows(values_only=True):
    if row[0] and row[0] != '题号':
        rows.append(row)

def esc(s):
    if s is None:
        return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"

lines = []
lines.append("""CREATE TABLE IF NOT EXISTS questions (
  id            SERIAL PRIMARY KEY,
  question_id   TEXT NOT NULL UNIQUE,
  dimension     TEXT NOT NULL,
  sub_dimension TEXT,
  signal_code   TEXT,
  signal_name   TEXT,
  question_type TEXT,
  stem          TEXT NOT NULL,
  option_a      TEXT NOT NULL,
  score_a       TEXT NOT NULL,
  option_b      TEXT NOT NULL,
  score_b       TEXT NOT NULL,
  option_c      TEXT NOT NULL,
  score_c       TEXT NOT NULL,
  option_d      TEXT NOT NULL,
  score_d       TEXT NOT NULL,
  option_e      TEXT,
  score_e       TEXT,
  source        TEXT,
  design_notes  TEXT,
  version       TEXT DEFAULT 'v0',
  status        TEXT DEFAULT '待审',
  sort_order    INTEGER NOT NULL
);
""")

for i, r in enumerate(rows, 1):
    question_id = esc(r[0])
    dimension   = esc(r[1])
    sub_dim     = esc(r[2])
    sig_code    = esc(r[3])
    sig_name    = esc(r[4])
    q_type      = esc(r[5])
    stem        = esc(r[6])
    opt_a       = esc(r[7])
    sc_a        = esc(r[8])
    opt_b       = esc(r[9])
    sc_b        = esc(r[10])
    opt_c       = esc(r[11])
    sc_c        = esc(r[12])
    opt_d       = esc(r[13])
    sc_d        = esc(r[14])
    opt_e       = esc(r[15])
    sc_e        = esc(r[16])
    source      = esc(r[17])
    notes       = esc(r[18])
    version     = esc(r[19]) if r[19] else "'v0'"
    status      = esc(r[20]) if r[20] else "'待审'"

    # D3-Q06: -2追/-2逃 统一为 -2
    if r[0] == 'D3-Q06':
        sc_c = "'-2'"
        sc_d = "'-2'"

    sql = (
        f"INSERT INTO questions "
        f"(question_id,dimension,sub_dimension,signal_code,signal_name,question_type,"
        f"stem,option_a,score_a,option_b,score_b,option_c,score_c,option_d,score_d,"
        f"option_e,score_e,source,design_notes,version,status,sort_order)\n"
        f"VALUES ({question_id},{dimension},{sub_dim},{sig_code},{sig_name},{q_type},"
        f"{stem},{opt_a},{sc_a},{opt_b},{sc_b},{opt_c},{sc_c},{opt_d},{sc_d},"
        f"{opt_e},{sc_e},{source},{notes},{version},{status},{i});"
    )
    lines.append(sql)

print('\n'.join(lines))
