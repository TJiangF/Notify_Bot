#!/usr/bin/env python3
"""随申办房源 -> 最近地铁站(1.5km) + 线路，增量缓存。

数据源：
- 地址坐标：geocode.py（AMap 地理编码，data/geocache.json）
- 周边地铁站：AMap place/around types=150500 radius=1500
- 站内线路：AMap bus/stopname（取“地铁站”站点的“地铁X号线”）

输出：
- data/ssb_metro.json          projectId -> {addr, known, near:{name,dist,lines}, lines}
- data/metro_station_lines.json station -> {station, lines}
"""
import os
import re
import json
import time
import argparse

import requests

import geocode

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CURRENT = os.path.join(DATA, "current.json")
CACHE = os.path.join(DATA, "ssb_metro.json")
STATION_CACHE = os.path.join(DATA, "metro_station_lines.json")
AMAP_KEY = geocode.AMAP_WEB_KEY
RADIUS = 1500


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


def _normalize_station(name):
    s = (name or "").strip()
    s = re.sub(r"[（(]?地铁站.*$", "", s).strip()
    s = s.rstrip("（( ")
    return s


def _line_name(busline):
    n = (busline or "").strip()
    m = re.match(r"^地铁(.+?)\(", n)
    if m:
        return m.group(1).strip()
    m = re.match(r"^地铁(.+)$", n)
    if m:
        return m.group(1).strip()
    return ""


def _station_lines(station, cache):
    if not station:
        return []
    if station in cache:
        return cache[station].get("lines") or []
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/bus/stopname",
            params={"key": AMAP_KEY, "keywords": station, "city": "上海"},
            timeout=20,
        )
        j = r.json()
        stops = j.get("busstops") or []
    except Exception:
        return []
    target = None
    for s in stops:
        nm = s.get("name") or ""
        if "地铁站" in nm:
            target = s
            break
    if target is None:
        for s in stops:
            if any((b.get("name") or "").startswith("地铁") for b in (s.get("buslines") or [])):
                target = s
                break
    if target is None:
        cache[station] = {"station": "", "lines": [], "ts": time.time()}
        return []
    lines = []
    for b in target.get("buslines") or []:
        line = _line_name(b.get("name"))
        if line and line not in lines:
            lines.append(line)
    cache[station] = {"station": target.get("name") or "", "lines": lines, "ts": time.time()}
    return lines


def nearest_metro(addr, district, station_cache):
    c = geocode.geocode(addr, district)
    if not c:
        return {"known": False, "near": None, "lines": []}
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params={"key": AMAP_KEY, "location": f"{c['lng']},{c['lat']}",
                    "radius": RADIUS, "types": "150500", "sortrule": "distance",
                    "offset": 25, "page": 1, "extensions": "base"},
            timeout=20,
        )
        j = r.json()
        if j.get("status") != "1":
            return None
        pois = j.get("pois") or []
    except Exception:
        return None
    if not pois:
        return {"known": True, "near": None, "lines": []}
    cand = [p for p in pois
            if "出入口" not in (p.get("name") or "")
            and "号口" not in (p.get("name") or "")]
    if not cand:
        cand = pois
    p = min(cand, key=lambda x: int(x.get("distance") or 999999))
    station = _normalize_station(p.get("name"))
    lines = _station_lines(station, station_cache)
    dist = int(p.get("distance") or 0)
    return {"known": True,
            "near": {"name": station, "dist": dist, "lines": lines},
            "lines": lines}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    cur = _load(CURRENT)
    projects = cur.get("ssb") or []
    cache = _load(CACHE)
    pcache = cache.get("projects") or {}
    station_cache = _load(STATION_CACHE)

    changed = 0
    for idx, x in enumerate(projects):
        if args.limit and changed >= args.limit:
            break
        pid = str(x.get("id") or "")
        addr = (x.get("addr") or "").strip()
        if not pid or not addr:
            continue
        old = pcache.get(pid)
        if old and old.get("addr") == addr and not args.force:
            continue
        res = nearest_metro(addr, x.get("district") or "", station_cache)
        if res is None:
            continue
        res["addr"] = addr
        res["ts"] = time.time()
        pcache[pid] = res
        changed += 1
        if changed % 10 == 0:
            cache["projects"] = pcache
            cache["built_at"] = time.time()
            _save(CACHE, cache)
            _save(STATION_CACHE, station_cache)
            print(f"进度 {idx + 1}/{len(projects)}，已更新 {changed}", flush=True)
        time.sleep(args.sleep)

    cache["projects"] = pcache
    cache["built_at"] = time.time()
    _save(CACHE, cache)
    _save(STATION_CACHE, station_cache)
    print(f"完成：项目 {len(pcache)}，本次更新 {changed}，站点缓存 {len(station_cache)}", flush=True)


if __name__ == "__main__":
    main()
