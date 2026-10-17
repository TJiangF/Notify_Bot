import os
import json
import requests

import ssb_monitor as base

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch_ssb_all():
    headers = dict(base.HEADERS)
    headers["Cookie"] = base.COOKIE
    param = {
        "districtId": "", "doorType": "", "rentHigh": "", "rentLow": "",
        "searchWord": "", "street": [], "supplyWay": "",
        "ringRdId": "", "orderBy": "", "isAsc": True,
    }
    out = []
    page = 1
    while True:
        data = {"params": json.dumps(
            {"pageNo": page, "pageSize": 500, "param": param},
            ensure_ascii=False,
        )}
        r = requests.post(base.API, headers=headers, data=data, timeout=25)
        r.raise_for_status()
        j = r.json()
        if "data" not in j:
            msg = str(j.get("message") or j.get("url") or j)
            if "查询次数" in msg or "上限" in msg:
                raise base.RateLimitError(msg)
            raise base.AuthError("随申办 Cookie 无效")
        inner = j["data"]
        if isinstance(inner, str):
            inner = json.loads(inner)
        d = inner["data"]
        res = d.get("results", [])
        out.extend(res)
        base.record_usage(1, len(res))
        if page * d.get("pageSize", 500) >= d.get("totalCount", 0):
            break
        page += 1
    return out


def map_ssb(ssb):
    return [{
        "id": r.get("projectId"),
        "name": r.get("projectName"),
        "district": r.get("districtName") or "未知",
        "online": r.get("onlineFlatNum") or 0,
        "total": r.get("totalFlatNum") or 0,
        "rent_low": r.get("rentLow"),
        "rent_high": r.get("rentHigh"),
        "addr": r.get("projectLocation"),
        "tel": r.get("projectTel"),
        "house_type": r.get("houseTypeName"),
        "door_type": r.get("rentDoorTypeName"),
        "supply_start": r.get("concentRateSupplyStartDay"),
        "supply_end": r.get("concentRateSupplyEndDay"),
        "accept_start": r.get("concentRateAcceptStartDay"),
        "accept_end": r.get("concentRateAcceptEndDay"),
        "intro": r.get("projectIntroduction"),
    } for r in (ssb or [])]


def map_pd(pd):
    return [{
        "id": r.get("projectId"),
        "name": r.get("villageProjectName"),
        "district": "浦东新区",
        "kzts": r.get("kzts") or 0,
        "status": r.get("projectStatusName"),
        "addr": r.get("LOCATION"),
        "tel": r.get("lxdh"),
        "price": r.get("price_range"),
        "metro": r.get("metro_subway") or [],
        "zone": r.get("zoneName"),
        "supply_date": r.get("supplyDate"),
        "release_time": r.get("releaseTime"),
        "fylx": r.get("xmfyzts") or [],
    } for r in (pd or [])]


def map_notice(notice):
    return [{
        "id": r.get("noticeId"),
        "name": r.get("projectName"),
        "addr": r.get("projectAddress"),
        "rent": r.get("planRentLevel"),
        "supply_date": r.get("planSupplyDate"),
        "tel": r.get("contact"),
        "org": r.get("orgName"),
        "intro": r.get("introduction"),
    } for r in (notice or [])]


def build_snapshot(ssb, pd, notice):
    return {
        "date": base.now_bj().strftime("%Y-%m-%d"),
        "generated_at": base.now_bj().isoformat(timespec="seconds"),
        "ssb": map_ssb(ssb),
        "pd": map_pd(pd),
        "notice": map_notice(notice),
    }


def collect_and_save():
    ssb = fetch_ssb_all()
    state = base.load_state()
    pd = base.fetch_pd(state)
    base.save_state(state)
    try:
        notice = base.fetch_notice()
    except Exception as e:
        print("预告抓取失败：", repr(e))
        notice = []
    snap = build_snapshot(ssb, pd, notice)
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, snap["date"] + ".json")
    with open(path, "w") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print(f"已保存 {path}：随申办 {len(snap['ssb'])} 条 / 明珠在线 {len(snap['pd'])} 条 / 预告 {len(snap['notice'])} 条")
    return path


if __name__ == "__main__":
    collect_and_save()
