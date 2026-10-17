import os
import re
import json
import glob
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "report.html")


def fmt_dt(s):
    if not s:
        return "当前"
    try:
        return datetime.fromisoformat(str(s)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(s)[:16].replace("T", " ")


def load_snapshots():
    snaps = []
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "20*.json"))):
        with open(f) as fh:
            snaps.append(json.load(fh))
    return snaps


def load_current():
    p = os.path.join(DATA_DIR, "current.json")
    if os.path.exists(p):
        with open(p) as fh:
            return json.load(fh)
    snaps = load_snapshots()
    return snaps[-1] if snaps else {"ssb": [], "pd": [], "notice": [], "date": "", "generated_at": ""}


def by_id(items):
    return {str(x["id"]): x for x in items}


def diff(prev, cur, valkey):
    p, c = by_id(prev), by_id(cur)
    new = [c[i] for i in c if i not in p]
    gone = [p[i] for i in p if i not in c]
    inc, dec, renamed = [], [], []
    for i in c:
        if i not in p:
            continue
        pv, cv = p[i].get(valkey) or 0, c[i].get(valkey) or 0
        if cv > pv:
            inc.append((c[i], pv, cv))
        elif cv < pv:
            dec.append((c[i], pv, cv))
        if p[i].get("name") and c[i].get("name") and p[i]["name"] != c[i]["name"]:
            renamed.append((c[i], p[i]["name"]))
    return new, gone, inc, dec, renamed


def district_stats(cur, changes):
    new, gone, inc, dec, _ = changes
    st = defaultdict(lambda: {"proj": 0, "online": 0, "new": 0, "gone": 0, "d": 0})
    for x in cur:
        d = x["district"]
        st[d]["proj"] += 1
        st[d]["online"] += x.get("online", x.get("kzts", 0))
    for x in new:
        st[x["district"]]["new"] += 1
    for x in gone:
        st[x["district"]]["gone"] += 1
    for x, pv, cv in inc:
        st[x["district"]]["d"] += cv - pv
    for x, pv, cv in dec:
        st[x["district"]]["d"] += cv - pv
    return st


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def dtag(v):
    if v > 0:
        return f'<span class="up">+{v}</span>'
    if v < 0:
        return f'<span class="down">{v}</span>'
    return "0"


def _fmt_card(cur, prv):
    if prv is None:
        return f"{cur}"
    d = cur - prv
    if d == 0:
        return f"{cur}"
    return f"{cur}<span class='d'>（{prv}{'+' if d > 0 else ''}{d}）</span>"


