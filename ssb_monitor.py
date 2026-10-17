import os
import re
import json
import time
import sys
import base64
import subprocess
from datetime import datetime, timezone, timedelta
import requests

API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList"
NOTICE_API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getNotice"
PD_API = "https://pdrcgy.pudong.gov.cn/api/rcaj/fwcx/getProjectAndHouse.html"
PD_PAGE = "https://pdrcgy.pudong.gov.cn/api/rcaj/fwcx.html?index=0"

WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_SENDKEY", "")
SERVERCHAN_HEARTBEAT = os.environ.get("SERVERCHAN_HEARTBEAT", "0").lower() in ("1", "true", "yes")

COOKIE = os.environ.get("SSB_COOKIE", "")
DISTRICT_ID = os.environ.get("SSB_DISTRICT_ID", "")
DISTRICT_NAME = os.environ.get("SSB_DISTRICT_NAME", "全市")
PD_COOKIE = os.environ.get("PD_COOKIE", "")
PD_CSRF = os.environ.get("PD_CSRF", "")
PD_USER = os.environ.get("PD_USER", "")
PD_PASS = os.environ.get("PD_PASS", "")
PD_ENC_KEY = os.environ.get("PD_ENC_KEY", "")
PD_LOGIN_PAGE = "https://pdrcgy.pudong.gov.cn/api/security/login.html"
PD_CAPTCHA = "https://pdrcgy.pudong.gov.cn/captcha.jpg"
PD_LOGIN_POST = "https://pdrcgy.pudong.gov.cn/login?z=1"
PD_RSA_PUB = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCdkNw/RMcJV84k3PrPWxakctTy"
    "k3vYz4iHwpdq1PxKIIko54c+c2gyNtYaYZjwUmTf1dRvOGelhYLJSr9vx0MQCND"
    "bGWLX1MVUoZWIPw1Le1okyq7WukaPp0y1fpDqLKc7l4UcImTc8S2YynKefXmRBV"
    "W323rD2APrIkobq91aNwIDAQAB"
)
PD_REMEMBER_KEY = "__pd_remember__"

KEYWORDS = [k.strip() for k in os.environ.get(
    "SSB_KEYWORDS", "森兰,中铁,桂竹,海上,西派,海华智,万安里").split(",") if k.strip()]

STATE = os.environ.get("SSB_STATE", "ssb_state.json")
PAGE_SIZE = 500
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FORCE_HEARTBEAT = os.environ.get("SSB_FORCE_HEARTBEAT", "").lower() in ("1", "true", "yes")
SUPPRESS_PUSH = False

IGNORE = {
    "4594": "森兰星遇公寓(新展城店)",
    "3025": "城家高级公寓（森兰洲海路地铁站店）",
}

ERR_SB = "__err_sb__"
ERR_PD = "__err_pd__"
NOTICE_KEY = "__notices__"
HEARTBEAT_KEY = "__last_heartbeat_hour__"
SCOPE_KEY = "__scope__"
PD_PROJECTS_KEY = "__pd_projects__"
HEARTBEAT_HOURS = set(range(8, 21)) | {22}
QUIET_START, QUIET_END = 0, 8

try:
    sys.path.insert(0, BASE_DIR)
    import config as _cfgmod
    _c = _cfgmod.load()
    if _c.get("wecom_webhook"):
        WEBHOOK = _c["wecom_webhook"]
    if _c.get("serverchan_key"):
        SERVERCHAN_KEY = _c["serverchan_key"]
    if _c.get("keywords"):
        KEYWORDS = _c["keywords"]
    if _c.get("ignore"):
        IGNORE = _c["ignore"]
    if _c.get("district_id"):
        DISTRICT_ID = _c["district_id"]
    if _c.get("district_name"):
        DISTRICT_NAME = _c["district_name"]
    if _c.get("heartbeat_hours"):
        HEARTBEAT_HOURS = set(int(h) for h in _c["heartbeat_hours"])
    QUIET_START = int(_c.get("quiet_start", 0))
    QUIET_END = int(_c.get("quiet_end", 8))
except Exception:
    pass

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20 MiniProgramEnv/Mac"
)

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://zwdt.sh.gov.cn",
    "Referer": "https://zwdt.sh.gov.cn/smzy/sh_zf_onething_mobile/rent-house/assurance-find",
    "User-Agent": UA,
    "Cookie": COOKIE,
}


