import os
import json
import time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "data", "geocache.json")
AMAP_WEB_KEY = os.environ.get("AMAP_WEB_KEY", "c10424f5d1ba284ca4473bc03c8ed18f")

_LOADED = None


def _load():
    global _LOADED
    if _LOADED is None:
        if os.path.exists(CACHE):
            try:
                _LOADED = json.load(open(CACHE))
            except Exception:
                _LOADED = {}
        else:
            _LOADED = {}
    return _LOADED


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(_LOADED, open(CACHE, "w"), ensure_ascii=False)
    except Exception:
        pass


def _query(address, city="上海"):
    for attempt in range(4):
        try:
            r = requests.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"address": address, "city": city, "key": AMAP_WEB_KEY},
                timeout=15,
            )
            j = r.json()
            if j.get("status") == "1" and j.get("geocodes"):
                lng, lat = [float(x) for x in j["geocodes"][0]["location"].split(",")]
                return {"lng": lng, "lat": lat}
            info = j.get("info", "")
            if "EXCEEDED" in info or "QUOTA" in info or "LIMIT" in info:
                time.sleep(0.6 * (attempt + 1))
                continue
            return None
        except Exception as e:
            print("geocode 失败:", address, repr(e))
            time.sleep(0.6 * (attempt + 1))
    return None


def geocode(addr, district="", city="上海", cache_only=False):
    """地址 -> {lng, lat} 或 None（带区上下文提高准确率；结果缓存到 data/geocache.json）"""
    addr = (addr or "").strip()
    if not addr:
        return None
    d = _load()
    if addr in d:
        return d[addr]
    if cache_only:
        return None
    variants = [addr]
    if "上海" not in addr:
        if district:
            variants.insert(0, f"上海市{district}{addr}")
        v2 = f"上海市{addr}"
        if v2 not in variants:
            variants.append(v2)
    for v in variants:
        c = _query(v)
        if c:
            d[addr] = c
            _save()
            return c
    d[addr] = None
    _save()
    return None


def suggest(keywords, city="上海"):
    """输入提示（POI+地址），返回 [{name,district,addr,lng,lat}]"""
    keywords = (keywords or "").strip()
    if not keywords:
        return []
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/assistant/inputtips",
            params={"keywords": keywords, "city": city, "citylimit": "true", "key": AMAP_WEB_KEY},
            timeout=10,
        )
        j = r.json()
    except Exception as e:
        print("inputtips 失败:", keywords, repr(e))
        return []
    out = []
    for t in j.get("tips", []) or []:
        loc = t.get("location") or ""
        if "," not in loc:
            continue
        try:
            lng, lat = [float(x) for x in loc.split(",")]
        except Exception:
            continue
        name = t.get("name") or ""
        if not name:
            continue
        out.append({"name": name, "district": t.get("district") or "",
                    "addr": t.get("address") or t.get("district") or "",
                    "lng": lng, "lat": lat})
    return out


def build(items):
    """批量地理编码（items: [(addr, district)] 或 [addr]）"""
    fail = 0
    for it in items:
        a, dist = (it[0], it[1]) if isinstance(it, (tuple, list)) else (it, "")
        if geocode(a, district=dist) is None:
            fail += 1
        time.sleep(0.2)
    print(f"完成：{len(items)} 个地址，失败 {fail}")
