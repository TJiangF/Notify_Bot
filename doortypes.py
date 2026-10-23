import os
import re
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


def fetch(pid, force=False):
    pid = str(pid)
    if not force:
        c = load(pid)
        if c is not None:
            return c
    r = requests.post(API, headers=_headers(pid), files={"projectId": (None, pid)}, timeout=30)
    r.raise_for_status()
    j = r.json()
    inner = j.get("data")
    if isinstance(inner, str):
        inner = json.loads(inner)
    if not isinstance(inner, dict) or "data" not in inner:
        return None
    d = inner["data"]
    out = {"project": d.get("project") or {}, "doorTypes": d.get("doorTypes") or []}
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(out, open(_path(pid), "w"), ensure_ascii=False)
    return out


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