class AuthError(Exception):
    pass


class RateLimitError(Exception):
    pass


class PdAuthError(Exception):
    pass


def fetch_all():
    param = {
        "districtId": DISTRICT_ID, "doorType": "", "rentHigh": "", "rentLow": "",
        "searchWord": "", "street": [], "supplyWay": "",
        "ringRdId": "", "orderBy": "", "isAsc": True,
    }
    out = []
    page = 1
    while True:
        data = {"params": json.dumps(
            {"pageNo": page, "pageSize": PAGE_SIZE, "param": param},
            ensure_ascii=False,
        )}
        r = requests.post(API, headers=HEADERS, data=data, timeout=25)
        r.raise_for_status()
        j = r.json()
        if "data" not in j:
            msg = str(j.get("message") or j.get("url") or j)
            if "查询次数" in msg or "上限" in msg:
                raise RateLimitError(msg)
            raise AuthError(msg)
        inner = j["data"]
        if isinstance(inner, str):
            inner = json.loads(inner)
        d = inner["data"]
        res = d.get("results", [])
        out.extend(res)
        record_usage(1, len(res))
        if page * d.get("pageSize", PAGE_SIZE) >= d.get("totalCount", 0):
            break
        page += 1
    return out


def fetch_notice():
    body = json.dumps({"pageNo": 1, "pageSize": 100, "param": {"noticeId": ""}}, ensure_ascii=False)
    headers = {
        "Origin": "https://zwdt.sh.gov.cn",
        "Referer": "https://zwdt.sh.gov.cn/smzy/sh_zf_onething_mobile/rent-house/assurance-find",
        "User-Agent": UA,
        "Cookie": COOKIE,
    }
    r = requests.post(NOTICE_API, headers=headers, files={"params": (None, body)}, timeout=25)
    r.raise_for_status()
    j = r.json()
    if "data" not in j:
        msg = str(j.get("message") or j.get("url") or j)
        if "查询次数" in msg or "上限" in msg:
            raise RateLimitError(msg)
        raise AuthError(msg)
    inner = j["data"]
    if isinstance(inner, str):
        inner = json.loads(inner)
    res = inner["data"].get("results", [])
    record_usage(1, len(res))
    return res


def _enc(s):
    if not PD_ENC_KEY or not s:
        return s
    from cryptography.fernet import Fernet
    return Fernet(PD_ENC_KEY.encode()).encrypt(s.encode()).decode()


def _dec(s):
    if not s:
        return ""
    if not PD_ENC_KEY:
        return s
    try:
        from cryptography.fernet import Fernet
        return Fernet(PD_ENC_KEY.encode()).decrypt(s.encode()).decode()
    except Exception:
        return ""


_OCR = None


def _ocr():
    global _OCR
    if _OCR is None:
        try:
            import ddddocr
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ddddocr"])
            import ddddocr
        _OCR = ddddocr.DdddOcr(show_ad=False)
    return _OCR


def pd_login():
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = load_der_public_key(base64.b64decode(PD_RSA_PUB))
    enc_pw = base64.b64encode(pub.encrypt(PD_PASS.encode(), padding.PKCS1v15())).decode()
    ocr = _ocr()
    try:
        ocr.set_ranges("0123456789")
    except Exception:
        pass
    s = requests.Session()
    for _ in range(12):
        page = s.get(PD_LOGIN_PAGE, headers={"user-agent": UA}, timeout=25, allow_redirects=False)
        m = re.search(r'name="_csrf"\s+content="([^"]+)"', page.text or "")
        csrf = m.group(1) if m else ""
        img = s.get(PD_CAPTCHA, headers={"user-agent": UA}, timeout=25).content
        code = ocr.classification(img)
        if len(code) != 5 or not code.isdigit():
            print(f"  PD验证码识别为 {code!r}，跳过重取")
            continue
        data = {"username": PD_USER, "password": enc_pw, "captcha": code, "yzm": "",
                "source": "", "remember-me": "true", "_csrf": csrf}
        H = {"X-CSRF-TOKEN": csrf, "X-Requested-With": "XMLHttpRequest",
             "Referer": PD_LOGIN_PAGE, "Origin": "https://pdrcgy.pudong.gov.cn", "user-agent": UA}
        r = s.post(PD_LOGIN_POST, data=data, headers=H, allow_redirects=False, timeout=25)
        loc = r.headers.get("location", "")
        print(f"  PD登录尝试 验证码={code!r} -> {r.status_code} {loc}")
        if r.status_code in (301, 302, 303) and "login.html" not in loc:
            print("  PD登录成功")
            return dict(s.cookies)
    raise PdAuthError("自动登录失败（验证码多次未识别）")