def render_html(latest, prev, snaps, base_options=None, selected_base=None,
                cur_label="当前", base_label="上一份快照", auto_refresh=0):
    ssb_ch = diff(prev["ssb"], latest["ssb"], "online")
    pd_ch = diff(prev["pd"], latest["pd"], "kzts")
    ssb_dist = district_stats(latest["ssb"], ssb_ch)
    pd_dist = district_stats(latest["pd"], pd_ch)

    notice = latest.get("notice", [])
    prev_notice_ids = {str(x.get("id")) for x in prev.get("notice", [])}
    nrows = []
    for n in sorted(notice, key=lambda a: str(a.get("supply_date") or "")):
        tag = "🆕 " if str(n.get("id")) not in prev_notice_ids else ""
        nrows.append(
            f'<tr><td>{tag}{esc(n.get("name"))}</td><td>{esc(n.get("supply_date"))}</td>'
            f'<td>{esc(n.get("rent"))}</td><td>{esc(n.get("addr"))}</td>'
            f'<td>{esc(n.get("tel"))}</td><td>{esc(n.get("org"))}</td></tr>')
    notice_table = "\n".join(nrows) or '<tr><td colspan="6">暂无预告</td></tr>'

    tot_ssb = len(latest["ssb"])
    tot_ssb_online = sum(x["online"] for x in latest["ssb"])
    tot_pd = len(latest["pd"])
    tot_pd_kzts = sum(x["kzts"] for x in latest["pd"])
    has_prev = prev is not None and ("ssb" in prev)
    p_ssb = len(prev.get("ssb", [])) if has_prev else None
    p_ssb_online = sum(x["online"] for x in prev.get("ssb", [])) if has_prev else None
    p_pd = len(prev.get("pd", [])) if has_prev else None
    p_pd_kzts = sum(x["kzts"] for x in prev.get("pd", [])) if has_prev else None
    p_notice = len(prev.get("notice", [])) if (has_prev and "notice" in prev) else None

    c_ssb = _fmt_card(tot_ssb, p_ssb)
    c_ssb_online = _fmt_card(tot_ssb_online, p_ssb_online)
    c_pd = _fmt_card(tot_pd, p_pd)
    c_pd_kzts = _fmt_card(tot_pd_kzts, p_pd_kzts)
    c_notice = _fmt_card(len(notice), p_notice)

    rows = []
    for d in sorted(ssb_dist, key=lambda k: -ssb_dist[k]["online"]):
        s = ssb_dist[d]
        rows.append(f"<tr><td>{esc(d)}</td><td>{s['proj']}</td><td>{s['online']}</td>"
                    f"<td>{('+' + str(s['new'])) if s['new'] else ''}</td>"
                    f"<td>{('-' + str(s['gone'])) if s['gone'] else ''}</td>"
                    f"<td>{dtag(s['d'])}</td></tr>")
    dist_table = "\n".join(rows)

    pd_rows = []
    for d in sorted(pd_dist):
        s = pd_dist[d]
        pd_rows.append(f"<tr><td>{esc(d)}</td><td>{s['proj']}</td><td>{s['online']}</td>"
                       f"<td>{('+' + str(s['new'])) if s['new'] else ''}</td>"
                       f"<td>{('-'+str(s['gone'])) if s['gone'] else ''}</td>"
                       f"<td>{dtag(s['d'])}</td></tr>")
    pd_table = "\n".join(pd_rows)

    def detail(source, ch):
        new, gone, inc, dec, renamed = ch
        h = []

        def grp(title, lis):
            if not lis:
                return ""
            return f'<div class="grp"><h4>{title}</h4><ul>' + "".join(lis) + "</ul></div>"

        h.append(grp(f"🆕 新增（{len(new)}）", [
            f'<li data-d="{esc(x["district"])}"><b>{esc(x["name"])}</b>（{esc(x["district"])}）　{esc(x.get("addr"))}　电话 {esc(x.get("tel"))}</li>'
            for x in new]))
        h.append(grp(f"❌ 下架（{len(gone)}）", [
            f'<li data-d="{esc(x["district"])}">{esc(x["name"])}（{esc(x["district"])}）</li>'
            for x in gone]))
        h.append(grp(f"➕ 增加（{len(inc)}）", [
            f'<li data-d="{esc(x["district"])}">{esc(x["name"])}（{esc(x["district"])}）：{pv} → <b>{cv}</b></li>'
            for x, pv, cv in inc]))
        h.append(grp(f"➖ 减少（{len(dec)}）", [
            f'<li data-d="{esc(x["district"])}">{esc(x["name"])}（{esc(x["district"])}）：{pv} → <b>{cv}</b></li>'
            for x, pv, cv in dec]))
        h.append(grp(f"✏️ 改名（{len(renamed)}）", [
            f'<li data-d="{esc(x["district"])}">{esc(old)} → <b>{esc(x["name"])}</b>（{esc(x["district"])}）</li>'
            for x, old in renamed]))
        body = "".join(h) if "".join(h) else "<p>无变动</p>"
        return f"<h3>{source}</h3>{body}"

    def all_projects(latest):
        ssb = latest["ssb"]
        htypes = sorted({x.get("house_type") for x in ssb if x.get("house_type")})
        hb_opts = "".join(f'<option value="{esc(h)}">{esc(h)}</option>' for h in htypes)
        door_opts = "".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in ["单间", "一居室", "二居室", "三居室", "多居室"])
        districts = sorted({x.get("district") for x in ssb if x.get("district")})
        dchecks = "".join(f'<label><input type="checkbox" class="sb_d" value="{esc(d)}"> {esc(d)}</label>' for d in districts)
        ssb_filter = (
            '<label>租金：<input id="sb_fmin" type="number" placeholder="最低" style="width:72px">'
            ' - <input id="sb_fmax" type="number" placeholder="最高" style="width:72px"></label>'
            f'<label>类型：<select id="sb_ftype"><option value="">全部</option>{hb_opts}</select></label>'
            f'<label>户型：<select id="sb_fdoor"><option value="">全部</option>{door_opts}</select></label>'
            '<details class="ms"><summary id="sb_dsum">行政区：全部</summary>'
            f'<div class="ms-list">{dchecks}</div></details>'
            '<button type="button" onclick="filterSb()">筛选</button>'
        )

        def dday(v):
            return str(v).split(" ")[0] if v else ""

        sitems = []
        for x in sorted(ssb, key=lambda a: -(a["online"] or 0)):
            lo, hi = x.get("rent_low"), x.get("rent_high")
            nums = [float(n) for n in (lo, hi) if isinstance(n, (int, float))]
            pmin = min(nums) if nums else 0
            pmax = max(nums) if nums else 0
            price = f"{lo} ~ {hi} 元" if (lo is not None or hi is not None) else "—"
            htype = x.get("house_type") or ""
            dts = [t.strip() for t in (x.get("door_type") or "").replace("，", "、").split("、") if t.strip()]
            door_key = "、".join(dts)
            district = x.get("district") or ""
            supply = " ~ ".join([d for d in [dday(x.get("supply_start")), dday(x.get("supply_end"))] if d]) or "—"
            accept = " ~ ".join([d for d in [dday(x.get("accept_start")), dday(x.get("accept_end"))] if d]) or "—"
            badge = f'<span class="badge s-blue">{esc(htype)}</span>' if htype else ""
            sitems.append(
                f'<li class="pditem" data-name="{esc(x["name"])}" data-pmin="{pmin}" data-pmax="{pmax}" data-type="{esc(htype)}" data-door="{esc(door_key)}" data-d="{esc(district)}">'
                f'<div class="pdhead"><span class="pdname">{esc(x["name"])}{badge}'
                f'<span class="pdkz">在线 {x["online"]} 套</span></span>'
                f'<span class="pdright">{esc(x.get("addr"))}　·　{esc(x.get("tel"))}</span></div>'
                f'<div class="pddetail"><div class="pdgrid">'
                f'<div class="pdcell"><b>租金</b>{esc(price)}</div>'
                f'<div class="pdcell"><b>户型</b>{esc("、".join(dts)) or "—"}</div>'
                f'<div class="pdcell"><b>供应</b>{esc(supply)}</div>'
                f'<div class="pdcell"><b>受理</b>{esc(accept)}</div>'
                f'<div class="pdcell"><b>介绍</b>{esc(x.get("intro")) or "—"}</div>'
                f'</div></div></li>')
        ssb_items = "".join(sitems)
        pd = latest["pd"]
        metros = sorted({m.split("/")[0].strip() for x in pd for m in (x.get("metro") or []) if m})
        statuses = sorted({x.get("status") for x in pd if x.get("status")})
        metro_opts = "".join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in metros)
        status_opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in statuses)
        pd_filter = (
            '<label>租金：<input id="pd_fmin" type="number" placeholder="最低" style="width:72px">'
            ' - <input id="pd_fmax" type="number" placeholder="最高" style="width:72px"></label>'
            f'<label>地铁：<select id="pd_fmetro"><option value="">全部</option>{metro_opts}</select></label>'
            f'<label>状态：<select id="pd_fstatus"><option value="">全部</option>{status_opts}</select></label>'
            '<label>户型：<select id="pd_ffy"><option value="">全部</option>'
            '<option value="一室">一室</option><option value="二室">二室</option><option value="三室">三室</option></select></label>'
            '<button type="button" onclick="filterPd()">筛选</button>'
        )
        pitems = []
        for x in sorted(pd, key=lambda a: -(a["kzts"] or 0)):
            price = x.get("price") or ""
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", price)]
            pmin = min(nums) if nums else 0
            pmax = max(nums) if nums else 0
            metro = "、".join(x.get("metro") or [])
            mlines = []
            for m in (x.get("metro") or []):
                ln = m.split("/")[0].strip()
                if ln and ln not in mlines:
                    mlines.append(ln)
            metro_key = "、".join(mlines)
            status = x.get("status") or ""
            fylx = "、".join(x.get("fylx") or [])
            cats = []
            for item in (x.get("fylx") or []):
                nm = re.sub(r"\d+(套|间)?$", "", item).strip()
                if nm.startswith("一室"):
                    c = "一室"
                elif nm.startswith(("二室", "两室")):
                    c = "二室"
                elif nm.startswith("三室"):
                    c = "三室"
                else:
                    c = ""
                if c and c not in cats:
                    cats.append(c)
            fyc = "、".join(cats)
            cls = {"运营": "s-yy", "待供应": "s-dg", "在建": "s-zj"}.get(status, "s-ot")
            badge = f'<span class="badge {cls}">{esc(status)}</span>' if status else ""
            pitems.append(
                f'<li class="pditem" data-name="{esc(x["name"])}" data-pmin="{pmin}" data-pmax="{pmax}" data-metro="{esc(metro_key)}" data-status="{esc(status)}" data-fy="{esc(fyc)}">'
                f'<div class="pdhead"><span class="pdname">{esc(x["name"])}{badge}'
                f'<span class="pdkz">可租 {x["kzts"]} 套</span></span>'
                f'<span class="pdright">{esc(x.get("addr"))}　·　{esc(x.get("tel"))}</span></div>'
                f'<div class="pddetail"><div class="pdgrid">'
                f'<div class="pdcell"><b>租金</b>{esc(price) or "—"}</div>'
                f'<div class="pdcell"><b>地铁</b>{esc(metro) or "—"}</div>'
                f'<div class="pdcell"><b>板块</b>{esc(x.get("zone")) or "—"}</div>'
                f'<div class="pdcell"><b>供应</b>{esc(x.get("supply_date")) or "—"}</div>'
                f'<div class="pdcell"><b>发布</b>{esc(x.get("release_time")) or "—"}</div>'
                f'<div class="pdcell"><b>户型</b>{esc(fylx) or "—"}</div>'
                f'</div></div></li>')
        pd_items = "".join(pitems)
        return ssb_filter, ssb_items, pd_filter, pd_items

    ssb_filter, ssb_items, pd_filter, pd_items = all_projects(latest)

    trend = []
    for s in snaps:
        trend.append(f"<tr><td>{s['date']}</td><td>{len(s['ssb'])}</td>"
                     f"<td>{sum(x['online'] for x in s['ssb'])}</td>"
                     f"<td>{len(s['pd'])}</td><td>{sum(x['kzts'] for x in s['pd'])}</td></tr>")
    trend_table = "\n".join(trend)

    opts = ""
    if base_options:
        for val, label in base_options:
            sel = " selected" if val == selected_base else ""
            opts += f'<option value="{esc(val)}"{sel}>{esc(label)}</option>'

    selector = ""
    if opts:
        selector = (f'<form method="get" style="display:inline">当前数据 与 <select name="base" onchange="this.form.submit()">{opts}</select> 相比</form>')
        sent = f'当前数据（{esc(cur_label)}） 与 〔{esc(base_label)}〕 相比'
    else:
        sent = f'当前数据（{esc(cur_label)}） 与 〔{esc(base_label)}〕 相比'

    meta = f'<meta http-equiv="refresh" content="{auto_refresh}">' if auto_refresh else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">{meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>上海房源变化报表</title>
