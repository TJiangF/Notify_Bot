import os
import sys
import json
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import report  # noqa: E402
import config as cfgmod  # noqa: E402

ADMIN_PATH = os.environ.get("SSB_ADMIN_PATH", "/admin")
ADMIN_PW = os.environ.get("SSB_ADMIN_PASSWORD", "change-me")
SECRET = os.environ.get("SSB_WEB_SECRET", "please-change-this")
AUTO_REFRESH = int(os.environ.get("SSB_REFRESH_SEC", "1800"))
BJ = timezone(timedelta(hours=8))

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET)


def pick_default_base(snaps, days):
    today = datetime.now(BJ).date()
    target = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    dates = [s["date"] for s in snaps]
    if target in dates:
        return target
    earlier = [d for d in dates if d < today.strftime("%Y-%m-%d")]
    return earlier[-1] if earlier else dates[-1]


@app.get("/", response_class=HTMLResponse)
def index(base: str = Query(None)):
    cur = report.load_current()
    snaps = report.load_snapshots()
    if not snaps:
        return HTMLResponse("<h3>暂无数据，等待首次刷新…</h3>")
    options = [(s["date"], s["date"] + " 12:00") for s in sorted(snaps, key=lambda x: x["date"], reverse=True)]
    cfg = cfgmod.load()
    valid = {b for b, _ in options}
    sel = base if (base in valid) else pick_default_base(snaps, int(cfg.get("default_base_days", 1)))
    prev = next((s for s in snaps if s["date"] == sel), snaps[-1])
    html = report.render_html(
        cur, prev, snaps,
        base_options=options, selected_base=sel,
        cur_label=report.fmt_dt(cur.get("generated_at", "")),
        base_label=sel + " 12:00",
        auto_refresh=AUTO_REFRESH,
    )
    return HTMLResponse(html)


def _admin_page(request, msg="", err=""):
    cfg = cfgmod.load()
    logged = request.session.get("admin")
    if not logged:
        return HTMLResponse(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>管理登录</title>
<style>body{{font-family:-apple-system,"PingFang SC",sans-serif;background:#f5f6f8}}
.box{{max-width:340px;margin:80px auto;background:#fff;padding:24px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
input{{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}}
button{{padding:8px 14px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer}}
.err{{color:#dc2626;margin:8px 0}}</style></head><body>
<div class="box"><h3>管理登录</h3>{('<div class=err>'+err+'</div>') if err else ''}
<form method=post action="{ADMIN_PATH}/login"><p><input type=password name=pw placeholder=管理密码></p>
<p><button>登录</button></p></form></div></body></html>""")

    hours = ",".join(str(h) for h in cfg.get("heartbeat_hours", []))
    ignore = json.dumps(cfg.get("ignore", {}), ensure_ascii=False, indent=1)
    keywords = ",".join(cfg.get("keywords", []))
    return HTMLResponse(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>管理配置</title>
<style>body{{font-family:-apple-system,"PingFang SC",sans-serif;background:#f5f6f8;margin:0}}
.wrap{{max-width:640px;margin:24px auto;background:#fff;padding:22px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
label{{display:block;font-size:13px;color:#555;margin:12px 0 4px}}
input,textarea{{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box;font-size:14px}}
button{{padding:9px 16px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer;margin-top:16px}}
.ok{{color:#1a8f43;margin:8px 0}}</style></head><body><div class="wrap">
<h2>监控 / 推送配置</h2>{('<div class=ok>'+msg+'</div>') if msg else ''}
<form method=post action="{ADMIN_PATH}/save">
<label>企业微信 Webhook</label><input name=wecom_webhook value="{cfg.get('wecom_webhook','')}">
<label>Server酱 SendKey</label><input name=serverchan_key value="{cfg.get('serverchan_key','')}">
<label>关键字（逗号分隔）</label><input name=keywords value="{keywords}">
<label>忽略名单（JSON：项目ID→名称）</label><textarea name=ignore rows=4>{ignore}</textarea>
<label>监控区 ID / 名称</label>
<div style="display:flex;gap:8px"><input name=district_id value="{cfg.get('district_id','')}"><input name=district_name value="{cfg.get('district_name','')}"></div>
<label>心跳小时（逗号分隔，24小时制）</label><input name=heartbeat_hours value="{hours}">
<label>夜间静默起止（小时）</label>
<div style="display:flex;gap:8px"><input name=quiet_start value="{cfg.get('quiet_start',0)}"><input name=quiet_end value="{cfg.get('quiet_end',8)}"></div>
<label>报表默认基线（几天前）</label><input name=default_base_days value="{cfg.get('default_base_days',1)}">
<div><button>保存</button> <a href="{ADMIN_PATH}/logout" style="margin-left:12px;font-size:13px">退出</a></div>
</form></div></body></html>""")


@app.get(ADMIN_PATH, response_class=HTMLResponse)
def admin(request: Request):
    return _admin_page(request)


@app.post(ADMIN_PATH + "/login")
def admin_login(request: Request, pw: str = Form("")):
    if pw == ADMIN_PW:
        request.session["admin"] = True
        return RedirectResponse(ADMIN_PATH, status_code=303)
    return _admin_page(request, err="密码错误")


@app.get(ADMIN_PATH + "/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(ADMIN_PATH, status_code=303)


@app.post(ADMIN_PATH + "/save")
def admin_save(request: Request, wecom_webhook: str = Form(""), serverchan_key: str = Form(""),
               keywords: str = Form(""), ignore: str = Form("{}"), district_id: str = Form("14"),
               district_name: str = Form("浦东新区"), heartbeat_hours: str = Form(""),
               quiet_start: str = Form("0"), quiet_end: str = Form("8"), default_base_days: str = Form("1")):
    if not request.session.get("admin"):
        return RedirectResponse(ADMIN_PATH, status_code=303)
    try:
        ig = json.loads(ignore) if ignore.strip() else {}
    except Exception:
        ig = {}
    try:
        hh = [int(x) for x in heartbeat_hours.split(",") if x.strip() != ""]
    except Exception:
        hh = cfgmod.DEFAULTS["heartbeat_hours"]
    cfg = {
        "wecom_webhook": wecom_webhook.strip(),
        "serverchan_key": serverchan_key.strip(),
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
        "ignore": ig,
        "district_id": district_id.strip() or "14",
        "district_name": district_name.strip() or "浦东新区",
        "heartbeat_hours": hh,
        "quiet_start": int(quiet_start or 0),
        "quiet_end": int(quiet_end or 8),
        "default_base_days": int(default_base_days or 1),
    }
    cfgmod.save(cfg)
    return _admin_page(request, msg="已保存，监控将在下一轮（≤5 分钟）生效")