def _pd_request(session):
    page = session.get(PD_PAGE, headers={"accept": "text/html", "user-agent": UA},
                       timeout=25, allow_redirects=False)
    if page.status_code != 200:
        raise PdAuthError(f"页面异常 {page.status_code}")
    m = re.search(r'name="_csrf"\s+content="([^"]+)"', page.text or "")
    csrf = m.group(1) if m else PD_CSRF
    if not csrf:
        raise PdAuthError("未取到 CSRF")
    body = {
        "checkdDicData": {"xm_pq": [], "xm_qy": [], "xm_dtx": "", "xm_dtz": [],
                          "xm_kfs": [], "xm_kzts": [], "xm_zt": [], "xm_fylx": []},
        "xm_input": "", "tj_input": "", "type": 2,
        "page_param": {"PAGE": 1, "LIMIT": 500}, "qyzs": None,
    }
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://pdrcgy.pudong.gov.cn",
        "referer": "https://pdrcgy.pudong.gov.cn/api/rcaj/fwcx.html?index=0",
        "user-agent": UA,
        "x-csrf-token": csrf,
        "x-requested-with": "XMLHttpRequest",
    }
    r = session.post(PD_API, headers=headers, json=body, timeout=25, allow_redirects=False)
    if r.status_code in (301, 302, 303, 307, 308):
        raise PdAuthError("重定向到登录页")
    if r.status_code == 403:
        raise PdAuthError("403（会话或 CSRF 失效）")
    r.raise_for_status()
    try:
        j = r.json()
    except Exception:
        raise PdAuthError("非 JSON 响应（可能未登录）")
    if not isinstance(j, dict) or not any(k in j for k in ("project1", "project2", "project3")):
        raise PdAuthError("响应结构异常")
    seen = {}
    for k in ("project1", "project2", "project3"):
        for it in (j.get(k) or []):
            seen[str(it["projectId"])] = it
    return list(seen.values())


def fetch_pd(state):
    if not (PD_USER or PD_COOKIE):
        return None
    s = requests.Session()
    rm = _dec(state.get(PD_REMEMBER_KEY, ""))
    if rm:
        s.cookies.set("remember-me", rm)
    if PD_COOKIE and not rm:
        for part in PD_COOKIE.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                s.cookies.set(k, v)
    try:
        return _pd_request(s)
    except PdAuthError as e:
        print("PD 会话失效：", e)
        if not (PD_USER and PD_PASS):
            raise
        ck = pd_login()
        rm2 = ck.get("remember-me")
        if rm2:
            state[PD_REMEMBER_KEY] = _enc(rm2)
        s2 = requests.Session()
        for k, v in ck.items():
            s2.cookies.set(k, v)
        return _pd_request(s2)


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {}


def save_state(s):
    with open(STATE, "w") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def project_items(state):
    return {k: v for k, v in state.items() if not str(k).startswith("__")}


def match_keyword(name):
    return [k for k in KEYWORDS if k in (name or "")]


def is_keyword(name):
    return bool(match_keyword(name))


def star(name):
    return "⭐" if is_keyword(name) else "・"


def now_bj():
    return datetime.now(timezone(timedelta(hours=8)))


USAGE_FILE = os.path.join(BASE_DIR, "data", "usage.json")


def record_usage(nreq=0, nrec=0):
    try:
        d = {}
        if os.path.exists(USAGE_FILE):
            d = json.load(open(USAGE_FILE))
        today = now_bj().strftime("%Y-%m-%d")
        e = d.setdefault(today, {"req": 0, "rec": 0})
        e["req"] += nreq
        e["rec"] += nrec
        json.dump(d, open(USAGE_FILE, "w"))
    except Exception:
        pass


REPORT_DIR = os.path.join(BASE_DIR, "data")