<style>
 html{{scroll-behavior:smooth}}
 body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#222;display:flex;align-items:flex-start}}
 #sidebar{{flex:0 0 210px;position:sticky;top:0;height:100vh;overflow:auto;background:#fff;border-right:1px solid #e6e8eb;transition:flex-basis .2s}}
 #sidebar.collapsed{{flex-basis:46px}}
 #sidebar .sb-inner{{padding:12px 10px}}
 #sidebar.collapsed .sb-link,#sidebar.collapsed .sb-title{{display:none}}
 .sb-toggle{{float:right;background:none;border:0;font-size:18px;cursor:pointer;color:#555;padding:2px 6px;line-height:1}}
 .sb-title{{font-size:12px;color:#999;margin:10px 0 6px;clear:both}}
 .sb-link{{display:block;padding:7px 8px;color:#333;font-size:14px;border-radius:6px;text-decoration:none;white-space:nowrap}}
 .sb-link:hover{{background:#eef4fd;color:#2563eb}}
 @media (max-width:760px){{ #sidebar{{display:none}} }}
 .wrap{{flex:1;min-width:0;max-width:1000px;margin:0 auto;padding:24px}}
 h1{{font-size:22px;margin:0 0 4px}}
 .sub{{color:#666;font-size:14px;margin:6px 0 18px;line-height:1.9}}
 .sub select{{padding:4px 8px;border:1px solid #ccc;border-radius:6px;font-size:14px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
 .card{{background:#fff;border-radius:10px;padding:14px 18px;flex:1;min-width:150px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
 .card .n{{font-size:24px;font-weight:700}} .card .d{{font-size:13px;color:#888;font-weight:400;margin-left:2px}} .card .l{{color:#888;font-size:12px;margin-top:2px}}
 table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:22px}}
 th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #eee;font-size:14px}}
 th{{background:#fafafa;color:#666;font-weight:600}}
 .up{{color:#d33;font-weight:700}} .down{{color:#1a8f43;font-weight:700}}
 h2{{font-size:17px;margin:26px 0 10px}} h3{{font-size:15px;margin:18px 0 6px}}
 h4{{margin:10px 0 4px;font-size:13px;color:#555}} ul{{margin:4px 0 10px;padding-left:22px}} li{{font-size:13px;margin:3px 0;line-height:1.5}}
 .box{{background:#fff;border-radius:10px;padding:6px 18px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
 .filters{{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 0;border-bottom:1px solid #eee;margin-bottom:6px}}
 .filters label{{font-size:13px;cursor:pointer;user-select:none;white-space:nowrap}}
 .filters input{{margin-right:4px;vertical-align:middle}}
 .grp{{margin:6px 0}} .alllist{{margin:6px 0 2px;padding-left:22px}} .alllist li{{font-size:13px;margin:3px 0;line-height:1.5}}
 .emptyhint{{color:#999;font-size:13px;padding:8px 0}}
 .note{{color:#999;font-size:12px;margin:-14px 0 20px;line-height:1.6}}
 .note-top{{color:#999;font-size:12px;margin:2px 0 10px;line-height:1.6}}
 .pdlist{{list-style:none;padding:0;margin:6px 0}}
 .pditem{{border-bottom:1px solid #eee}}
 .pdhead{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 10px;padding:10px 4px;cursor:pointer;font-size:14px;align-items:baseline}}
 .pdhead:hover{{background:#fafafa}}
 .pdname{{font-weight:600}}
 .pdkz{{color:#1a8f43;font-weight:600;margin-left:8px;font-size:12px}}
 .badge{{font-size:11px;padding:1px 6px;border-radius:8px;margin-left:6px;color:#fff;white-space:nowrap}}
 .s-yy{{background:#1a8f43}} .s-dg{{background:#e08a00}} .s-zj{{background:#888}} .s-ot{{background:#999}} .s-blue{{background:#5b9bd5}}
 .ms{{position:relative;display:inline-block}}
 .ms>summary{{cursor:pointer;font-size:14px;list-style:none;padding:6px 24px 6px 8px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#000;white-space:nowrap}}
 .ms[open]>summary{{border-color:#2563eb}}
 .ms>summary::-webkit-details-marker{{display:none}}
 .ms>summary::after{{content:"▾";position:absolute;right:8px;color:#888}}
 .ms[open]>summary::after{{content:"▴"}}
 .ms .ms-list{{position:absolute;z-index:20;top:100%;left:0;margin-top:4px;background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px 10px;max-height:260px;overflow:auto;box-shadow:0 4px 12px rgba(0,0,0,.12);min-width:160px}}
 .ms .ms-list label{{display:block;white-space:nowrap;font-size:13px;padding:3px 0;cursor:pointer}}
 .listhead{{display:flex;justify-content:space-between;align-items:center;margin:16px 0 4px}}
 .listhead h3{{margin:0}}
 .listwrap{{display:none}}
 .tbtn{{font-size:13px;padding:5px 12px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#2563eb;cursor:pointer}}
 .tbtn:hover{{border-color:#2563eb}}
 .hright{{display:flex;gap:10px;align-items:center}}
 .searchbox{{position:relative}}
 .searchbox .q{{padding:5px 26px 5px 8px;border:1px solid #ccc;border-radius:6px;font-size:13px;width:190px}}
 .searchbox .qclear{{position:absolute;right:4px;top:50%;transform:translateY(-50%);border:0;background:none;color:#999;font-size:16px;cursor:pointer;padding:0 4px;display:none}}
 .sug{{display:none;position:absolute;z-index:40;top:100%;left:0;margin-top:2px;background:#fff;border:1px solid #ddd;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.14);max-height:260px;overflow:auto;min-width:200px}}
 .sug-item{{padding:6px 10px;font-size:13px;cursor:pointer;white-space:nowrap}}
 .sug-item:hover{{background:#eff6ff}}
 .sug-item.muted{{color:#999;cursor:default}}
 .pdright{{color:#888;text-align:right;margin-left:auto;font-size:12px}}
 .pddetail{{display:none;padding:4px 4px 14px}}
 .pditem.open .pddetail{{display:block}}
 .pdgrid{{display:block}}
 .pdcell{{display:block;font-size:13px;color:#333;line-height:1.9;word-break:break-all}}
 .pdcell b{{color:#999;font-weight:400;margin-right:6px;display:inline-block;min-width:44px}}
 @media (max-width:640px){{
   .wrap{{padding:12px}}
   h1{{font-size:19px}}
   .pdhead{{font-size:13px}}
   .pdright{{width:100%;text-align:left;margin-left:0}}
   th,td{{font-size:12px;padding:6px 5px}}
   .card .n{{font-size:20px}}
 }}
</style></head><body>
<div id="sidebar"><div class="sb-inner">
<button class="sb-toggle" onclick="toggleNav()">«</button>
<div class="sb-title">章节</div>
<a class="sb-link" href="#sec-top">概览</a>
<a class="sb-link" href="#sec-notice">供应预告</a>
<a class="sb-link" href="#sec-ssb">随申办·行政区</a>
<a class="sb-link" href="#sec-pd">明珠在线·行政区</a>
<a class="sb-link" href="#sec-chg">变动明细</a>
<a class="sb-link" href="#sec-all">全部房源明细</a>
<a class="sb-link" href="#sec-trend">逐日趋势</a>
</div></div>
<div class="wrap">
<h1 id="sec-top">上海房源变化报表</h1>
<div class="sub">{selector if opts else ''}<div>{sent}　｜　数据每 30 分钟更新，页面每 30 分钟自动刷新</div></div>
<div class="cards">
 <div class="card"><div class="n">{c_ssb}</div><div class="l">随申办 项目数</div></div>
 <div class="card"><div class="n">{c_ssb_online}</div><div class="l">随申办 在线房源数</div></div>
 <div class="card"><div class="n">{c_pd}</div><div class="l">明珠在线 项目数</div></div>
 <div class="card"><div class="n">{c_pd_kzts}</div><div class="l">明珠在线 可租套数</div></div>
 <div class="card"><div class="n">{c_notice}</div><div class="l">随申办 供应预告</div></div>
</div>

<h2 id="sec-notice">随申办 · 供应预告（{len(notice)}）</h2>
<table><thead><tr><th>项目</th><th>计划供应日</th><th>租金</th><th>地址</th><th>电话</th><th>运营单位</th></tr></thead>
<tbody>{notice_table}</tbody></table>

<h2 id="sec-ssb">随申办 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>在线房源</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{dist_table}</tbody></table>
<div class="note">* "在线房源"取自平台自带字段（onlineFlatNum），仅代表该时刻的在线套数，不保证随时可租。</div>

<h2 id="sec-pd">明珠在线 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>可租套数</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{pd_table}</tbody></table>
<div class="note">* "可租套数"取自平台页面自带字段（kzts），不保证当前有房；显示 0 套表示该项目当前无可租房源（如已租满或尚未供应）。</div>

<h2 id="sec-chg">变动明细（当前 vs 基线）</h2>
<div class="box">
{detail("随申办", ssb_ch)}
{detail("明珠在线", pd_ch)}
</div>

<h2 id="sec-all">全部房源明细</h2>
<div class="box">
<div class="allbox">
<div class="listhead"><h3>随申办</h3><div class="hright"><div class="searchbox"><input id="sb_q" class="q" placeholder="搜索项目名"><button type="button" class="qclear" id="sb_clr">×</button><div id="sb_sug" class="sug"></div></div><button type="button" class="tbtn" onclick="toggleList('sbwrap',this)">展开列表 ▾</button></div></div>
<div class="filters">{ssb_filter}</div>
<div class="listwrap" id="sbwrap"><ul class="pdlist" id="sblist">{ssb_items}</ul></div>
</div>
<div class="allbox">
<div class="listhead"><h3>明珠在线</h3><div class="hright"><div class="searchbox"><input id="pd_q" class="q" placeholder="搜索项目名"><button type="button" class="qclear" id="pd_clr">×</button><div id="pd_sug" class="sug"></div></div><button type="button" class="tbtn" onclick="toggleList('pdwrap',this)">展开列表 ▾</button></div></div>
<div class="note note-top">* 可租套数按接口字段（kzts）提取，仅供参考，不保证当前有房。</div>
<div class="filters">{pd_filter}</div>
<div class="listwrap" id="pdwrap"><ul class="pdlist" id="pdlist">{pd_items}</ul></div>
</div>
</div>

<h2 id="sec-trend">逐日趋势</h2>
<table><thead><tr><th>日期</th><th>随申办项目</th><th>随申办在线</th><th>明珠项目</th><th>明珠可租</th></tr></thead>
<tbody>{trend_table}</tbody></table>
</div>
<script>
function filterSb(){{
  var mn=parseFloat((document.getElementById('sb_fmin')||{{}}).value); if(isNaN(mn)) mn=0;
  var mx=parseFloat((document.getElementById('sb_fmax')||{{}}).value); if(isNaN(mx)) mx=Infinity;
  var ty=(document.getElementById('sb_ftype')||{{}}).value||'';
  var dr=(document.getElementById('sb_fdoor')||{{}}).value||'';
  var dset={{}}; document.querySelectorAll('.sb_d:checked').forEach(function(c){{ dset[c.value]=1; }});
  var n=Object.keys(dset).length;
  var sum=document.getElementById('sb_dsum'); if(sum) sum.textContent='行政区：'+(n?('已选 '+n+' 个'):'全部');
  document.querySelectorAll('#sblist .pditem').forEach(function(li){{
    var pmin=parseFloat(li.getAttribute('data-pmin'))||0, pmax=parseFloat(li.getAttribute('data-pmax'))||0;
    var okP=(pmax>=mn)&&(pmin<=mx);
    var okT=!ty||li.getAttribute('data-type')===ty;
    var okD=!dr||(li.getAttribute('data-door')||'').indexOf(dr)>=0;
    var okA=!n||dset[li.getAttribute('data-d')];
    li.style.display=(okP&&okT&&okD&&okA)?'':'none';
  }});
}}
function filterPd(){{
  var mn=parseFloat((document.getElementById('pd_fmin')||{{}}).value); if(isNaN(mn)) mn=0;
  var mx=parseFloat((document.getElementById('pd_fmax')||{{}}).value); if(isNaN(mx)) mx=Infinity;
  var mt=(document.getElementById('pd_fmetro')||{{}}).value||'';
  var st=(document.getElementById('pd_fstatus')||{{}}).value||'';
  var fy=(document.getElementById('pd_ffy')||{{}}).value||'';
  document.querySelectorAll('#pdlist .pditem').forEach(function(li){{
    var pmin=parseFloat(li.getAttribute('data-pmin'))||0;
    var pmax=parseFloat(li.getAttribute('data-pmax'))||0;
    var okP=(pmax>=mn)&&(pmin<=mx);
    var okM=!mt||(li.getAttribute('data-metro')||'').indexOf(mt)>=0;
    var okS=!st||li.getAttribute('data-status')===st;
    var okF=!fy||(li.getAttribute('data-fy')||'').indexOf(fy)>=0;
    li.style.display=(okP&&okM&&okS&&okF)?'':'none';
  }});
}}
function toggleList(id, btn){{
  var el=document.getElementById(id);
  if(!el) return;
  if(el.style.display==='block'){{ el.style.display='none'; btn.textContent='展开列表 ▾'; }}
  else {{ el.style.display='block'; btn.textContent='收起列表 ▴'; }}
}}
function toggleNav(){{
  var el=document.getElementById('sidebar');
  el.classList.toggle('collapsed');
  var b=el.querySelector('.sb-toggle');
  if(b) b.textContent=el.classList.contains('collapsed')?'»':'«';
  try{{ localStorage.setItem('nav_collapsed', el.classList.contains('collapsed')?'1':'0'); }}catch(e){{}}
}}
(function(){{
  try{{
    var el=document.getElementById('sidebar');
    if(el && localStorage.getItem('nav_collapsed')==='1'){{
      el.classList.add('collapsed');
      var b=el.querySelector('.sb-toggle'); if(b) b.textContent='»';
    }}
  }}catch(e){{}}
}})();
function doSearch(src){{
  var inp=document.getElementById(src+'_q');
  var q=(inp.value||'').trim();
  var listId=(src==='sb')?'sblist':'pdlist';
  var wrapId=(src==='sb')?'sbwrap':'pdwrap';
  var items=document.querySelectorAll('#'+listId+' .pditem');
  if(!q){{ if(src==='sb') filterSb(); else filterPd(); return; }}
  document.getElementById(wrapId).style.display='block';
  items.forEach(function(li){{
    var hit=(li.getAttribute('data-name')||'')===q;
    li.style.display=hit?'':'none';
    if(hit) li.classList.add('open');
  }});
}}
function clearSearch(src){{
  var inp=document.getElementById(src+'_q'); if(inp) inp.value='';
  var sug=document.getElementById(src+'_sug'); if(sug){{ sug.style.display='none'; sug.innerHTML=''; }}
  var cl=document.getElementById(src+'_clr'); if(cl) cl.style.display='none';
  doSearch(src);
}}
function suggest(src){{
  var inp=document.getElementById(src+'_q');
  var sug=document.getElementById(src+'_sug');
  var cl=document.getElementById(src+'_clr');
  var listId=(src==='sb')?'sblist':'pdlist';
  var q=(inp.value||'').trim();
  if(cl) cl.style.display=q?'block':'none';
  if(!q){{ sug.style.display='none'; sug.innerHTML=''; doSearch(src); return; }}
  var names=[], seen={{}};
  document.querySelectorAll('#'+listId+' .pditem').forEach(function(li){{
    var nm=li.getAttribute('data-name')||'';
    if(nm.indexOf(q)>=0 && !seen[nm]){{ seen[nm]=1; names.push(nm); }}
  }});
  names.sort();
  sug.innerHTML='';
  if(!names.length){{ var d=document.createElement('div'); d.className='sug-item muted'; d.textContent='无匹配'; sug.appendChild(d); sug.style.display='block'; return; }}
  names.slice(0,50).forEach(function(n){{
    var d=document.createElement('div'); d.className='sug-item'; d.textContent=n;
    d.addEventListener('click', function(){{ inp.value=n; sug.style.display='none'; doSearch(src); }});
    sug.appendChild(d);
  }});
  sug.style.display='block';
}}
['sb','pd'].forEach(function(src){{
  var inp=document.getElementById(src+'_q');
  if(inp){{
    inp.addEventListener('input', function(){{ suggest(src); }});
    inp.addEventListener('keydown', function(e){{
      if(e.key==='Escape') clearSearch(src);
      if(e.key==='Enter'){{ var s=document.getElementById(src+'_sug'); if(s) s.style.display='none'; doSearch(src); }}
    }});
  }}
  var cl=document.getElementById(src+'_clr');
  if(cl) cl.addEventListener('click', function(){{ clearSearch(src); }});
}});
document.addEventListener('click', function(e){{
  if(!e.target.closest || !e.target.closest('.searchbox')){{
    document.querySelectorAll('.sug').forEach(function(s){{ s.style.display='none'; }});
  }}
}});
document.querySelectorAll('.pdhead').forEach(function(h){{ h.addEventListener('click', function(){{ h.parentNode.classList.toggle('open'); }}); }});
['pd_fmin','pd_fmax','pd_fmetro','pd_fstatus','pd_ffy'].forEach(function(id){{ var el=document.getElementById(id); if(el){{ el.addEventListener('change', filterPd); el.addEventListener('input', filterPd); }} }});
filterPd();
['sb_fmin','sb_fmax','sb_ftype','sb_fdoor'].forEach(function(id){{ var el=document.getElementById(id); if(el){{ el.addEventListener('change', filterSb); el.addEventListener('input', filterSb); }} }});
document.querySelectorAll('.sb_d').forEach(function(c){{ c.addEventListener('change', filterSb); }});
filterSb();
</script>
</body></html>"""


def build():
    snaps = load_snapshots()
    if not snaps:
        raise SystemExit("没有 data/20*.json，先运行 refresh.py")
    latest = snaps[-1]
    prev = snaps[-2] if len(snaps) >= 2 else {"ssb": [], "pd": [], "notice": []}
    html = render_html(latest, prev, snaps)
    with open(OUT, "w") as f:
        f.write(html)
    print("已生成", OUT)
    return OUT


if __name__ == "__main__":
    build()
