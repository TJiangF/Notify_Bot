import os
import sys
import json
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import snapshot  # noqa: E402

DATA_DIR = os.path.join(BASE, "data")
BJ = timezone(timedelta(hours=8))


def now_bj():
    return datetime.now(BJ)


def refresh_current():
    ssb = snapshot.fetch_ssb_all()
    state = snapshot.base.load_state()
    pd = snapshot.base.fetch_pd(state)
    snapshot.base.save_state(state)
    try:
        notice = snapshot.base.fetch_notice()
    except Exception as e:
        print("预告抓取失败：", repr(e))
        notice = []
    snap = snapshot.build_snapshot(ssb, pd, notice)
    os.makedirs(DATA_DIR, exist_ok=True)
    cur = os.path.join(DATA_DIR, "current.json")
    with open(cur, "w") as f:
        json.dump(snap, f, ensure_ascii=False)
    print(f"已刷新 current.json：随申办 {len(snap['ssb'])} / 明珠 {len(snap['pd'])} / 预告 {len(snap['notice'])}")

    bj = now_bj()
    if 12 <= bj.hour < 14:
        daily = os.path.join(DATA_DIR, bj.strftime("%Y-%m-%d") + ".json")
        if not os.path.exists(daily):
            with open(daily, "w") as f:
                json.dump(snap, f, ensure_ascii=False, indent=1)
            print(f"已保存每日快照 {daily}")
    return cur


if __name__ == "__main__":
    refresh_current()