def _map_ssb(items):
    return [{"id": r.get("projectId"), "name": r.get("projectName"),
             "district": r.get("districtName") or "未知", "online": r.get("onlineFlatNum") or 0,
             "total": r.get("totalFlatNum") or 0, "rent_low": r.get("rentLow"), "rent_high": r.get("rentHigh"),
             "addr": r.get("projectLocation"), "tel": r.get("projectTel"),
             "house_type": r.get("houseTypeName"), "door_type": r.get("rentDoorTypeName"),
             "supply_start": r.get("concentRateSupplyStartDay"), "supply_end": r.get("concentRateSupplyEndDay"),
             "accept_start": r.get("concentRateAcceptStartDay"), "accept_end": r.get("concentRateAcceptEndDay"),
             "intro": r.get("projectIntroduction")} for r in (items or [])]


def _map_pd(items):
    return [{"id": r.get("projectId"), "name": r.get("villageProjectName"), "district": "浦东新区",
             "kzts": r.get("kzts") or 0, "status": r.get("projectStatusName"), "addr": r.get("LOCATION"),
             "tel": r.get("lxdh"), "price": r.get("price_range"), "metro": r.get("metro_subway") or [],
             "zone": r.get("zoneName"), "supply_date": r.get("supplyDate"), "release_time": r.get("releaseTime"),
             "fylx": r.get("xmfyzts") or []} for r in (items or [])]


def _map_notice(items):
    return [{"id": r.get("noticeId"), "name": r.get("projectName"), "addr": r.get("projectAddress"),
             "rent": r.get("planRentLevel"), "supply_date": r.get("planSupplyDate"), "tel": r.get("contact"),
             "org": r.get("orgName"), "intro": r.get("introduction")} for r in (items or [])]


def write_report(cur, pd, notice, daily=False):
    try:
        snap = {"date": now_bj().strftime("%Y-%m-%d"), "generated_at": now_bj().isoformat(timespec="seconds"),
                "ssb": _map_ssb(cur), "pd": _map_pd(pd), "notice": _map_notice(notice)}
        os.makedirs(REPORT_DIR, exist_ok=True)
        json.dump(snap, open(os.path.join(REPORT_DIR, "current.json"), "w"), ensure_ascii=False)
        if daily:
            json.dump(snap, open(os.path.join(REPORT_DIR, snap["date"] + ".json"), "w"), ensure_ascii=False, indent=1)
        print(f"已更新报表：随申办 {len(snap['ssb'])} / 明珠 {len(snap['pd'])} / 预告 {len(snap['notice'])}")
    except Exception as e:
        print("写报表失败：", repr(e))


def in_quiet_hours():
    h = now_bj().hour
    return QUIET_START <= h < QUIET_END


def send_wecom(text):
    try:
        r = requests.post(WEBHOOK, json={"msgtype": "text", "text": {"content": text}}, timeout=15)
        print("WeCom响应:", r.text[:200])
    except Exception as e:
        print("WeCom推送异常:", repr(e))


def send_serverchan(text):
    lines = text.splitlines()
    title = (lines[0] if lines else "房源监控")[:32].strip() or "房源监控"
    key = SERVERCHAN_KEY
    if key.startswith("sctp"):
        m = re.match(r"sctp(\d+)t", key)
        if not m:
            print("Server酱 SendKey 格式错误")
            return
        url = f"https://{m.group(1)}.push.ft07.com/send/{key}.send"
    else:
        url = f"https://sctapi.ftqq.com/{key}.send"
    try:
        r = requests.post(url, data={"title": title, "desp": text}, timeout=15)
        print("Server酱响应:", r.text[:200])
    except Exception as e:
        print("Server酱推送失败：", repr(e))


def push(text, heartbeat=False):
    if SUPPRESS_PUSH:
        print("[静默-不推送] " + text.splitlines()[0][:60])
        return
    sent = False
    if WEBHOOK:
        send_wecom(text)
        sent = True
    if SERVERCHAN_KEY and (not heartbeat or SERVERCHAN_HEARTBEAT):
        send_serverchan(text)
        sent = True
    if not sent:
        print("[no channel] " + text)


def diff(state, cur):
    cur_map = {str(it["projectId"]): it for it in cur}
    old = project_items(state)
    new, inc, dec, gone, renamed = [], [], [], [], []
    for pid, it in cur_map.items():
        if pid in IGNORE:
            continue
        online = it.get("onlineFlatNum") or 0
        prev = old.get(pid)
        if prev is None:
            new.append((it, None, online))
        else:
            po = prev.get("online", 0)
            if online > po:
                inc.append((it, po, online))
            elif online < po:
                dec.append((it, po, online))
            oldname = prev.get("name")
            if oldname and (it.get("projectName") or "") != oldname:
                renamed.append((it, oldname))
    for pid, prev in old.items():
        if pid in IGNORE:
            continue
        if pid not in cur_map:
            gone.append(prev)
    return new, inc, dec, gone, renamed


