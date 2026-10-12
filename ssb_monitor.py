import os
import json
import time
import sys
import requests

API = "https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList"

WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
COOKIE = os.environ.get("SSB_COOKIE", "")
KEYWORDS = [k.strip() for k in os.environ.get("SSB_KEYWORDS", "").split(",") if k.strip()]
INTERVAL = int(os.environ.get("SSB_INTERVAL", "300"))
STATE = os.environ.get("SSB_STATE", "ssb_state.json")
PAGE_SIZE = 500
AUTH_FLAG = "__auth_failed__"

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


def fetch(keyword):
    param = {
        "districtId": "", "doorType": "", "rentHigh": "", "rentLow": "",
        "searchWord": keyword, "street": [], "supplyWay": "",
        "ringRdId": "", "orderBy": "", "isAsc": True,
    }
    out = []
    page = 1
    while True:
        data = {"params": json.dumps(
            {"pageNo": page, "pageSize": PAGE_SIZE, "param": param},
            ensure_ascii=False,
        )}
        r = requests.post(API, headers=HEADERS, data=data, timeout=20)
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


def is_baseline(state):
    return not any(not str(k).startswith("__") for k in state)


def wecom(text):
    if not WEBHOOK:
        print("[no webhook] " + text)
        return
    requests.post(
        WEBHOOK,
        json={"msgtype": "text", "text": {"content": text}},
        timeout=15,
    )


def fmt(it):
    return (
        f"项目：{it.get('projectName')}\n"
        f"地址：{it.get('projectLocation')}\n"
        f"区域：{it.get('districtName')} / {it.get('ringRdName')}\n"
        f"户型：{it.get('rentDoorTypeName')}\n"
        f"租金：{it.get('rentLow')} ~ {it.get('rentHigh')} 元\n"
        f"在线房源：{it.get('onlineFlatNum')} 套（总共 {it.get('totalFlatNum')}）\n"
        f"供应时间：{it.get('concentRateSupplyStartDay')} ~ {it.get('concentRateSupplyEndDay')}\n"
        f"电话：{it.get('projectTel')}"
    )


def check_once(state, baseline=False):
    for kw in KEYWORDS or [""]:
        for it in fetch(kw):
            pid = str(it.get("projectId"))
            online = it.get("onlineFlatNum") or 0
            prev = state.get(pid)
            if prev is None:
                state[pid] = {"online": online, "name": it.get("projectName")}
                if not baseline and os.environ.get("SSB_NOTIFY_FIRST") != "1":
                    wecom("【保障房·新项目】\n" + fmt(it))
            elif online > prev.get("online", 0):
                diff = online - prev.get("online", 0)
                state[pid]["online"] = online
                wecom(f"【保障房·房源增加 +{diff}】\n" + fmt(it))


def handle_auth_error(state):
    if not state.get(AUTH_FLAG):
        wecom("⚠️ 保障房监控 Cookie 已失效，请重新登录随申办抓取新的 Cookie 更新。")
        state[AUTH_FLAG] = True
        save_state(state)


def handle_recovered(state):
    if state.pop(AUTH_FLAG, None):
        wecom("✅ 保障房监控已恢复正常。")


def run_once():
    state = load_state()
    baseline = is_baseline(state)
    try:
        check_once(state, baseline)
        handle_recovered(state)
        save_state(state)
        print("完成一次检查，共跟踪", len(state), "个项目")
    except AuthError as e:
        print("Cookie 失效：", e)
        handle_auth_error(state)


def run_loop():
    state = load_state()
    baseline = is_baseline(state)
    wecom("保障房监控已启动，关键词：" + (", ".join(KEYWORDS) or "全部"))
    while True:
        try:
            check_once(state, baseline)
            handle_recovered(state)
            save_state(state)
            if baseline:
                print("已建立基线，共", len(state), "个项目，后续仅推送变化")
                baseline = False
            print(time.strftime("%H:%M:%S"), "检查完成，共跟踪", len(state), "个项目")
        except AuthError as e:
            print("Cookie 失效：", e)
            handle_auth_error(state)
        except Exception as e:
            print(time.strftime("%H:%M:%S"), "错误：", repr(e))
        time.sleep(INTERVAL)


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
