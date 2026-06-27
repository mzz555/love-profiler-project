"""dev_play_partner_b.py — 【DEV 专用】脚本扮演「第二个人 B」答完一次双人测评。

本地 dev-login 只发固定用户，开发者工具里造不出第二个用户(B)，无法触发双人计算。
本脚本造一个不同于 A 的 B 用户，join 指定/最新「等待中」的 session 并随机作答，
从而触发引擎计算 + 报告生成，让 A 的等待页刷出报告。仅供本地联调验收。

用法（在 love-profiler/ 目录下，后端需已启动）：
    python scripts/dev_play_partner_b.py                  # 自动找最新等待中的 session
    python scripts/dev_play_partner_b.py --session <id>   # 指定 session_id（前缀匹配）
    python scripts/dev_play_partner_b.py --token <pairing_token>
    python scripts/dev_play_partner_b.py --base http://127.0.0.1:8000 --no-poll
"""
import argparse
import io
import random
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings
from app.database import SessionLocal
from app.middleware.auth import create_access_token
from app.models.couple_session import CoupleSession
from app.models.user import User

B_OPENID_DEFAULT = "dev_test_user_b"


def get_or_create_b(openid: str) -> int:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.openid == openid).first()
        if u is None:
            u = User(openid=openid)
            db.add(u); db.commit(); db.refresh(u)
        return u.id
    finally:
        db.close()


def pick_session(session_arg: str | None, token_arg: str | None) -> tuple[str, str, int]:
    db = SessionLocal()
    try:
        q = db.query(CoupleSession)
        if token_arg:
            s = q.filter(CoupleSession.pairing_token == token_arg).first()
        elif session_arg:
            s = q.filter(CoupleSession.session_id.like(session_arg + "%")).first()
        else:
            s = (q.filter(CoupleSession.a_status == "done",
                          CoupleSession.b_status == "pending",
                          CoupleSession.partner_user_id.is_(None))
                  .order_by(CoupleSession.created_at.desc()).first())
        if s is None:
            sys.exit("找不到符合条件的 session（需 A 已 done、尚无搭档）。")
        return s.session_id, s.pairing_token, s.initiator_user_id
    finally:
        db.close()


def rand_value(q: dict) -> int:
    return random.randint(0, 100) if q["item_type"] == "slider" else random.randint(1, 7)


def main() -> None:
    if not settings.dev_mode:
        sys.exit("拒绝执行：本脚本仅在 DEV_MODE=true 下可用。")

    ap = argparse.ArgumentParser(description="DEV：扮演第二人 B 答完一次双人测评")
    ap.add_argument("--session", help="目标 session_id（前缀匹配）")
    ap.add_argument("--token", help="目标 pairing_token（精确）")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="后端 base URL")
    ap.add_argument("--openid", default=B_OPENID_DEFAULT, help="B 的 openid")
    ap.add_argument("--no-poll", action="store_true", help="提交后不轮询结果")
    args = ap.parse_args()

    b_id = get_or_create_b(args.openid)
    print(f"B user_id = {b_id}（openid={args.openid}）")

    session_id, token, a_id = pick_session(args.session, args.token)
    if b_id == a_id:
        sys.exit(f"B({b_id}) 与发起方 A({a_id}) 相同，请换一个 --openid。")
    print(f"目标 session: {session_id[:8]} | A_uid={a_id} | token={token[:12]}...")

    headers = {"Authorization": "Bearer " + create_access_token(b_id)}

    r = httpx.post(args.base + "/couple/join", json={"pairing_token": token}, headers=headers, timeout=20)
    print("join:", r.status_code, r.text[:120])
    r.raise_for_status()
    qs = r.json()["questions"]

    self_ans = [{"question_id": q["question_id"], "value": rand_value(q)} for q in qs]
    pred = [{"question_id": q["question_id"], "value": rand_value(q)} for q in qs if q.get("apply_prediction")]
    print(f"提交：self={len(self_ans)} predicted={len(pred)}")

    r = httpx.post(args.base + "/couple/answer",
                   json={"session_id": session_id, "self": self_ans, "predicted": pred, "skipped": []},
                   headers=headers, timeout=90)
    print("answer:", r.status_code, r.text[:160])
    r.raise_for_status()

    if args.no_poll:
        return
    for i in range(12):
        r = httpx.get(args.base + "/couple/result", params={"session_id": session_id}, headers=headers, timeout=20)
        st = r.json().get("status") if r.status_code == 200 else r.status_code
        print(f"poll {i}: http={r.status_code} status={st}")
        if r.status_code == 200 and r.json().get("status") == "complete":
            rep = r.json()["report"]
            print("报告已生成，盲区卡片数 =", len(rep.get("blindspot_cards", [])))
            return
        time.sleep(3)
    print("轮询结束仍未 complete（报告可能仍在生成或 LLM 失败）。")


if __name__ == "__main__":
    main()
