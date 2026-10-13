import os
import re
import json
import time
import sys
from datetime import datetime, timezone, timedelta
import requests

API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList"

WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_SENDKEY", "")
SERVERCHAN_HEARTBEAT = os.environ.get("SERVERCHAN_HEARTBEAT", "0").lower() in ("1", "true", "yes")
COOKIE = os.environ.get("SSB_COOKIE", "")
DISTRICT_ID = os.environ.get("SSB_DISTRICT_ID", "14")
DISTRICT_NAME = os.environ.get("SSB_DISTRICT_NAME", "浦东新区")
KEYWORDS = [k.strip() for k in os.environ.get(
    "SSB_KEYWORDS", "森兰,中铁,桂竹,海上,西派,海华智,万安里").split(",") if k.strip()]
STATE = os.environ.get("SSB_STATE", "ssb_state.json")
PAGE_SIZE = 500
FORCE_HEARTBEAT = os.environ.get("SSB_FORCE_HEARTBEAT", "").lower() in ("1", "true", "yes")

IGNORE = {
    "4594": "森兰星遇公寓(新展城店)",
    "3025": "城家高级公寓（森兰洲海路地铁站店）",
}

ERROR_KEY = "__last_error__"
HEARTBEAT_KEY = "__last_heartbeat_hour__"
SCOPE_KEY = "__scope__"
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
    title = (lines[0] if lines else "保障房监控")[:32].strip() or "保障房监控"
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


def build_change_msg(new, inc, dec, gone):
    kw_new = [it for it, _, _ in new if is_keyword(it.get("projectName"))]
    lines = [f"【{DISTRICT_NAME}保障房 · 变动】"]
    if kw_new:
        lines.append("🔔 关键字新房源（含 " + "/".join(
            sorted({k for it in kw_new for k in match_keyword(it.get('projectName'))})) + "）：")
        for it in kw_new:
            lines.append(f"⭐ {it['projectName']}：在线 {it.get('onlineFlatNum')} 套（共 {it.get('totalFlatNum')}）")
        lines.append("")
    if new:
        lines.append(f"🆕 新增项目（{len(new)}）")
        for it, _, now in new:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：在线 {now} 套（共 {it.get('totalFlatNum')}）")
    if inc:
        lines.append(f"➕ 房源增加（{len(inc)}）")
        for it, po, now in inc:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：{po} → {now}（+{now - po}）")
    if dec:
        lines.append(f"➖ 房源减少（{len(dec)}）")
        for it, po, now in dec:
            lines.append(f"{star(it['projectName'])} {it['projectName']}：{po} → {now}（{now - po}）")
    if gone:
        lines.append(f"❌ 下架/消失（{len(gone)}）")
        for prev in gone:
            lines.append(f"・ {prev.get('name')}（原在线 {prev.get('online')} 套）")
    return "\n".join(lines) if (new or inc or dec or gone) else None


def build_heartbeat(cur):
    total_online = sum((it.get("onlineFlatNum") or 0) for it in cur)
    hits = [it for it in cur if is_keyword(it.get("projectName"))]
    lines = [
        f"【{DISTRICT_NAME}保障房 · 定时心跳】",
        f"时间：{now_bj().strftime('%Y-%m-%d %H:%M')}",
        f"项目数：{len(cur)} 个 ｜ 在线房源：{total_online} 套",
        f"关键字：{'、'.join(KEYWORDS)}",
        "",
        "关键字房源：",
    ]
    if hits:
        for it in sorted(hits, key=lambda x: -(x.get("onlineFlatNum") or 0)):
            tag = "（已忽略）" if str(it["projectId"]) in IGNORE else ""
            lines.append(f"⭐ {it['projectName']}：{it.get('onlineFlatNum')} 套{tag}")
    else:
        lines.append("  （暂无命中）")
    return "\n".join(lines)


def notify_error(state, err_type, text):
    if state.get(ERROR_KEY) != err_type:
        push(text)
        state[ERROR_KEY] = err_type
        save_state(state)


def handle_recovered(state):
    if state.pop(ERROR_KEY, None) is not None:
        push("✅ 保障房监控已恢复正常。")


def run_once():
    if in_quiet_hours() and not FORCE_HEARTBEAT:
        try:
            n = len(fetch_all())
            print(f"夜间静默（00:00-08:00）：已保活会话，{n} 个项目，本次不推送")
        except Exception as e:
            print("夜间静默：保活请求失败", repr(e))
        return
    state = load_state()
    baseline = not project_items(state)
    try:
        cur = fetch_all()
    except AuthError as e:
        print("Cookie 失效：", e)
        notify_error(
            state, "auth",
            "⚠️ 保障房监控登录信息已失效（Cookie 过期），请重新登录随申办抓取新的 Cookie，"
            "并更新仓库 Secret「SSB_COOKIE」。",
        )
        return
    except Exception as e:
        print("抓取失败：", repr(e))
        notify_error(
            state, "fetch",
            f"⚠️ 保障房监控获取数据失败：{type(e).__name__}: {e}\n"
            f"请检查（可能是网络问题或接口变动）。",
        )
        return

    if not cur:
        print("返回空列表，跳过本轮")
        notify_error(
            state, "empty",
            "⚠️ 保障房监控返回空数据，可能接口变动或登录异常，请检查。",
        )
        return

    handle_recovered(state)

    if FORCE_HEARTBEAT:
        push(build_heartbeat(cur))
        update_state(state, cur)
        state[SCOPE_KEY] = f"district:{DISTRICT_ID}"
        save_state(state)
        print("已按测试开关强制发送心跳")
        return

    bj = now_bj()
    stamp = bj.strftime("%Y-%m-%d %H")

    if baseline:
        print("首次运行，建立基线，共", len(cur), "个项目")
    else:
        new, inc, dec, gone = diff(state, cur)
        msg = build_change_msg(new, inc, dec, gone)
        if msg:
            push(msg)
            print("已推送变动：新增", len(new), "增", len(inc), "减", len(dec), "下架", len(gone))

    if bj.hour in HEARTBEAT_HOURS and state.get(HEARTBEAT_KEY) != stamp:
        push(build_heartbeat(cur), heartbeat=True)
        state[HEARTBEAT_KEY] = stamp
        print("整点心跳已推送:", stamp)

    update_state(state, cur)
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