def update_state(state, cur):
    for k in list(state.keys()):
        if not str(k).startswith("__"):
            del state[k]
    for it in cur:
        state[str(it["projectId"])] = {
            "online": it.get("onlineFlatNum") or 0,
            "total": it.get("totalFlatNum") or 0,
            "name": it.get("projectName"),
        }


def pd_diff(state, cur):
    old = state.get(PD_PROJECTS_KEY, {})
    cur_map = {str(it["projectId"]): it for it in cur}
    new, gone, renamed = [], [], []
    for pid, it in cur_map.items():
        if pid not in old:
            new.append(it)
        else:
            oldname = old[pid].get("name")
            if oldname and (it.get("villageProjectName") or "") != oldname:
                renamed.append((it, oldname))
    for pid, prev in old.items():
        if pid not in cur_map:
            gone.append(prev)
    return new, gone, renamed


def pd_update(state, cur):
    d = {}
    for it in cur:
        d[str(it["projectId"])] = {
            "name": it.get("villageProjectName"),
            "location": it.get("LOCATION"),
            "phone": it.get("lxdh"),
            "status": it.get("projectStatusName"),
            "kzts": it.get("kzts") or 0,
        }
    state[PD_PROJECTS_KEY] = d


def section(title, lines):
    if not lines:
        return ""
    return f"\n━━ {title} ━━\n" + "\n".join(lines) + "\n"


def sb_change_lines(new, inc, dec, gone, renamed):
    lines = []
    kw_new = [it for it, _, _ in new if is_keyword(it.get("projectName"))]
    if kw_new:
        lines.append("🔔 关键字新房源（含 " + "/".join(
            sorted({k for it in kw_new for k in match_keyword(it.get('projectName'))})) + "）：")
        for it in kw_new:
            lines.append(f"⭐ {it['projectName']}：在线 {it.get('onlineFlatNum')} 套（共 {it.get('totalFlatNum')}）")
    if new:
        lines.append(f"🆕 新增项目（{len(new)}）")
        for it, _, now in new:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：在线 {now} 套")
    if inc:
        lines.append(f"➕ 房源增加（{len(inc)}）")
        for it, po, now in inc:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：{po} → {now}")
    if dec:
        lines.append(f"➖ 房源减少（{len(dec)}）")
        for it, po, now in dec:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：{po} → {now}")
    if renamed:
        lines.append(f"✏️ 项目改名（{len(renamed)}）")
        for it, oldname in renamed:
            lines.append(f"{star(it['projectName'])} {oldname} → {it['projectName']}")
    if gone:
        lines.append(f"❌ 下架/消失（{len(gone)}）")
        for prev in gone:
            lines.append(f"・ {prev.get('name')}")
    return lines


def sb_heartbeat_lines(cur):
    total_online = sum((it.get("onlineFlatNum") or 0) for it in cur)
    hits = [it for it in cur if is_keyword(it.get("projectName"))]
    lines = [f"项目数：{len(cur)} 个 ｜ 在线房源：{total_online} 套", "关键字："]
    if hits:
        for it in sorted(hits, key=lambda x: -(x.get("onlineFlatNum") or 0)):
            tag = "（已忽略）" if str(it["projectId"]) in IGNORE else ""
            lines.append(f"⭐ {it['projectName']}：{it.get('onlineFlatNum')} 套{tag}")
    else:
        lines.append("  （暂无命中）")
    return lines


def pd_change_lines(new, gone, renamed):
    lines = []
    if new:
        lines.append(f"🆕 新增房源（{len(new)}）")
        for it in new:
            lines.append(f"・ {it.get('villageProjectName')}")
            lines.append(f"   地址：{it.get('LOCATION')}")
            lines.append(f"   电话：{it.get('lxdh')}")
            lines.append(f"   状态：{it.get('projectStatusName')}，可租 {it.get('kzts')} 套")
    if renamed:
        lines.append(f"✏️ 项目改名（{len(renamed)}）")
        for it, oldname in renamed:
            lines.append(f"・ {oldname} → {it.get('villageProjectName')}")
            lines.append(f"   地址：{it.get('LOCATION')}")
            lines.append(f"   电话：{it.get('lxdh')}")
    if gone:
        lines.append(f"➖ 减少房源（{len(gone)}）")
        for prev in gone:
            lines.append(f"・ {prev.get('name')}")
            lines.append(f"   地址：{prev.get('location')}")
            lines.append(f"   电话：{prev.get('phone')}")
    return lines


