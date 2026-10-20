import os
import sys
import json
import uuid
import math
import html
import threading
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import report  # noqa: E402
import config as cfgmod  # noqa: E402
import geocode  # noqa: E402

ADMIN_PATH = os.environ.get("SSB_ADMIN_PATH", "/admin")
ADMIN_PW = os.environ.get("SSB_ADMIN_PASSWORD", "change-me")
SECRET = os.environ.get("SSB_WEB_SECRET", "please-change-this")
AUTO_REFRESH = int(os.environ.get("SSB_REFRESH_SEC", "3600"))
BJ = timezone(timedelta(hours=8))
DATA_DIR = os.path.join(BASE, "data")
VISITS_FILE = os.path.join(DATA_DIR, "visits.json")
USAGE_SB = os.path.join(DATA_DIR, "usage.json")
USAGE_PD = os.path.join(DATA_DIR, "usage_pd.json")
GEO_RATE_FILE = os.path.join(DATA_DIR, "georate.json")
GEO_DAILY_LIMIT = int(os.environ.get("GEO_DAILY_LIMIT", "100"))
_RATE_LOCK = threading.Lock()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET)

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
COMMENTS_FILE = os.path.join(DATA_DIR, "comments.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def load_comments():
    if os.path.exists(COMMENTS_FILE):
        try:
            return json.load(open(COMMENTS_FILE))
        except Exception:
            return {}
    return {}


def save_comments(d):
    try:
        json.dump(d, open(COMMENTS_FILE, "w"), ensure_ascii=False)
    except Exception:
        pass


@app.get("/api/comments")
def api_comments(key: str = ""):
    return load_comments().get(key, [])


def _hav_m(a, b):
    R = 6371000.0
    lat1, lng1 = math.radians(a["lat"]), math.radians(a["lng"])
    lat2, lng2 = math.radians(b["lat"]), math.radians(b["lng"])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return int(2 * R * math.asin(math.sqrt(h)))


def _client_ip(request):
    xr = request.headers.get("x-real-ip", "")
    if xr:
        return xr.strip()
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _rate_take(ip):
    """该 IP 今日计数 +1；超限返回 False"""
    today = datetime.now(BJ).strftime("%Y-%m-%d")
    with _RATE_LOCK:
        d = {}
        if os.path.exists(GEO_RATE_FILE):
            try:
                d = json.load(open(GEO_RATE_FILE))
            except Exception:
                d = {}
        if d.get("date") != today:
            d = {"date": today, "ips": {}}
        ips = d.setdefault("ips", {})
        n = int(ips.get(ip, 0))
        if n >= GEO_DAILY_LIMIT:
            return False
        ips[ip] = n + 1
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            json.dump(d, open(GEO_RATE_FILE, "w"), ensure_ascii=False)
        except Exception:
            pass
        return True


def _rate_msg():
    return f"今日使用次数过多（每个 IP 每天 {GEO_DAILY_LIMIT} 次），请明天再试"


@app.get("/api/geosuggest")
def api_geosuggest(request: Request, q: str = ""):
    if not _rate_take(_client_ip(request)):
        return {"ok": False, "msg": _rate_msg(), "items": []}
    return {"ok": True, "items": geocode.suggest(q)}


@app.get("/api/nearby")
def api_nearby(request: Request, q: str = "", n: int = 10, lng: float = 0.0, lat: float = 0.0):
    if not _rate_take(_client_ip(request)):
        return {"ok": False, "msg": _rate_msg()}
    q = (q or "").strip()
    if lng and lat:
        origin = {"lng": lng, "lat": lat}
    elif q:
        tips = geocode.suggest(q)
        if tips:
            origin = {"lng": tips[0]["lng"], "lat": tips[0]["lat"]}
        else:
            origin = geocode.geocode(q)
    else:
        return {"ok": False, "msg": "请输入地址"}
    if not origin:
        return {"ok": False, "msg": "地址解析失败，换个更常见的地址试试"}
    cur = report.load_current()
    houses = []

    def add(items, src, valkey, rentf):
        for x in items:
            c = geocode.geocode(x.get("addr"), district=x.get("district", ""))
            if not c:
                continue
            h = {"name": x.get("name"), "addr": x.get("addr"), "src": src,
                 "lng": c["lng"], "lat": c["lat"], "val": x.get(valkey) or 0,
                 "rent": rentf(x), "id": x.get("id")}
            h["dist"] = _hav_m(origin, c)
            houses.append(h)

    add(cur.get("ssb", []), "随申办", "online", lambda x: f'{x.get("rent_low")}~{x.get("rent_high")}元')
    add(cur.get("pd", []), "明珠在线", "kzts", lambda x: x.get("price") or "")
    houses.sort(key=lambda h: h["dist"])
    return {"ok": True, "origin": origin, "houses": houses[:max(1, min(int(n), 50))]}


@app.get("/api/kwcount")
def api_kwcount(w: str = ""):
    w = (w or "").strip()
    cur = report.load_current()
    items = [x for x in cur.get("ssb", []) if w and w in (x.get("name") or "")]
    return {"ok": True, "count": len(items), "online": sum((x.get("online") or 0) for x in items)}


@app.get("/api/kwitems")
def api_kwitems(w: str = ""):
    w = (w or "").strip()
    cur = report.load_current()
    ign = cfgmod.load().get("ignore", {}) or {}
    items = []
    for x in cur.get("ssb", []):
        if w and w in (x.get("name") or ""):
            pid = str(x.get("id"))
            items.append({"id": pid, "name": x.get("name"), "online": x.get("online") or 0,
                          "ignored": pid in ign})
    items.sort(key=lambda a: -(a.get("online") or 0))
    return {"ok": True, "count": len(items), "items": items}


@app.post("/api/comment")
async def api_comment(key: str = Form(...), text: str = Form(""), images: list[UploadFile] = File(default=[])):
    text = (text or "").strip()
    imgs = []
    for uf in (images or []):
        if not uf or not getattr(uf, "filename", ""):
            continue
        ext = os.path.splitext(uf.filename)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            ext = ".jpg"
        try:
            data = await uf.read()
        except Exception:
            continue
        if not data or len(data) > 8 * 1024 * 1024:
            continue
        name = uuid.uuid4().hex + ext
        with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
            f.write(data)
        imgs.append(name)
    if not text and not imgs:
        return {"ok": False, "msg": "请输入文字或选择图片"}
    c = load_comments()
    c.setdefault(key, []).append({"time": _now().strftime("%Y-%m-%d %H:%M"), "text": text[:2000], "images": imgs})
    save_comments(c)
    return {"ok": True}


def _now():
    return datetime.now(BJ)


def bump_visit(ip):
    today = _now().strftime("%Y-%m-%d")
    d = {}
    if os.path.exists(VISITS_FILE):
        try:
            d = json.load(open(VISITS_FILE))
        except Exception:
            d = {}
    d["total"] = int(d.get("total", 0)) + 1
    d.setdefault("days", {})
    d["days"][today] = int(d["days"].get(today, 0)) + 1
    d.setdefault("ip", {})
    d["ip"][ip] = int(d["ip"].get(ip, 0)) + 1
    d.setdefault("ip_days", {}).setdefault(today, {})
    d["ip_days"][today][ip] = int(d["ip_days"][today].get(ip, 0)) + 1
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        json.dump(d, open(VISITS_FILE, "w"))
    except Exception:
        pass


def visit_stats():
    d = {}
    if os.path.exists(VISITS_FILE):
        try:
            d = json.load(open(VISITS_FILE))
        except Exception:
            d = {}
    today = _now().strftime("%Y-%m-%d")
    today_map = d.get("ip_days", {}).get(today, {})
    ips = sorted(today_map.items(), key=lambda x: -x[1])
    return int(d.get("total", 0)), int(d.get("days", {}).get(today, 0)), len(today_map), ips


def read_usage(path):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            return {}
    return {}


def schedule_times(cfg):
    step = int(cfg.get("sched_step", 20)) or 20
    out = []
    for h in range(24):
        m = 0
        while m < 60:
            out.append(f"{h:02d}:{m:02d}")
            m += step
    return out


@app.get("/", response_class=HTMLResponse)
def index(request: Request, base: str = Query(None)):
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    bump_visit(ip)
    cur = report.load_current()
    snaps = report.load_snapshots()
    if not snaps:
        return HTMLResponse("<h3>暂无数据，等待首次刷新…</h3>")
    options = [(s["date"], s["date"] + " 12:00") for s in sorted(snaps, key=lambda x: x["date"], reverse=True)]
    cfg = cfgmod.load()
    valid = {b for b, _ in options}
    sel = base if (base in valid) else _pick_base(snaps, int(cfg.get("default_base_days", 1)))
    prev = next((s for s in snaps if s["date"] == sel), snaps[-1])
    html = report.render_html(
        cur, prev, snaps,
        base_options=options, selected_base=sel,
        cur_label=report.fmt_dt(cur.get("generated_at", "")),
        base_label=sel + " 12:00",
        auto_refresh=AUTO_REFRESH,
    )
    return HTMLResponse(html)


def _pick_base(snaps, days):
    today = _now().date()
    target = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    dates = [s["date"] for s in snaps]
    if target in dates:
        return target
    earlier = [d for d in dates if d < today.strftime("%Y-%m-%d")]
    return earlier[-1] if earlier else dates[-1]


ADMIN_CSS = """
*{box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#eef1f5;color:#1f2733;margin:0}
.top{background:#0f172a;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
.top h1{font-size:16px;margin:0;font-weight:600}
.top a{color:#9db4d0;text-decoration:none;font-size:13px}
.wrap{max-width:1080px;margin:0 auto;padding:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:22px}
.card{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,.06),0 1px 2px rgba(16,24,40,.04)}
.card .k{font-size:12px;color:#8794a8;margin-bottom:6px}
.card .v{font-size:26px;font-weight:700;line-height:1.1}
.card .s{font-size:12px;color:#8794a8;margin-top:4px}
.card .v small{font-size:13px;font-weight:400;color:#8794a8}
section{background:#fff;border-radius:12px;padding:6px 20px 18px;margin-bottom:20px;box-shadow:0 1px 3px rgba(16,24,40,.06)}
h2{font-size:14px;margin:16px 0 10px;color:#334155;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eef1f5}
th{color:#8794a8;font-weight:600}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;background:#eef4fd;color:#2563eb;margin:2px 4px 2px 0;font-family:ui-monospace,Menlo,monospace}
.tag.point{background:#fef3e8;color:#c2720b}
label.f{display:block;font-size:12px;color:#8794a8;margin:12px 0 4px}
input,textarea,select{width:100%;padding:8px 10px;border:1px solid #d5dbe3;border-radius:8px;font-size:14px;background:#fff}
textarea{font-family:ui-monospace,Menlo,monospace;font-size:13px}
.row{display:flex;gap:14px}.row>div{flex:1}
button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:9px 18px;font-size:14px;cursor:pointer}
button:hover{background:#1d4ed8}
 .ok{background:#e8f7ee;color:#1a8f43;border-radius:8px;padding:8px 12px;font-size:13px;margin:10px 0}
 .muted{color:#8794a8;font-size:13px}
 .chk{display:inline-flex;align-items:center;gap:6px;font-size:14px;margin:4px 14px 4px 0;cursor:pointer}
 .chk input{width:auto;margin:0}
 .pushbox{border:1px solid #e6e8eb;border-radius:10px;padding:12px 14px;margin:10px 0;background:#fbfcfe}
 .distlist{display:flex;flex-wrap:wrap;gap:2px;margin-top:6px}
 .kwtbl{width:100%;border-collapse:collapse}
 .kwtbl th,.kwtbl td{border-bottom:1px solid #eef0f3;padding:6px;font-size:13px;text-align:center;vertical-align:middle}
 .kwtbl th{color:#666;font-weight:500}
 .kwtbl input[type=text]{padding:6px 8px;font-size:13px}
 .kwcount{font-size:12px;color:#1a8f43;white-space:nowrap}
 .kwcount.warn{color:#dc2626;font-weight:600}
 .kwitemsrow td{padding:0 6px 10px}
 .kwitems{display:flex;flex-wrap:wrap;gap:6px 10px;text-align:left}
 .kwitem{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:#475467;background:#f2f6ff;border:1px solid #e3ecff;border-radius:6px;padding:3px 8px;cursor:pointer;white-space:nowrap}
 .kwitem input{width:auto;margin:0}
 button.ghost{background:#fff;color:#2563eb;border:1px solid #bfd3ff}
 button.ghost:hover{background:#f2f6ff}
 button:disabled{opacity:.5;cursor:not-allowed}
 .f{display:block;font-size:13px;color:#475467;margin:12px 0 4px}
."""


def esc(s):
    return html.escape(str("" if s is None else s))


ADMIN_PUSH_JS = """
<script>
var KW = (window.KW_INIT || []).slice();
var IGN = {};
(function(){ var ta=document.getElementById('ignore_ta'); if(ta){ try{ IGN=JSON.parse(ta.value||'{}')||{}; }catch(e){ IGN={}; } } })();
function kwEsc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function renderKw(){
  var tb=document.getElementById('kwrows'); if(!tb) return;
  tb.innerHTML='';
  KW.forEach(function(r,i){
    var tr=document.createElement('tr');
    tr.innerHTML='<td style="text-align:left"><input type="text" class="kw" data-i="'+i+'" value="'+kwEsc(r.word)+'" placeholder="如：森兰"></td>'
      +'<td><input type="checkbox" class="kwnew" data-i="'+i+'" '+(r['new']?'checked':'')+'></td>'
      +'<td><input type="checkbox" class="kwup" data-i="'+i+'" '+(r.updown?'checked':'')+'></td>'
      +'<td><input type="checkbox" class="kwcnt" data-i="'+i+'" '+(r.count?'checked':'')+'></td>'
      +'<td><input type="checkbox" class="kwign" data-i="'+i+'" '+(r.ignore?'checked':'')+'></td>'
      +'<td><span class="kwcount" id="kwc_'+i+'">—</span></td>'
      +'<td><button type="button" class="ghost kwdel" data-i="'+i+'">删除</button></td>';
    tb.appendChild(tr);
    var tr2=document.createElement('tr'); tr2.className='kwitemsrow';
    tr2.innerHTML='<td colspan="7"><div class="kwitems" id="kwi_'+i+'"></div></td>';
    tb.appendChild(tr2);
  });
  document.getElementById('kwadd').disabled = KW.length>=10;
  KW.forEach(function(r,i){ if((r.word||'').trim()) fetchItems(i); });
}
function fetchItems(i){
  var w=(KW[i].word||'').trim(); var box=document.getElementById('kwi_'+i); var cnt=document.getElementById('kwc_'+i);
  if(!box) return;
  if(!w){ box.innerHTML=''; if(cnt){cnt.textContent='—';cnt.className='kwcount';} return; }
  fetch('/api/kwitems?w='+encodeURIComponent(w)).then(function(r){return r.json();}).then(function(d){
    var items=(d&&d.items)||[];
    if(cnt){ cnt.textContent=items.length+' 个项目'+(items.length>10?'（太宽泛，请修改）':''); cnt.className='kwcount'+(items.length>10?' warn':''); }
    if(!items.length){ box.innerHTML='<span class="muted">（暂无命中）</span>'; return; }
    box.innerHTML=items.map(function(it){
      var pid=String(it.id);
      var chk=(IGN[pid]!==undefined)?'checked':'';
      return '<label class="kwitem"><input type="checkbox" class="kwignite" data-pid="'+kwEsc(pid)+'" data-name="'+kwEsc(it.name)+'" '+chk+'> '+kwEsc(it.name)+'（'+(it.online||0)+' 套）</label>';
    }).join('');
  }).catch(function(){ if(box) box.innerHTML='<span class="muted">（加载失败）</span>'; });
}
(function(){
  var tb=document.getElementById('kwrows');
  if(tb){
    tb.addEventListener('input', function(e){
      var t=e.target; if(!t.classList.contains('kw')) return;
      var i=+t.getAttribute('data-i'); KW[i].word=t.value;
      clearTimeout(t._t); t._t=setTimeout(function(){ fetchItems(i); }, 350);
    });
    tb.addEventListener('change', function(e){
      var t=e.target; var i=+t.getAttribute('data-i');
      if(t.classList.contains('kwnew')) KW[i]['new']=t.checked;
      else if(t.classList.contains('kwup')) KW[i].updown=t.checked;
      else if(t.classList.contains('kwcnt')) KW[i].count=t.checked;
      else if(t.classList.contains('kwign')) KW[i].ignore=t.checked;
      else if(t.classList.contains('kwignite')){
        var pid=t.getAttribute('data-pid'), nm=t.getAttribute('data-name');
        if(t.checked) IGN[pid]=nm; else delete IGN[pid];
      }
    });
    tb.addEventListener('click', function(e){
      if(e.target.classList.contains('kwdel')){ KW.splice(+e.target.getAttribute('data-i'),1); renderKw(); }
    });
  }
  var add=document.getElementById('kwadd');
  if(add) add.addEventListener('click', function(){ if(KW.length<10){ KW.push({word:'',new:true,updown:true,count:true,ignore:false}); renderKw(); } });
  var form=document.querySelector('form[action$="/save"]');
  if(form) form.addEventListener('submit', function(){
    var dists=[]; document.querySelectorAll('.dist:checked').forEach(function(c){ dists.push(c.value); });
    var pj={ total_change: !!(document.getElementById('p_total')||{}).checked,
             district_change: !!(document.getElementById('p_dist')||{}).checked,
             districts: dists,
             keywords: KW.filter(function(r){return (r.word||'').trim();}).map(function(r){
               return {word:r.word.trim(), 'new':!!r['new'], updown:!!r.updown, count:!!r.count, ignore:!!r.ignore};
             }) };
    document.getElementById('push_json').value=JSON.stringify(pj);
    var ta=document.getElementById('ignore_ta'); if(ta) ta.value=JSON.stringify(IGN,null,1);
  });
  renderKw();
})();
</script>
"""



def _shell(inner, request):
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理后台</title>
<style>{ADMIN_CSS}</style></head><body>
<div class="top"><h1>房源监控 · 管理后台</h1><a href="{ADMIN_PATH}/logout">退出登录</a></div>
<div class="wrap">{inner}</div></body></html>"""


def render_login(err=""):
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理登录</title><style>{ADMIN_CSS}</style>
</head><body><div style="max-width:360px;margin:80px auto;background:#fff;padding:26px;border-radius:14px;box-shadow:0 6px 24px rgba(16,24,40,.1)">
<h1 style="font-size:17px;margin:0 0 16px">房源监控 · 管理后台</h1>
{('<div style="color:#dc2626;font-size:13px;margin-bottom:10px">'+err+'</div>') if err else ''}
<form method="post" action="{ADMIN_PATH}/login">
<label class="f">管理密码</label><input type="password" name="pw" autofocus>
<p><button style="width:100%;margin-top:16px">登录</button></p></form></div></body></html>"""


def render_dashboard(request, msg=""):
    cfg = cfgmod.load()
    total, today, uniq, ips = visit_stats()
    sb = read_usage(USAGE_SB)
    pd = read_usage(USAGE_PD)
    td = _now().strftime("%Y-%m-%d")
    sb_t = sb.get(td, {})
    pd_t = pd.get(td, {})
    times = schedule_times(cfg)
    days = sorted(set(list(sb.keys()) + list(pd.keys())), reverse=True)[:7]

    ip_rows = "".join(f"<tr><td>{ip}</td><td>{n}</td></tr>" for ip, n in ips[:20]) or '<tr><td colspan="2" class="muted">暂无</td></tr>'

    def usage_rows(data):
        rows = ""
        for d in days:
            e = data.get(d, {})
            rows += f"<tr><td>{d}</td><td>{e.get('req',0)}</td><td>{e.get('rec',0)}</td></tr>"
        return rows or '<tr><td colspan="3" class="muted">暂无</td></tr>'

    time_tags = "".join(f'<span class="tag point">{t}</span>' for t in times)
    hb = ",".join(str(h) for h in cfg.get("heartbeat_hours", []))
    extra = ",".join(str(h) for h in cfg.get("sched_extra_hours", []))
    keywords = ",".join(cfg.get("keywords", []))
    ignore = json.dumps(cfg.get("ignore", {}), ensure_ascii=False, indent=1)
    push = cfg.get("push", {}) or {}
    cur_now = report.load_current()
    districts = sorted({x.get("district") for x in cur_now.get("ssb", []) if x.get("district")})
    sel_dists = set(push.get("districts") or [])
    dist_checks = "".join(
        f'<label class="chk"><input type="checkbox" class="dist" value="{esc(d)}"{" checked" if d in sel_dists else ""}> {esc(d)}</label>'
        for d in districts)
    p_total = "checked" if push.get("total_change") else ""
    p_dist = "checked" if push.get("district_change") else ""
    kw_init = json.dumps([
        {"word": r.get("word", ""), "new": bool(r.get("new")), "updown": bool(r.get("updown")),
         "count": bool(r.get("count")), "ignore": bool(r.get("ignore"))}
        for r in (push.get("keywords") or []) if isinstance(r, dict)
    ], ensure_ascii=False)
    push_js = f'<script>var KW_INIT = {kw_init};</script>' + ADMIN_PUSH_JS

    inner = f"""
<div class="grid">
  <div class="card"><div class="k">报表今日访问</div><div class="v">{today}</div><div class="s">累计 {total} 次</div></div>
  <div class="card"><div class="k">今日独立 IP</div><div class="v">{uniq}</div></div>
  <div class="card"><div class="k">随申办 今日调用</div><div class="v">{sb_t.get('req',0)}<small> 请求</small></div><div class="s">{sb_t.get('rec',0)} 条记录</div></div>
  <div class="card"><div class="k">明珠在线 今日调用</div><div class="v">{pd_t.get('req',0)}<small> 请求</small></div><div class="s">{pd_t.get('rec',0)} 条记录</div></div>
  <div class="card"><div class="k">今日查询点位</div><div class="v">{len(times)}</div><div class="s">08:00–19:00 每 {cfg.get('sched_step',10)} 分钟 + 夜间整点</div></div>
</div>

<section>
<h2>访问统计 · 今日 IP</h2>
<table><thead><tr><th>IP</th><th>访问次数</th></tr></thead><tbody>{ip_rows}</tbody></table>
</section>

<section>
<h2>接口用量（近 7 天）</h2>
<div class="row">
<div><div class="muted" style="margin:8px 0 4px">随申办</div>
<table><thead><tr><th>日期</th><th>请求</th><th>记录</th></tr></thead><tbody>{usage_rows(sb)}</tbody></table></div>
<div><div class="muted" style="margin:8px 0 4px">明珠在线</div>
<table><thead><tr><th>日期</th><th>请求</th><th>记录</th></tr></thead><tbody>{usage_rows(pd)}</tbody></table></div>
</div>
</section>

<section>
<h2>查询策略</h2>
<div class="muted" style="margin-bottom:12px">查询与推送是分开的：查询全天 24 小时按间隔进行（夜间也跑，用于会话保活）；推送只在下面「推送策略」的心跳整点触发。</div>
<form method="post" action="{ADMIN_PATH}/save">
<div class="row">
  <div><label class="f">查询间隔（分钟）</label><input name="sched_step" value="{cfg.get('sched_step',20)}"></div>
  <div><label class="f">报表默认基线（几天前）</label><input name="default_base_days" value="{cfg.get('default_base_days',1)}"></div>
</div>
<div class="pushbox">
  <div><b>主号</b>：每次查询全部数据（翻页 + 供应预告 + 青年安居）。</div>
  <div><b>备号</b>：每次仅单次访问保活（不翻页、不取预告/青年）；主号失效时自动切换为备号全量查询。</div>
  <div class="muted" style="margin-top:8px">今日查询点位（{len(times)} 次）：</div>
  <div style="margin-top:6px">{time_tags}</div>
</div>
<input type="hidden" name="sched_start" value="{cfg.get('sched_start',8)}">
<input type="hidden" name="sched_end" value="{cfg.get('sched_end',19)}">
<input type="hidden" name="sched_extra_hours" value="{extra}">
<input type="hidden" name="district_id" value="{cfg.get('district_id','')}">
<input type="hidden" name="district_name" value="{cfg.get('district_name','全市')}">
</section>

<section>
<h2 style="margin-top:22px">推送策略</h2>
<div class="muted" style="margin-bottom:12px">推送按「心跳整点」触发：到点对比上次心跳，汇总下面「推送内容」里勾选的变动发送；异常（Cookie 失效、限流、恢复）为特殊情况即时推送。</div>
<div class="row">
  <div><label class="f">心跳整点（逗号，24 时制）</label><input name="heartbeat_hours" value="{hb}"></div>
  <div><label class="f">夜间静默起（时，不推送）</label><input name="quiet_start" value="{cfg.get('quiet_start',0)}"></div>
  <div><label class="f">夜间静默止（时）</label><input name="quiet_end" value="{cfg.get('quiet_end',8)}"></div>
</div>
<div class="muted">特殊情况（Cookie 失效 / 查询限流 / 恢复）始终即时推送，不受内容勾选影响。</div>

<h2 style="margin-top:22px">推送内容</h2>
<div class="row">
  <div><label class="f">企业微信 Webhook</label><input name="wecom_webhook" value="{cfg.get('wecom_webhook','')}"></div>
  <div><label class="f">Server酱 SendKey</label><input name="serverchan_key" value="{cfg.get('serverchan_key','')}"></div>
</div>

<div class="pushbox">
  <label class="chk"><input type="checkbox" id="p_total" {p_total}> 随申办总项目数量增减</label>
</div>

<div class="pushbox">
  <label class="chk"><input type="checkbox" id="p_dist" {p_dist}> 随申办特定行政区项目数量增减</label>
  <div class="muted" style="margin:6px 0 4px">勾选要关注的行政区（可多选）：</div>
  <div class="distlist">{dist_checks or '<span class="muted">（暂无行政区数据）</span>'}</div>
</div>

<div class="pushbox">
  <div style="font-weight:600;margin-bottom:6px">随申办特定词条房源变动（最多 10 个）</div>
  <div class="muted" style="margin-bottom:8px">每个词条可分别勾选「新增 / 上下线 / 数量变动」；下方会逐条列出当前命中的项目，可单独勾选忽略。命中超过 10 个说明词条太宽泛，建议修改。</div>
  <table class="kwtbl">
    <thead><tr><th style="text-align:left">词条</th><th>新增</th><th>上下线</th><th>数量变动</th><th>整词忽略</th><th>当前命中</th><th></th></tr></thead>
    <tbody id="kwrows"></tbody>
  </table>
  <button type="button" id="kwadd" class="ghost" style="margin-top:8px">+ 添加词条</button>
</div>

<input type="hidden" name="push_json" id="push_json">

<details style="margin-top:10px"><summary class="muted">高级：忽略名单（项目ID→名称，JSON）</summary>
<textarea name="ignore" id="ignore_ta" rows="4">{ignore}</textarea></details>
{(f'<div class="ok">{msg}</div>') if msg else ''}
<p><button>保存配置</button> <span class="muted">保存后监控下一轮生效（≤按策略点位）</span></p>
</form>
</section>
"""
    inner += push_js
    return _shell(inner, request)


@app.get(ADMIN_PATH, response_class=HTMLResponse)
def admin(request: Request):
    if not request.session.get("admin"):
        return HTMLResponse(render_login())
    return HTMLResponse(render_dashboard(request))


@app.post(ADMIN_PATH + "/login")
def admin_login(request: Request, pw: str = Form("")):
    if pw == ADMIN_PW:
        request.session["admin"] = True
        return RedirectResponse(ADMIN_PATH, status_code=303)
    return HTMLResponse(render_login("密码错误"))


@app.get(ADMIN_PATH + "/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(ADMIN_PATH, status_code=303)


@app.post(ADMIN_PATH + "/save")
def admin_save(request: Request, wecom_webhook: str = Form(""), serverchan_key: str = Form(""),
               ignore: str = Form("{}"), district_id: str = Form(""),
               district_name: str = Form("全市"), heartbeat_hours: str = Form(""),
               quiet_start: str = Form("0"), quiet_end: str = Form("8"), default_base_days: str = Form("1"),
               sched_start: str = Form("8"), sched_end: str = Form("19"), sched_extra_hours: str = Form("20,21,22,0"),
               sched_step: str = Form("10"), push_json: str = Form("")):
    if not request.session.get("admin"):
        return RedirectResponse(ADMIN_PATH, status_code=303)

    def ints(s, dflt):
        try:
            return [int(x) for x in s.split(",") if x.strip() != ""]
        except Exception:
            return dflt

    try:
        ig = json.loads(ignore) if ignore.strip() else {}
    except Exception:
        ig = {}
    old = cfgmod.load()
    if push_json.strip():
        try:
            pj = json.loads(push_json)
        except Exception:
            pj = {}
        if not isinstance(pj, dict):
            pj = {}
        rules, seen = [], set()
        for r in (pj.get("keywords") or [])[:10]:
            if not isinstance(r, dict):
                continue
            w = str(r.get("word", "")).strip()
            if not w or w in seen:
                continue
            seen.add(w)
            rules.append({"word": w, "new": bool(r.get("new")), "updown": bool(r.get("updown")),
                          "count": bool(r.get("count")), "ignore": bool(r.get("ignore"))})
        push_cfg = {
            "total_change": bool(pj.get("total_change")),
            "district_change": bool(pj.get("district_change")),
            "districts": [str(d) for d in (pj.get("districts") or []) if str(d).strip()],
            "keywords": rules,
        }
        kw_list = [r["word"] for r in rules]
    else:
        push_cfg = old.get("push", cfgmod.DEFAULTS["push"])
        kw_list = old.get("keywords", [])
    cfg = {
        "wecom_webhook": wecom_webhook.strip(),
        "serverchan_key": serverchan_key.strip(),
        "keywords": kw_list,
        "ignore": ig,
        "district_id": district_id.strip(),
        "district_name": district_name.strip() or "全市",
        "heartbeat_hours": ints(heartbeat_hours, cfgmod.DEFAULTS["heartbeat_hours"]),
        "quiet_start": int(quiet_start or 0),
        "quiet_end": int(quiet_end or 8),
        "default_base_days": int(default_base_days or 1),
        "sched_start": int(sched_start or 8),
        "sched_end": int(sched_end or 19),
        "sched_step": int(sched_step or 10),
        "sched_extra_hours": ints(sched_extra_hours, cfgmod.DEFAULTS["sched_extra_hours"]),
        "push": push_cfg,
    }
    cfgmod.save(cfg)
    return HTMLResponse(render_dashboard(request, msg="已保存，监控将在下一轮点位生效"))
