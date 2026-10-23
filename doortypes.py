import os
import re
import time
import json
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE, "data", "doortypes")
IMG_DIR = os.path.join(CACHE_DIR, "img")
API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/hxInfoByProjectId"
PHOTO = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getHxPhoto"
REFERER = "https://zwdt.sh.gov.cn/smzy/sh_zf_onething_mobile/rent-house/assurance-info"


def _cookie():
    return os.environ.get("SSB_COOKIE", "") or os.environ.get("SSB_COOKIE2", "")


def _headers(pid=None):
    h = {"Origin": "https://zwdt.sh.gov.cn", "User-Agent": "Mozilla/5.0",
         "Cookie": _cookie()}
    if pid:
        h["Referer"] = f"{REFERER}?projectId={pid}&supplyWay=2&isQingnian=0"
    else:
        h["Referer"] = REFERER
    return h


def _path(pid):
    return os.path.join(CACHE_DIR, str(pid) + ".json")


def cached(pid):
    return os.path.exists(_path(pid))


def load(pid):
    try:
        return json.load(open(_path(pid)))
    except Exception:
        return None


def project_sig(pid):
    """项目指纹：项目列表里的在线/总套数/租金区间/户型；用于判断是否需要重拉"""
    try:
        import report
        cur = report.load_current()
    except Exception:
        return None
    for x in cur.get("ssb", []):
        if str(x.get("id")) == str(pid):
            return "%s|%s|%s|%s|%s" % (x.get("online"), x.get("total"),
                                       x.get("rent_low"), x.get("rent_high"), x.get("door_type"))
    return None


def fetch(pid, sig=None):
    pid = str(pid)
    if sig is None:
        sig = project_sig(pid)
    r = requests.post(API, headers=_headers(pid), files={"projectId": (None, pid)}, timeout=30)
    r.raise_for_status()
    j = r.json()
    inner = j.get("data")
    if isinstance(inner, str):
        inner = json.loads(inner)
    if not isinstance(inner, dict) or "data" not in inner:
        return None
    d = inner["data"]
    out = {"project": d.get("project") or {}, "doorTypes": d.get("doorTypes") or [],
           "sig": sig, "fetched_at": int(time.time())}
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(out, open(_path(pid), "w"), ensure_ascii=False)
    return out


def ensure(pid):
    """有缓存且项目指纹未变 → 直接用缓存；否则重拉"""
    pid = str(pid)
    c = load(pid)
    sig = project_sig(pid)
    if c is not None and (sig is None or c.get("sig") == sig):
        return c
    return fetch(pid, sig)


def _mime(ext):
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg")


def _sniff(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return "image/jpeg", ".jpg"


def photo(file_id):
    file_id = str(file_id)
    if not re.match(r"^[0-9a-fA-F-]{36}$", file_id):
        raise ValueError("bad file id")
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(IMG_DIR, file_id + ext)
        if os.path.exists(p):
            data = open(p, "rb").read()
            mime, _ = _sniff(data)
            return data, mime
    r = requests.get(PHOTO, headers=_headers(), params={"doorTypeFileId": file_id}, timeout=30)
    r.raise_for_status()
    data = r.content
    mime, ext = _sniff(data)
    os.makedirs(IMG_DIR, exist_ok=True)
    open(os.path.join(IMG_DIR, file_id + ext), "wb").write(data)
    return data, mime
