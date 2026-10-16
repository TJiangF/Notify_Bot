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
    cur_path = os.path.join(DATA_DIR, "current.json")
    prev = {}
    if os.path.exists(cur_path):
        try:
            prev = json.load(open(cur_path))
        except Exception:
            prev = {}

    ssb_items = prev.get("ssb", [])
    try:
        ssb_items = snapshot.map_ssb(snapshot.fetch_ssb_all())
        print("随申办 OK:", len(ssb_items))
    except Exception as e:
        print("随申办抓取失败，沿用上次:", repr(e))

    state = snapshot.base.load_state()
    pd_items = prev.get("pd", [])
    try:
        pd_items = snapshot.map_pd(snapshot.base.fetch_pd(state))
        snapshot.base.save_state(state)
        print("明珠在线 OK:", len(pd_items))
    except Exception as e:
        print("明珠在线抓取失败，沿用上次:", repr(e))

    notice_items = prev.get("notice", [])
    try:
        notice_items = snapshot.map_notice(snapshot.base.fetch_notice())
        print("预告 OK:", len(notice_items))
    except Exception as e:
        print("预告抓取失败，沿用上次:", repr(e))

    snap = {
        "date": now_bj().strftime("%Y-%m-%d"),
        "generated_at": now_bj().isoformat(timespec="seconds"),
        "ssb": ssb_items,
        "pd": pd_items,
        "notice": notice_items,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cur_path, "w") as f:
        json.dump(snap, f, ensure_ascii=False)
    print(f"已刷新 current.json：随申办 {len(ssb_items)} / 明珠 {len(pd_items)} / 预告 {len(notice_items)}")

    bj = now_bj()
    if 12 <= bj.hour < 14 and ssb_items:
        daily = os.path.join(DATA_DIR, bj.strftime("%Y-%m-%d") + ".json")
        if not os.path.exists(daily):
            with open(daily, "w") as f:
                json.dump(snap, f, ensure_ascii=False, indent=1)
            print(f"已保存每日快照 {daily}")
    return cur_path


if __name__ == "__main__":
    refresh_current()
