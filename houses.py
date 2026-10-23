import os
import sys
import json
import time
import threading

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CACHE_FILE = os.path.join(DATA_DIR, "houses.json")
IMG_DIR = os.path.join(DATA_DIR, "hximg")

Z_BASE = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/"
SSB_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20 MiniProgramEnv/Mac"
)

_LOCK = threading.Lock()
_CACHE = None


def _cookie():
    return os.environ.get("ACTIVE_COOKIE_S") or os.environ.get("SSB_COOKIE", "")


def _hdr(cookie, pid=""):
    h = {
        "User-Agent": SSB_UA,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://zwdt.sh.gov.cn",
        "Referer": "https://zwdt.sh.gov.cn/smzy/sh_zf_onething_mobile/rent-house/assurance-info?projectId=" + pid,
        "Cookie": cookie,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return h


def _check(j, url):
    if isinstance(j, dict) and "code" in j and str(j["code"]) == "10000":
        raise RuntimeError("随申办登录失效(需更新Cookie)")
    return j


def hx_info(cookie, pid, timeout=25):
    h = _hdr(cookie, pid)
    r = requests.post(Z_BASE + "hxInfoByProjectId", headers=h, data={"projectId": pid}, timeout=timeout)
    j = _check(r.json(), r.url)
    inner = j["data"]
    if isinstance(inner, str):
        inner = json.loads(inner)
    return inner.get("data") or {}


def house_list(cookie, pid, page_no=1, page_size=500, timeout=25):
    h = _hdr(cookie, pid)
    payload = "params=" + json.dumps(
        {"pageNo": page_no, "pageSize": page_size, "param": {"projectId": pid}}, ensure_ascii=False)
    r = requests.post(Z_BASE + "getHouseListByHx", headers=h, data=payload, timeout=timeout)
    j = _check(r.json(), r.url)
    inner = j["data"]
    if isinstance(inner, str):
        inner = json.loads(inner)
    d = inner.get("data") or {}
    return {"results": (d.get("results") or []),
            "totalCount": d.get("totalCount") or 0,
            "pageNo": d.get("pageNo"), "pageSize": d.get("pageSize")}


def house_detail(cookie, hid, pid="", timeout=25):
    h = _hdr(cookie, pid)
    r = requests.post(Z_BASE + "getHouseInfoById", headers=h, data={"houseId": hid}, timeout=timeout)
    j = _check(r.json(), r.url)
    inner = j["data"]
    if isinstance(inner, str):
        inner = json.loads(inner)
    return inner.get("data") or {}


def _photo_cookie():
    c = os.environ.get("HX_PHOTO_COOKIE", "")
    if c and len(c) > 40:
        import base64
        return base64.b64decode(c).decode()
    f = os.path.join(BASE, "flow_cookie.txt")
    if os.path.exists(f):
        return open(f).read().strip()
    return _cookie()


def fetch_photo(cookie, fid, pid="", timeout=25):
    os.makedirs(IMG_DIR, exist_ok=True)
    path = os.path.join(IMG_DIR, fid)
    if os.path.exists(path) and os.path.getsize(path) > 512:
        return True
    ck = _photo_cookie() or cookie
    h = dict(_hdr(ck, pid))
    h.pop("Content-Type", None)
    try:
        r = requests.get(Z_BASE + "getHxPhoto", headers=h, params={"doorTypeFileId": fid}, timeout=timeout)
        ct = (r.headers.get("Content-Type") or "").lower()
        ok = r.status_code == 200 and ("image" in ct or r.content[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xdb")) and len(r.content) > 512
        if ok:
            open(path, "wb").write(r.content)
            return True
    except Exception:
        pass
    return False


def _cls(rows):
    return (rows or []) if isinstance(rows, list) else []


def collect(pid, page_size=500, max_pages=4, detail_n=0, cookie=None, pace=3.0):
    cookie = cookie or _cookie()
    if not cookie:
        raise RuntimeError("缺少随申办 Cookie(SSB_COOKIE)")
    hx = hx_info(cookie, pid)
    time.sleep(pace)
    rows, total, page = [], None, 1
    for page in range(1, max_pages + 1):
        d = None
        for attempt in range(6):
            d = house_list(cookie, pid, page, page_size)
            if d.get("results"):
                break
            time.sleep(min(20, 4.0 * (attempt + 1)))
        rows += _cls(d["results"])
        total = d["totalCount"]
        if not rows or len(rows) >= (total or 0):
            break
        time.sleep(pace)
    types = []
    for dt in (hx.get("doorTypes") or []):
        t = dict(dt.get("doorType") or {})
        t["files"] = [f for f in (dt.get("files") or []) if f]
        types.append(t)
    proj = {
        "projectId": pid,
        "projectName": (hx.get("project") or {}).get("projectName") or "",
        "projectLocation": (hx.get("project") or {}).get("projectLocation") or "",
    }
    rec = {"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "project": proj, "types": types,
           "houses": rows, "details": {}, "photofail": []}
    snap = load_cache()
    old = (snap.get(pid) or {}).get("details") if isinstance(snap, dict) else None
    if isinstance(old, dict):
        rec["details"] = old
    else:
        rec["details"] = {}
    save_record(pid, rec)
    return {"types": types, "houses": rows, "total": total}


def collect_details(pid, house_ids, cookie=None, pace=2.5):
    """给指定 houseId 抓单套详情并并入缓存; 返回 {houseId: houseInfo}"""
    cookie = cookie or _cookie()
    cur = load_cache()
    rec = cur.get(pid) or {}
    details = rec.get("details") or {}
    out = {}
    for i, hid in enumerate(house_ids):
        hid = str(hid)
        got = None
        for attempt in range(4):
            try:
                hd = house_detail(cookie, hid, pid)
            except Exception:
                hd = {}
            if hd.get("houseInfo"):
                got = hd
                break
            time.sleep(min(15, 3.0 * (attempt + 1)))
        if got:
            out[hid] = got.get("houseInfo") or {}
        if i < len(house_ids) - 1:
            time.sleep(pace)
    details.update(out)
    rec["details"] = details
    cur[pid] = rec
    save_cache(cur)
    return out


def collect_photos(pid, cookie=None, limit=6):
    cookie = cookie or _cookie()
    rec = (load_cache().get(pid)) or {}
    fails = []
    done = 0
    for t in (rec.get("types") or []):
        for f in (t.get("files") or []):
            fid = f.get("fileId") if isinstance(f, dict) else f
            if not fid:
                continue
            if fetch_photo(cookie, fid, pid):
                done += 1
            else:
                fails.append(fid)
            if done >= limit:
                break
        if done >= limit:
            break
    if fails:
        rec.setdefault("photofail", [])
        save_record(pid, rec)
    return {"ok": done, "fail": fails}


def pick_sample(pid, n_total=10, free=5):
    """从缓存选样例房源：前 free 套未出租(尽量不同户型) + 其余已出租(尽量不同户型)"""
    rec = load_cache().get(pid) or {}
    houses = rec.get("houses") or []
    n_total = max(1, int(n_total))
    n_free = min(max(0, int(free)), n_total)
    pick = []

    def take(pool, want, taken):
        kinds = set()
        for h in pool:
            if len(taken) >= want:
                break
            k = str(h.get("doorTypeNmae") or h.get("doorType"))
            if k in kinds:
                continue
            kinds.add(k)
            taken.append(h)
        for h in pool:
            if len(taken) >= want:
                break
            if h not in taken:
                taken.append(h)

    def mark_free(h_):
        return (h_ or {}).get("rentStatus") == "未出租"

    free_rows = [h for h in houses if mark_free(h)]
    rented = [h for h in houses if not mark_free(h)]
    taken = pick
    a = []
    take(free_rows, n_free, a)
    for h in a:
        if len(pick) < n_total:
            pick.append(h)
    b = []
    take(rented, n_total - len(pick), b)
    for h in b:
        if len(pick) < n_total:
            pick.append(h)
    return pick[:n_total]


def load_cache():
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        if os.path.exists(CACHE_FILE):
            try:
                _CACHE = json.load(open(CACHE_FILE))
            except Exception:
                _CACHE = {}
        else:
            _CACHE = {}
        if not isinstance(_CACHE, dict):
            _CACHE = {}
        return _CACHE


def save_cache(d):
    global _CACHE
    with _LOCK:
        _CACHE = d
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        json.dump(d, open(tmp, "w"), ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)


def save_record(pid, rec):
    d = load_cache()
    d[pid] = rec
    save_cache(d)


def img_path(fid):
    if not fid or any(c in fid for c in "/\\.."):
        return None
    p = os.path.join(IMG_DIR, fid)
    return p if os.path.exists(p) else None


def _norm_rows(rows):
    out = []
    for h in rows or []:
        sub = h.get("subRoomNumber")
        bed = h.get("bedNumber")
        hr = "合租(床位)" if (bed or (sub and str(sub).strip() not in ("", "-", "None"))) else "整租"
        out.append({
            "houseId": str(h.get("houseId") or ""),
            "dt": str(h.get("doorType") or ""),
            "dtName": h.get("doorTypeNmae") or "",
            "room": (h.get("roomNumber") or "") + (("+" + str(sub)) if sub else ""),
            "bed": bed or "",
            "area": h.get("area") or "",
            "rentStatus": h.get("rentStatus") or "",
            "lock": h.get("lockStatus"),
            "cs": h.get("contractStatus"),
        })
    return out


def summary(pid):
    """给 /api/hx 用：项目+每个户型汇总（含从已缓存房源统计的可租/已租/锁定）"""
    rec = load_cache().get(pid) or {}
    houses = _norm_rows(rec.get("houses") or [])
    stats = {}
    for r in houses:
        k = r["dt"]
        s = stats.setdefault(k, {"total": 0, "free": 0, "rented": 0, "lock": 0})
        s["total"] += 1
        if r["rentStatus"] == "未出租":
            s["free"] += 1
        else:
            s["rented"] += 1
        if r["lock"]:
            s["lock"] += 1
    types = []
    for t in (rec.get("types") or []):
        code = str(t.get("doorTypeCode") or t.get("doorType") or "")
        imgs = []
        for f in (t.get("files") or []):
            fid = f.get("fileId") if isinstance(f, dict) else f
            if fid and img_path(fid):
                imgs.append("/hximg/" + fid)
        types.append({
            "code": code,
            "id": t.get("doorTypeId") or "",
            "name": t.get("doorTypeName") or "",
            "online": t.get("onlineFlatNum") if t.get("onlineFlatNum") is not None else t.get("online"),
            "total": t.get("totalFlatNum"),
            "off": t.get("offlineFlatNum"),
            "rentLow": t.get("onlineRentLow"),
            "rentHigh": t.get("onlineRentHigh"),
            "areaLow": t.get("onlineAreaLow"),
            "areaHigh": t.get("onlineAreaHigh"),
            "turn": t.get("turnPersonNum"),
            "imgs": imgs,
            "stats": stats.get(code) or {"total": 0, "free": 0, "rented": 0, "lock": 0},
        })
    return {"ok": True, "project": rec.get("project") or {}, "types": types,
            "houseCnt": len(houses), "detailCnt": len(rec.get("details") or {}),
            "updated": rec.get("updated") or ""}


def rows(pid, dt="", only_free=False, limit=200, offset=0):
    rec = load_cache().get(pid) or {}
    rows_list = _norm_rows(rec.get("houses") or [])
    det = rec.get("details") or {}
    res = []
    for r in rows_list:
        if dt and r["dt"] != dt and r["dtName"] != dt:
            continue
        if only_free and r["rentStatus"] != "未出租":
            continue
        info = det.get(r["houseId"]) or {}
        r2 = dict(r)
        r2["rent"] = info.get("monthRent") or info.get("marketMonthRent") or ""
        r2["rentType"] = info.get("rentTypeName") or ""
        r2["supply"] = info.get("supplyStatusValue") or info.get("supplyStatus") or ""
        res.append(r2)
    return res[offset:offset + max(1, int(limit))]
