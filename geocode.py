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


def geocode(addr, city="上海", cache_only=False):
    """地址 -> {lng, lat} 或 None（结果缓存到 data/geocache.json）"""
    addr = (addr or "").strip()
    if not addr:
        return None
    d = _load()
    if addr in d:
        return d[addr]
    if cache_only:
        return None
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"address": addr, "city": city, "key": AMAP_WEB_KEY},
            timeout=15,
        )
        j = r.json()
        if j.get("status") == "1" and j.get("geocodes"):
            loc = j["geocodes"][0]["location"]  # "lng,lat"
            lng, lat = [float(x) for x in loc.split(",")]
            d[addr] = {"lng": lng, "lat": lat}
            _save()
            return d[addr]
    except Exception as e:
        print("geocode 失败:", addr, repr(e))
    d[addr] = None
    _save()
    return None


def build(addresses):
    """批量地理编码（首次构建缓存用）"""
    ori = 0
    for a in addresses:
        if geocode(a) is None:
            ori += 1
        time.sleep(0.05)
    print(f"完成：{len(addresses)} 个地址，失败 {ori}")
