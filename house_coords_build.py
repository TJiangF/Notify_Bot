#!/usr/bin/env python3
"""缓存随申办/明珠在线全部房源坐标，供智能找房默认全量地图使用。"""
import os
import json
import time
import argparse

import geocode

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CURRENT = os.path.join(DATA, "current.json")
CACHE = os.path.join(DATA, "house_coords.json")


def _load(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    cur = _load(CURRENT)
    cache = _load(CACHE)
    changed = 0
    for src in ("ssb", "pd"):
        for x in cur.get(src) or []:
            pid = str(x.get("id") or "")
            addr = (x.get("addr") or "").strip()
            if not pid or not addr:
                continue
            ck = f"{src}:{pid}"
            old = cache.get(ck)
            if old and old.get("addr") == addr and old.get("lng") is not None and not args.force:
                continue
            c = geocode.geocode(addr, x.get("district") or "")
            cache[ck] = {"addr": addr,
                         "lng": c["lng"] if c else None,
                         "lat": c["lat"] if c else None}
            changed += 1
            if changed % 10 == 0:
                _save(CACHE, cache)
                print(f"进度：已更新 {changed}", flush=True)
            time.sleep(args.sleep)
    _save(CACHE, cache)
    have = sum(1 for v in cache.values() if v.get("lng") is not None)
    print(f"完成：{len(cache)} 条，坐标有效 {have}，本次更新 {changed}", flush=True)


if __name__ == "__main__":
    main()