def pd_heartbeat_lines(pd):
    return [f"房源项目数：{len(pd)} 个"]


def notice_diff(state, cur):
    old = state.get(NOTICE_KEY, {})
    cur_map = {str(n["noticeId"]): n for n in cur}
    new = [n for pid, n in cur_map.items() if pid not in old]
    removed = [old[pid] for pid in old if pid not in cur_map]
    return new, removed


def notice_update(state, cur):
    state[NOTICE_KEY] = {str(n["noticeId"]): {
        "name": n.get("projectName"),
        "supplyDate": n.get("planSupplyDate"),
        "address": n.get("projectAddress"),
        "rent": n.get("planRentLevel"),
        "contact": n.get("contact"),
    } for n in cur}


def notice_change_lines(new, removed):
    lines = []
    if new:
        lines.append(f"📢 新增供应预告（{len(new)}）")
        for n in new:
            lines.append(f"・ {n.get('projectName')}")
            lines.append(f"   地址：{n.get('projectAddress')}")
            lines.append(f"   计划供应日：{n.get('planSupplyDate')}｜租金：{n.get('planRentLevel')}")
            lines.append(f"   电话：{n.get('contact')}")
    if removed:
        lines.append(f"➖ 预告移除（{len(removed)}）")
        for prev in removed:
            lines.append(f"・ {prev.get('name')}")
    return lines


def notice_heartbeat_lines(cur):
    lines = [f"供应预告：{len(cur)} 条"]
    for n in sorted(cur, key=lambda x: str(x.get("planSupplyDate") or "")):
        lines.append(f"・ {n.get('projectName')}｜{n.get('planSupplyDate')}｜{n.get('projectAddress')}")
    return lines


def notify_err(state, key, text):
    if state.get(key) != text:
        push(text)
        state[key] = text
        save_state(state)


def clear_err(state, key):
    return state.pop(key, None) is not None


