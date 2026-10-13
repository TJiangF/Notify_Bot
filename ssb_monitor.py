import os
import re
import json
import time
import sys
from datetime import datetime, timezone, timedelta
import requests

API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList"
PD_API = "https://pdrcgy.pudong.gov.cn/api/rcaj/fwcx/getProjectAndHouse.html"

WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_SENDKEY", "")
SERVERCHAN_HEARTBEAT = os.environ.get("SERVERCHAN_HEARTBEAT", "0").lower() in ("1", "true", "yes")

COOKIE = os.environ.get("SSB_COOKIE", "")
DISTRICT_ID = os.environ.get("SSB_DISTRICT_ID", "14")
DISTRICT_NAME = os.environ.get("SSB_DISTRICT_NAME", "浦东新区")
PD_COOKIE = os.environ.get("PD_COOKIE", "")
PD_CSRF = os.environ.get("PD_CSRF", "")

KEYWORDS = [k.strip() for k in os.environ.get(
    "SSB_KEYWORDS", "森兰,中铁,桂竹,海上,西派,海华智,万安里").split(",") if k.strip()]

STATE = os.environ.get("SSB_STATE", "ssb_state.json")
PAGE_SIZE = 500
FORCE_HEARTBEAT = os.environ.get("SSB_FORCE_HEARTBEAT", "").lower() in ("1", "true", "yes")

IGNORE = {
    "4594": "森兰星遇公寓(新展城店)",
    "3025": "城家高级公寓（森兰洲海路地铁站店）",
}

ERR_SB = "__err_sb__"
ERR_PD = "__err_pd__"
HEARTBEAT_KEY = "__last_heartbeat_hour__"
SCOPE_KEY = "__scope__"
PD_PROJECTS_KEY = "__pd_projects__"
HEARTBEAT_HOURS = set(range(8, 21)) | {22}

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
            raise AuthError(j.get("url", str(j)))
        inner = j["data"]
        if isinstance(inner, str):
            inner = json.loads(inner)
        d = inner["data"]
        out.extend(d.get("results", []))
        if page * d.get("pageSize", PAGE_SIZE) >= d.get("totalCount", 0):
            break
        page += 1
    return out


def fetch_pd():
    if not PD_COOKIE:
        return None
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
        "x-csrf-token": PD_CSRF,
        "x-requested-with": "XMLHttpRequest",
        "Cookie": PD_COOKIE,
    }
    r = requests.post(PD_API, headers=headers, json=body, timeout=25, allow_redirects=False)
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


def in_quiet_hours():
    return 0 <= now_bj().hour < 8


def send_wecom(text):
    requests.post(WEBHOOK, json={"msgtype": "text", "text": {"content": text}}, timeout=15)


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
        requests.post(url, data={"title": title, "desp": text}, timeout=15)
    except Exception as e:
        print("Server酱推送失败：", repr(e))


def push(text, heartbeat=False):
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
    new, inc, dec, gone = [], [], [], []
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
    for pid, prev in old.items():
        if pid in IGNORE:
            continue
        if pid not in cur_map:
            gone.append(prev)
    return new, inc, dec, gone


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
    new, gone, chg = [], [], []
    for pid, it in cur_map.items():
        prev = old.get(pid)
        if prev is None:
            new.append(it)
        elif is_keyword(it.get("villageProjectName")):
            changes = []
            if (it.get("projectStatusName") or "") != (prev.get("status") or ""):
                changes.append(f"状态 {prev.get('status')} → {it.get('projectStatusName')}")
            if (it.get("kzts") or 0) != (prev.get("kzts") or 0):
                changes.append(f"可租 {prev.get('kzts')} → {it.get('kzts')} 套")
            if changes:
                chg.append((it, changes))
    for pid, prev in old.items():
        if pid not in cur_map:
            gone.append(prev)
    return new, gone, chg


def pd_update(state, cur):
    d = {}
    for it in cur:
        d[str(it["projectId"])] = {
            "name": it.get("villageProjectName"),
            "status": it.get("projectStatusName"),
            "kzts": it.get("kzts") or 0,
        }
    state[PD_PROJECTS_KEY] = d


def section(title, lines):
    if not lines:
        return ""
    return f"\n━━ {title} ━━\n" + "\n".join(lines) + "\n"


def sb_change_lines(new, inc, dec, gone):
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


def pd_change_lines(new, gone, chg):
    lines = []
    kw_new = [it for it in new if is_keyword(it.get("villageProjectName"))]
    if kw_new:
        lines.append("🔔 关键字新项目：")
        for it in kw_new:
            lines.append(f"⭐ {it['villageProjectName']}：{it.get('projectStatusName')} 可租{it.get('kzts')}套")
    if new:
        lines.append(f"🆕 新增项目（{len(new)}）")
        for it in new:
            lines.append(f"{star(it.get('villageProjectName'))} {it['villageProjectName']}：{it.get('projectStatusName')} 可租{it.get('kzts')}套")
    if chg:
        lines.append(f"🔄 关键字变化（{len(chg)}）")
        for it, changes in chg:
            lines.append(f"⭐ {it['villageProjectName']}：" + "；".join(changes))
    if gone:
        lines.append(f"❌ 下架（{len(gone)}）")
        for prev in gone:
            lines.append(f"・ {prev.get('name')}")
    return lines