def run_once(report=False):
    global SUPPRESS_PUSH
    state = load_state()
    bj = now_bj()
    SUPPRESS_PUSH = in_quiet_hours() and not FORCE_HEARTBEAT

    cur_all = None
    try:
        cur_all = fetch_all()
    except RateLimitError as e:
        print("随申办限流：", e)
        notify_err(state, ERR_SB, "⚠️ 随申办当日查询次数已用完（每日上限），将于次日 00:00 恢复；监控在此期间无法更新。")
    except AuthError as e:
        print("随申办 Cookie 失效：", e)
        notify_err(state, ERR_SB, "⚠️ 随申办登录信息已失效，请重新登录随申办抓取新的 Cookie 并更新 Secret「SSB_COOKIE」。")
    except Exception as e:
        print("随申办抓取失败：", repr(e))
        notify_err(state, ERR_SB, f"⚠️ 随申办获取数据失败：{type(e).__name__}: {e}")

    pd = None
    pd_configured = bool(PD_USER or PD_COOKIE)
    if pd_configured:
        try:
            pd = fetch_pd(state)
        except PdAuthError as e:
            print("明珠在线会话失效且自动登录失败：", e)
            notify_err(state, ERR_PD, "⚠️ 明珠在线自动登录失败（会话过期且验证码未识别），请检查账号密码 Secret「PD_USER」「PD_PASS」。")
        except Exception as e:
            print("明珠在线抓取失败：", repr(e))
            notify_err(state, ERR_PD, f"⚠️ 明珠在线获取数据失败：{type(e).__name__}: {e}")

    notice = None
    if cur_all is not None:
        try:
            notice = fetch_notice()
        except Exception as e:
            print("预告抓取失败：", repr(e))

    recovered = False
    if cur_all is not None and clear_err(state, ERR_SB):
        recovered = True
    if pd_configured and pd is not None and clear_err(state, ERR_PD):
        recovered = True
    if recovered:
        push("✅ 监控已恢复正常。")

    kw_cur = [x for x in cur_all if is_keyword(x.get("projectName"))] if cur_all is not None else None

    scope = f"kw:{DISTRICT_ID}"
    if state.get(SCOPE_KEY) != scope:
        for k in list(state.keys()):
            if not str(k).startswith("__"):
                del state[k]

    sb_baseline = not project_items(state)
    pd_baseline = not state.get(PD_PROJECTS_KEY)
    notice_baseline = not state.get(NOTICE_KEY)

    if FORCE_HEARTBEAT:
        lines = ["【房源监控 · 测试心跳】", f"时间：{bj.strftime('%Y-%m-%d %H:%M')}"]
        if cur_all:
            lines += [section(f"随申办（{DISTRICT_NAME}·关键字）", sb_heartbeat_lines(kw_cur or []))]
            if notice:
                lines += [section("随申办·供应预告", notice_heartbeat_lines(notice))]
            if pd:
                lines += [section("明珠在线", pd_heartbeat_lines(pd))]
        else:
            lines = ["【房源监控 · 测试心跳】无数据（可能登录失效）"]
        push("\n".join(lines))
        if kw_cur is not None:
            update_state(state, kw_cur)
        if notice is not None:
            notice_update(state, notice)
        if pd is not None:
            pd_update(state, pd)
        state[SCOPE_KEY] = scope
        save_state(state)
        print("已按测试开关强制发送心跳")
        return

    change_sections = ""
    if kw_cur is not None:
        if not sb_baseline:
            sb_lines = sb_change_lines(*diff(state, kw_cur))
            change_sections += section(f"随申办（{DISTRICT_NAME}·关键字）", sb_lines)
        update_state(state, kw_cur)

    if notice is not None:
        if not notice_baseline:
            new_n, removed_n = notice_diff(state, notice)
            change_sections += section("随申办·供应预告", notice_change_lines(new_n, removed_n))
        notice_update(state, notice)

    if pd is not None:
        if not pd_baseline:
            new, gone, renamed = pd_diff(state, pd)
            pd_lines = pd_change_lines(new, gone, renamed)
            change_sections += section("明珠在线", pd_lines)
        pd_update(state, pd)

    if change_sections:
        push("【房源监控 · 变动】" + change_sections)
        print("已推送变动")
    elif sb_baseline and pd_baseline:
        print("首次运行，建立基线")

    stamp = bj.strftime("%Y-%m-%d %H")
    if bj.hour in HEARTBEAT_HOURS and state.get(HEARTBEAT_KEY) != stamp:
        lines = ["【房源监控 · 定时心跳】", f"时间：{bj.strftime('%Y-%m-%d %H:%M')}"]
        if kw_cur:
            lines += [section(f"随申办（{DISTRICT_NAME}·关键字）", sb_heartbeat_lines(kw_cur))]
        if notice:
            lines += [section("随申办·供应预告", notice_heartbeat_lines(notice))]
        if pd:
            lines += [section("明珠在线", pd_heartbeat_lines(pd))]
        if kw_cur or pd or notice:
            push("\n".join(lines), heartbeat=True)
            state[HEARTBEAT_KEY] = stamp
            print("整点心跳已推送:", stamp)

    state[SCOPE_KEY] = scope
    save_state(state)

    if report:
        write_report(cur_all, pd, notice, daily=(bj.hour == 12))


SCHED20_HOURS = set(range(8, 20))
SCHED_POINT_HOURS = {20, 21, 22, 0}


def is_scheduled(bj):
    if bj.hour in SCHED20_HOURS and bj.minute in (0, 20, 40):
        return True
    if bj.hour in SCHED_POINT_HOURS and bj.minute == 0:
        return True
    return False


def run_loop():
    last = None
    while True:
        try:
            bj = now_bj()
            key = bj.strftime("%Y-%m-%d %H:%M")
            if key != last and is_scheduled(bj):
                last = key
                run_once(report=(bj.minute == 0))
                print(bj.strftime("%Y-%m-%d %H:%M:%S"), "本轮完成", flush=True)
        except Exception as e:
            print("循环异常：", repr(e))
        time.sleep(20)


def main():
    if not COOKIE:
        print("错误：未设置环境变量 SSB_COOKIE")
        sys.exit(1)
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()


if __name__ == "__main__":
    main()