def pd_heartbeat_lines(pd):
    hits = [it for it in pd if is_keyword(it.get("villageProjectName"))]
    lines = [f"项目数：{len(pd)} 个", "关键字："]
    if hits:
        for it in sorted(hits, key=lambda x: -(x.get("kzts") or 0)):
            lines.append(f"⭐ {it['villageProjectName']}：【{it.get('projectStatusName')}】可租{it.get('kzts')}套")
    else:
        lines.append("  （暂无命中）")
    return lines


def notify_err(state, key, text):
    if state.get(key) != text:
        push(text)
        state[key] = text
        save_state(state)


def clear_err(state, key):
    return state.pop(key, None) is not None


def run_once():
    state = load_state()

    if in_quiet_hours() and not FORCE_HEARTBEAT:
        try:
            a = len(fetch_all())
        except Exception as e:
            a = f"失败({type(e).__name__})"
        b = "-"
        if PD_COOKIE:
            try:
                b = len(fetch_pd())
            except Exception as e:
                b = f"失败({type(e).__name__})"
        print(f"夜间静默：已保活（随申办 {a} / 人才公寓 {b}），本次不推送")
        return

    recovered = False

    cur = None
    try:
        cur = fetch_all()
    except AuthError as e:
        print("随申办 Cookie 失效：", e)
        notify_err(state, ERR_SB,
                   "⚠️ 随申办登录信息已失效，请重新登录随申办抓取新的 Cookie 并更新 Secret「SSB_COOKIE」。")
    except Exception as e:
        print("随申办抓取失败：", repr(e))
        notify_err(state, ERR_SB, f"⚠️ 随申办获取数据失败：{type(e).__name__}: {e}")

    pd = None
    pd_configured = bool(PD_COOKIE)
    if pd_configured:
        try:
            pd = fetch_pd()
        except PdAuthError as e:
            print("人才公寓会话失效：", e)
            notify_err(state, ERR_PD,
                       "⚠️ 浦东人才公寓登录信息已失效，请重新登录该网站并更新 Secret「PD_COOKIE」「PD_CSRF」。")
        except Exception as e:
            print("人才公寓抓取失败：", repr(e))
            notify_err(state, ERR_PD, f"⚠️ 浦东人才公寓获取数据失败：{type(e).__name__}: {e}")

    if cur is not None and clear_err(state, ERR_SB):
        recovered = True
    if pd_configured and pd is not None and clear_err(state, ERR_PD):
        recovered = True
    if recovered:
        push("✅ 监控已恢复正常。")

    sb_baseline = not project_items(state)
    pd_baseline = not state.get(PD_PROJECTS_KEY)

    if FORCE_HEARTBEAT:
        lines = []
        if cur:
            lines += ["【房源监控 · 测试心跳】", f"时间：{now_bj().strftime('%Y-%m-%d %H:%M')}"]
            lines += [section(f"随申办（{DISTRICT_NAME}）", sb_heartbeat_lines(cur))]
            if pd:
                lines += [section("浦东人才公寓", pd_heartbeat_lines(pd))]
        else:
            lines = ["【房源监控 · 测试心跳】无数据（可能登录失效）"]
        push("\n".join(lines))
        if cur:
            update_state(state, cur)
        if pd is not None:
            pd_update(state, pd)
        state[SCOPE_KEY] = f"district:{DISTRICT_ID}"
        save_state(state)
        print("已按测试开关强制发送心跳")
        return

    change_sections = ""
    if cur is not None:
        if not sb_baseline:
            sb_lines = sb_change_lines(*diff(state, cur))
            change_sections += section(f"随申办（{DISTRICT_NAME}）", sb_lines)
        update_state(state, cur)

    if pd is not None:
        if not pd_baseline:
            new, gone, chg = pd_diff(state, pd)
            pd_lines = pd_change_lines(new, gone, chg)
            change_sections += section("浦东人才公寓", pd_lines)
        pd_update(state, pd)

    if change_sections:
        push("【房源监控 · 变动】" + change_sections)
        print("已推送变动")
    elif sb_baseline and pd_baseline:
        print("首次运行，建立基线")

    bj = now_bj()
    stamp = bj.strftime("%Y-%m-%d %H")
    if bj.hour in HEARTBEAT_HOURS and state.get(HEARTBEAT_KEY) != stamp:
        lines = ["【房源监控 · 定时心跳】", f"时间：{bj.strftime('%Y-%m-%d %H:%M')}"]
        if cur:
            lines += [section(f"随申办（{DISTRICT_NAME}）", sb_heartbeat_lines(cur))]
        if pd:
            lines += [section("浦东人才公寓", pd_heartbeat_lines(pd))]
        if cur or pd:
            push("\n".join(lines), heartbeat=True)
            state[HEARTBEAT_KEY] = stamp
            print("整点心跳已推送:", stamp)

    state[SCOPE_KEY] = f"district:{DISTRICT_ID}"
    save_state(state)


def run_loop():
    while True:
        run_once()
        time.sleep(int(os.environ.get("SSB_INTERVAL", "300")))


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
