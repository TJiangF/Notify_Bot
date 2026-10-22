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


def _range_box(pfx, rmax=0):
    return (
        '<span class="rangebox">'
        f'<input type="number" id="{pfx}_fmin" class="rn" placeholder="最低">'
        '<span>-</span>'
        f'<input type="number" id="{pfx}_fmax" class="rn" placeholder="最高">'
        '</span>'
    )


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
        tag_opts = "".join(f'<label><input type="checkbox" class="sb_t" value="{esc(t)}"> {esc(t)}</label>'
                           for t in ["保障性租赁住房", "新青年就业安居"])
        h_opts = "".join(f'<label><input type="checkbox" class="sb_h" value="{esc(d)}"> {esc(d)}</label>'
                         for d in ["单间", "一居室", "二居室", "三居室", "多居室"])
        districts = sorted({x.get("district") for x in ssb if x.get("district")})
        dchecks = "".join(f'<label><input type="checkbox" class="sb_d" value="{esc(d)}"> {esc(d)}</label>' for d in districts)
        hmax = 0
        for x in ssb:
            h = x.get("rent_high")
            if isinstance(h, (int, float)):
                hmax = max(hmax, h)
        rmax = int((hmax // 1000 + 1) * 1000) if hmax else 20000
        ssb_filter = (
            '<label>租金：' + _range_box("sb", rmax) + '</label>'
            '<details class="ms"><summary id="sb_tsum">类型：全部</summary>'
            f'<div class="ms-list">{tag_opts}</div></details>'
            '<details class="ms"><summary id="sb_hsum">户型：全部</summary>'
            f'<div class="ms-list">{h_opts}</div></details>'
            '<details class="ms"><summary id="sb_dsum">行政区：全部</summary>'
            f'<div class="ms-list">{dchecks}</div></details>'
            '<button type="button" onclick="applySb()">筛选</button>'
            '<button type="button" class="btn-reset" onclick="resetSb()">清空筛选</button>'
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
            tags = []
            ht = x.get("house_type")
            if ht:
                tags.append(ht)
            if x.get("qnaj"):
                tags.append("新青年就业安居")
            badges = "".join(f'<span class="badge {"s-green" if t == "新青年就业安居" else "s-blue"}">{esc(t)}</span>' for t in tags)
            tags_attr = "、".join(tags)
            dts = [t.strip() for t in (x.get("door_type") or "").replace("，", "、").split("、") if t.strip()]
            door_key = "、".join(dts)
            district = x.get("district") or ""
            supply = " ~ ".join([d for d in [dday(x.get("supply_start")), dday(x.get("supply_end"))] if d]) or "—"
            accept = " ~ ".join([d for d in [dday(x.get("accept_start")), dday(x.get("accept_end"))] if d]) or "—"
            sitems.append(
                f'<li class="pditem" data-key="ssb:{esc(str(x.get("id")))}" data-name="{esc(x["name"])}" data-pmin="{pmin}" data-pmax="{pmax}" data-tags="{esc(tags_attr)}" data-door="{esc(door_key)}" data-d="{esc(district)}">'
                f'<div class="pdhead"><span class="pdname">{esc(x["name"])}{badges}'
                f'<span class="pdkz">在线 {x["online"]} 套</span></span>'
                f'<span class="pdheadright"><span class="pdright">{esc(x.get("addr"))}　·　{esc(x.get("tel"))}</span>'
                f'<button type="button" class="cmp-add" onclick="addCompare(event,this)">加入比较</button></span></div>'
                f'<div class="pddetail"><div class="pdgrid">'
                f'<div class="pdcell"><b>租金</b>{esc(price)}</div>'
                f'<div class="pdcell"><b>户型</b>{esc("、".join(dts)) or "—"}</div>'
                f'<div class="pdcell"><b>供应</b>{esc(supply)}</div>'
                f'<div class="pdcell"><b>受理</b>{esc(accept)}</div>'
                 f'<div class="pdcell"><b>介绍</b>{esc(x.get("intro")) or "—"}</div>'
                 f'</div>'
                 f'<div class="hxwrap" data-pid="{esc(str(x.get("id")))}" data-name="{esc(x["name"]) }">'
                 f'<div class="hxstate muted">户型与房源明细（面积/门牌/整合租/租金/状态/库存）</div>'
                 f'<div class="hxbox"></div>'
                 f'<button type="button" class="hxbtn ghost">查看该项目的户型与房源明细</button>'
                 f'</div>'
                 f'<div class="cmts" data-key="ssb:{esc(str(x.get("id")))}"></div></div></li>')
        ssb_items = "".join(sitems)
        pd = latest["pd"]
        metros = sorted({m.split("/")[0].strip() for x in pd for m in (x.get("metro") or []) if m})
        statuses = sorted({x.get("status") for x in pd if x.get("status")})
        metro_opts = "".join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in metros)
        status_opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in statuses)
        hmaxp = 0
        for x in pd:
            pr = x.get("price") or ""
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", pr)]
            if nums:
                hmaxp = max(hmaxp, max(nums))
        rmaxp = int((hmaxp // 1000 + 1) * 1000) if hmaxp else 20000
        fy_opts = "".join(f'<label><input type="checkbox" class="pd_h" value="{esc(d)}"> {esc(d)}</label>'
                          for d in ["一室", "二室", "三室"])
        metro_chk = "".join(f'<label><input type="checkbox" class="pd_m" value="{esc(m)}"> {esc(m)}</label>' for m in metros)
        status_chk = "".join(f'<label><input type="checkbox" class="pd_s" value="{esc(s)}"> {esc(s)}</label>' for s in statuses)
        pd_filter = (
            '<label>租金：' + _range_box("pd", rmaxp) + '</label>'
            '<details class="ms"><summary id="pd_msum">地铁：全部</summary>'
            f'<div class="ms-list">{metro_chk}</div></details>'
            '<details class="ms"><summary id="pd_ssum">状态：全部</summary>'
            f'<div class="ms-list">{status_chk}</div></details>'
            '<details class="ms"><summary id="pd_hsum">户型：全部</summary>'
            f'<div class="ms-list">{fy_opts}</div></details>'
            '<button type="button" onclick="applyPd()">筛选</button>'
            '<button type="button" class="btn-reset" onclick="resetPd()">清空筛选</button>'
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
                f'<li class="pditem" data-key="pd:{esc(str(x.get("id")))}" data-name="{esc(x["name"])}" data-pmin="{pmin}" data-pmax="{pmax}" data-metro="{esc(metro_key)}" data-status="{esc(status)}" data-fy="{esc(fyc)}">'
                f'<div class="pdhead"><span class="pdname">{esc(x["name"])}{badge}'
                f'<span class="pdkz">可租 {x["kzts"]} 套</span></span>'
                f'<span class="pdheadright"><span class="pdright">{esc(x.get("addr"))}　·　{esc(x.get("tel"))}</span>'
                f'<button type="button" class="cmp-add" onclick="addCompare(event,this)">加入比较</button></span></div>'
                f'<div class="pddetail"><div class="pdgrid">'
                f'<div class="pdcell"><b>租金</b>{esc(price) or "—"}</div>'
                f'<div class="pdcell"><b>地铁</b>{esc(metro) or "—"}</div>'
                f'<div class="pdcell"><b>板块</b>{esc(x.get("zone")) or "—"}</div>'
                f'<div class="pdcell"><b>供应</b>{esc(x.get("supply_date")) or "—"}</div>'
                f'<div class="pdcell"><b>发布</b>{esc(x.get("release_time")) or "—"}</div>'
                f'<div class="pdcell"><b>户型</b>{esc(fylx) or "—"}</div>'
                f'</div><div class="cmts" data-key="pd:{esc(str(x.get("id")))}"></div></div></li>')
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

    _st = latest.get("stale") or {}
    _names = [n for n, k in (("随申办", "ssb"), ("明珠在线", "pd"), ("供应预告", "notice")) if _st.get(k)]
    if _names:
        stale_banner = (f'<div class="stalebar">⚠️ 最近一次抓取未成功，'
                        f'{"、".join(_names)}数据为上一次有效值（{esc(latest.get("generated_at", ""))[:16]}）。</div>')
    else:
        stale_banner = ""

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
 .stalebar{{background:#fff7e6;border:1px solid #ffd591;color:#ad6800;border-radius:8px;padding:9px 12px;font-size:13px;margin:-8px 0 16px}}
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
 .s-yy{{background:#1a8f43}} .s-dg{{background:#e08a00}} .s-zj{{background:#888}} .s-ot{{background:#999}} .s-blue{{background:#5b9bd5}} .s-green{{background:#d7f2e3;color:#0f7a45}}
 .ms{{position:relative;display:inline-block}}
 .ms>summary{{cursor:pointer;font-size:14px;list-style:none;padding:6px 24px 6px 8px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#000;white-space:nowrap}}
 .ms[open]>summary{{border-color:#2563eb}}
 .ms>summary::-webkit-details-marker{{display:none}}
 .ms>summary::after{{content:"▾";position:absolute;right:8px;color:#888}}
 .ms[open]>summary::after{{content:"▴"}}
 .ms .ms-list{{position:absolute;z-index:20;top:100%;left:0;margin-top:4px;background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px 10px;max-height:260px;overflow:auto;box-shadow:0 4px 12px rgba(0,0,0,.12);min-width:160px}}
 .ms .ms-list label{{display:block;white-space:nowrap;font-size:13px;padding:3px 0;cursor:pointer}}
 .rangebox{{display:inline-flex;align-items:center;gap:8px;vertical-align:middle}}
 .rangedrag{{position:relative;width:170px;height:22px;flex:0 0 auto}}
 .rangedrag .rbar{{position:absolute;top:9px;left:0;right:0;height:4px;background:#e2e8f0;border-radius:2px}}
 .rangedrag .rbar i{{position:absolute;top:0;height:4px;background:#2563eb;border-radius:2px}}
 .rangedrag input[type=range]{{position:absolute;left:0;top:0;width:100%;height:22px;margin:0;background:transparent;-webkit-appearance:none;appearance:none;pointer-events:none}}
 .rangedrag input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;pointer-events:auto;width:16px;height:16px;border-radius:50%;background:#2563eb;border:2px solid #fff;box-shadow:0 1px 4px rgba(37,99,235,.5);cursor:pointer}}
 .rangebox .rn{{width:66px;padding:5px 6px;border:1px solid #ccc;border-radius:6px;font-size:13px}}
 .btn-reset{{font-size:13px;padding:5px 12px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#666;cursor:pointer}}
 .btn-reset:hover{{border-color:#f43f5e;color:#f43f5e}}
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
 .pdheadright{{display:flex;align-items:center;gap:10px;margin-left:auto}}
 .pdright{{color:#888;text-align:right;font-size:12px}}
 .cmp-add{{font-size:12px;padding:3px 10px;border:1px solid #2563eb;color:#2563eb;background:#fff;border-radius:14px;cursor:pointer;white-space:nowrap}}
 .cmp-add:hover{{background:#2563eb;color:#fff}}
 .cmp-fab{{position:fixed;right:18px;bottom:18px;z-index:90;background:#2563eb;color:#fff;border:0;border-radius:22px;padding:11px 18px;box-shadow:0 6px 18px rgba(37,99,235,.45);cursor:pointer;font-size:14px}}
 .cmp-fab:hover{{background:#1d4ed8}}
 .cmp{{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:92vw;height:90vh;z-index:100;background:#fff;border-radius:16px;box-shadow:0 24px 70px rgba(0,0,0,.35);display:none;flex-direction:column;overflow:hidden}}
 .cmp.open{{display:flex}}
 .cmp-head{{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid #eef0f3;font-weight:600;font-size:15px}}
 .cmp-actions{{display:flex;align-items:center;gap:16px}}
 .cmp-clear{{font-size:13px;color:#999;font-weight:400;cursor:pointer;background:none;border:0}}
 .cmp-clear:hover{{color:#f43f5e}}
 .cmp-close{{font-size:22px;line-height:1;background:none;border:0;color:#555;cursor:pointer;padding:0 2px}}
 .cmp-scroll{{overflow:auto;flex:1;background:#fafbfc;position:relative}}
 .cmptab{{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}}
 .cmptab th{{position:sticky;top:0;background:#f4f6f9;color:#555;font-weight:600;text-align:left;padding:9px 12px;border-bottom:1px solid #e6e8eb;white-space:nowrap}}
 .cmptab td{{padding:8px 12px;border-bottom:1px solid #eef0f3;vertical-align:top;white-space:nowrap;max-width:240px;overflow:hidden;text-overflow:ellipsis}}
 .cmptab tr.cmp-dragging td{{background:#eef4fd}}
 .cmptab .c-x{{width:36px;text-align:center;padding:6px}}
 .cmptab .c-name{{font-weight:600;max-width:220px}}
 .cmptab .c-intro{{max-width:340px}}
 .cmptab .c-intro.expanded{{white-space:normal;max-width:560px}}
 .c-expand{{color:#2563eb;cursor:pointer;font-size:11px;margin-left:4px;white-space:nowrap}}
 .cmp-x{{width:22px;height:22px;border-radius:50%;border:0;background:#f43f5e;color:#fff;cursor:pointer;line-height:1;font-size:14px;padding:0}}
 .cmp-x:hover{{background:#e11d48}}
 .cmp-src{{font-size:10px;color:#fff;background:#9aa4b2;border-radius:5px;padding:1px 6px;margin-left:6px;white-space:nowrap}}
 .cmp-empty{{color:#999;font-size:13px;padding:32px;text-align:center}}
 .pddetail{{display:none;padding:4px 4px 14px}}
 .pditem.open .pddetail{{display:block}}
 .pdgrid{{display:block}}
 .pdcell{{display:block;font-size:13px;color:#333;line-height:1.9;word-break:break-all}}
 .pdcell b{{color:#999;font-weight:400;margin-right:6px;display:inline-block;min-width:44px}}
 .cmts{{margin-top:10px;border-top:1px dashed #e6e8eb;padding-top:10px}}
 .cmt-title{{font-size:12px;color:#8794a8;margin-bottom:6px}}
 .cmt{{border:1px solid #eef0f3;border-radius:8px;padding:8px 10px;margin-bottom:8px;background:#fff}}
 .cmt-meta{{font-size:11px;color:#a3adbd;margin-bottom:4px}}
 .cmt-text{{font-size:13px;color:#333;white-space:pre-wrap;word-break:break-word}}
 .cmt-imgs{{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}}
 .cmt-imgs img{{width:84px;height:84px;object-fit:cover;border-radius:6px;border:1px solid #eef0f3}}
 .cmt-empty{{color:#a3adbd;font-size:12px;padding:6px 0}}
 .cmt-form{{margin-top:8px}}
 .cmt-form textarea{{width:100%;border:1px solid #d5dbe3;border-radius:8px;padding:8px;font-size:13px;box-sizing:border-box;resize:vertical;font-family:inherit}}
 .cmt-row{{display:flex;align-items:center;gap:10px;margin-top:6px}}
 .cmt-row input[type=file]{{font-size:12px;flex:1;min-width:0}}
 .cmt-send{{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:6px 16px;font-size:13px;cursor:pointer;white-space:nowrap}}
 .cmt-send:disabled{{opacity:.6;cursor:default}}
 .cmt-hint{{font-size:12px;color:#e11d48;margin-top:4px}}
 .hxwrap{{margin-top:10px;padding:10px;border:1px solid #e6eaf2;border-radius:10px;background:#fafbff}}
 .hxwrap .hxbtn{{margin-top:8px}}
 .hxstate{{font-size:12px}}
 .hxbox{{margin-top:8px}}
 .hxcard{{display:inline-flex;flex-direction:column;gap:6px;width:210px;border:1px solid #dbe3f2;border-radius:10px;padding:10px;background:#fff;cursor:pointer;vertical-align:top;margin:4px;transition:box-shadow .15s}}
 .hxcard:hover{{box-shadow:0 4px 16px rgba(37,99,235,.18)}}
 .hxcard .hxt{{font-weight:600;font-size:13px}}
 .hxcard .hxmeta{{font-size:12px;color:#667085;line-height:1.6}}
 .hxcard .hximg{{width:100%;height:110px;object-fit:contain;border-radius:8px;background:#f2f5fb}}
 .hxcard .hxnoimg{{width:100%;height:110px;display:flex;align-items:center;justify-content:center;color:#98a2b3;font-size:12px;background:#f6f8fb;border-radius:8px}}
 .hxglm{{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0}}
 .hxtag{{font-size:11px;border-radius:12px;padding:2px 8px;background:#eef4ff;color:#1d4ed8}}
 .hxtag.warn{{background:#fdecec;color:#c0392b}}
 .hxmodal{{position:fixed;inset:0;background:rgba(15,23,42,.45);display:none;z-index:60;align-items:center;justify-content:center}}
 .hxmodal .panel{{background:#fff;border-radius:14px;max-width:860px;width:92%;max-height:86vh;overflow:auto;padding:16px}}
 .hxmodal h3{{margin:2px 0 10px;font-size:15px}}
 .hxmodal table{{width:100%;border-collapse:collapse;font-size:12px}}
 .hxmodal th,.hxmodal td{{border-bottom:1px solid #eef0f4;padding:6px 8px;text-align:left;white-space:nowrap}}
 .hxmodal .stfree{{color:#1a8f43;font-weight:600}}
 .hxmodal .strent{{color:#c0392b}}
 .hxmodal .closebar{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
 .mapsearch{{display:flex;gap:10px;align-items:flex-start;padding:10px 0;flex-wrap:wrap}}
 .mapsb{{position:relative;flex:1;min-width:220px}}
 .mapsearch input{{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #d5dbe3;border-radius:8px;font-size:14px}}
 .mapsearch button{{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:9px 18px;font-size:14px;cursor:pointer;white-space:nowrap}}
 .mapsug{{position:absolute;left:0;right:0;top:100%;z-index:30;background:#fff;border:1px solid #d5dbe3;border-radius:8px;margin-top:2px;max-height:300px;overflow:auto;display:none;box-shadow:0 8px 22px rgba(0,0,0,.14)}}
 .mapsug>div{{padding:8px 10px;cursor:pointer;border-bottom:1px solid #f1f3f6}}
 .mapsug>div:hover{{background:#f2f6ff}}
 .mapsug .sg-n{{font-weight:600;font-size:13px}}
 .mapsug .sg-a{{color:#8794a8;font-size:12px;margin-top:1px}}
 .amap{{height:460px;border-radius:10px;margin-top:10px;background:#eef1f5}}
 .maplist{{margin-top:12px}}
 .mapitem{{display:flex;gap:10px;padding:8px 4px;border-bottom:1px solid #eef0f3;align-items:flex-start}}
 .mapidx{{flex:0 0 auto;width:22px;height:22px;border-radius:50%;background:#2563eb;color:#fff;text-align:center;line-height:22px;font-size:12px}}
 .mapname{{font-weight:600;font-size:14px}}
 .maptag{{font-size:11px;color:#fff;background:#9aa4b2;border-radius:5px;padding:1px 6px;margin-left:6px}}
 .maptag.tag-sb{{background:#2f6fed}}
 .maptag.tag-pd{{background:#f59e0b}}
 .mapmeta{{font-size:12px;color:#666;margin-top:2px}}
 .muted{{color:#8794a8}}
 @media (max-width:640px){{
   .wrap{{padding:12px}}
   h1{{font-size:19px}}
   .pdhead{{font-size:13px}}
   .pdheadright{{width:100%;justify-content:space-between;margin-left:0;margin-top:4px}}
   .pdright{{text-align:left}}
   th,td{{font-size:12px;padding:6px 5px}}
   .card .n{{font-size:20px}}
   .cmp{{width:96vw;height:94vh}}
 }}
</style></head><body>
<div id="sidebar"><div class="sb-inner">
<button class="sb-toggle" onclick="toggleNav()">«</button>
<div class="sb-title">章节</div>
<a class="sb-link" href="#sec-top">概览</a>
<a class="sb-link" href="#sec-map">智能找房</a>
<a class="sb-link" href="#sec-notice">供应预告</a>
<a class="sb-link" href="#sec-ssb">随申办·行政区</a>
<a class="sb-link" href="#sec-pd">明珠在线·行政区</a>
<a class="sb-link" href="#sec-chg">变动明细</a>
<a class="sb-link" href="#sec-all">全部房源明细</a>
<a class="sb-link" href="#sec-trend">逐日趋势</a>
</div></div>
<div class="wrap">
<h1 id="sec-top">上海房源变化报表</h1>
<div class="sub">{selector if opts else ''}<div>{sent}　｜　数据每 20 分钟更新，页面定时自动刷新</div></div>
{stale_banner}
<div class="cards">
 <div class="card"><div class="n">{c_ssb}</div><div class="l">随申办 项目数</div></div>
 <div class="card"><div class="n">{c_ssb_online}</div><div class="l">随申办 在线房源数</div></div>
 <div class="card"><div class="n">{c_pd}</div><div class="l">明珠在线 项目数</div></div>
 <div class="card"><div class="n">{c_pd_kzts}</div><div class="l">明珠在线 可租套数</div></div>
 <div class="card"><div class="n">{c_notice}</div><div class="l">随申办 供应预告</div></div>
</div>

<h2 id="sec-map">🧭 智能找房</h2>
<div class="box">
  <div class="mapsearch">
    <div class="mapsb">
      <input id="map_q" placeholder="输入上海地址或地标，如：人民广场 / 张江科学之门 / 某路某弄" autocomplete="off">
      <div id="map_sug" class="mapsug"></div>
    </div>
    <button type="button" onclick="doFind()">找附近房源</button>
    <span id="map_msg" class="muted"></span>
  </div>
  <div id="amap" class="amap"></div>
  <div id="map_list" class="maplist"></div>
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
<button id="cmpFab" class="cmp-fab" onclick="toggleCompare()">对比 <span id="cmpFabN">0</span></button>
<div id="cmpPanel" class="cmp">
  <div class="cmp-head"><span>对比清单 <span id="cmpN">0</span></span>
    <div class="cmp-actions"><button class="cmp-clear" onclick="clearCompare()">清空</button><button class="cmp-close" onclick="toggleCompare()">×</button></div>
  </div>
  <div class="cmp-scroll">
    <table class="cmptab"><thead id="cmpThead"></thead><tbody id="cmpTbody"></tbody></table>
    <div id="cmpEmpty" class="cmp-empty">还没有加入对比的房源</div>
  </div>
</div>
<div id="hxModal" class="hxmodal"><div class="panel"><div class="closebar"><h3 id="hxTitle">户型 · 房源明细</h3><button type="button" class="ghost" onclick="hxClose()">关闭</button></div><div id="hxBody"></div></div></div>
<script src="https://webapi.amap.com/maps?v=1.4.15&key=c226df9a44846d549b4f1689ece31e5"></script>
<script>
function filterSb(){{
  var mn=parseFloat((document.getElementById('sb_fmin')||{{}}).value); if(isNaN(mn)) mn=0;
  var mx=parseFloat((document.getElementById('sb_fmax')||{{}}).value); if(isNaN(mx)) mx=Infinity;
  var tset={{}}; document.querySelectorAll('.sb_t:checked').forEach(function(c){{ tset[c.value]=1; }});
  var tkeys=Object.keys(tset); var tn=tkeys.length;
  var tsum=document.getElementById('sb_tsum'); if(tsum) tsum.textContent='类型：'+(tn?('已选 '+tn+' 个'):'全部');
  var hset={{}}; document.querySelectorAll('.sb_h:checked').forEach(function(c){{ hset[c.value]=1; }});
  var hkeys=Object.keys(hset); var hn=hkeys.length;
  var hsum=document.getElementById('sb_hsum'); if(hsum) hsum.textContent='户型：'+(hn?('已选 '+hn+' 个'):'全部');
  var dset={{}}; document.querySelectorAll('.sb_d:checked').forEach(function(c){{ dset[c.value]=1; }});
  var n=Object.keys(dset).length;
  var sum=document.getElementById('sb_dsum'); if(sum) sum.textContent='行政区：'+(n?('已选 '+n+' 个'):'全部');
  document.querySelectorAll('#sblist .pditem').forEach(function(li){{
    var pmin=parseFloat(li.getAttribute('data-pmin'))||0, pmax=parseFloat(li.getAttribute('data-pmax'))||0;
    var okP=(pmax>=mn)&&(pmin<=mx);
    var tags=li.getAttribute('data-tags')||'';
    var okT=!tn||tkeys.some(function(t){{ return tags.indexOf(t)>=0; }});
    var doors=li.getAttribute('data-door')||'';
    var okH=!hn||hkeys.some(function(t){{ return doors.indexOf(t)>=0; }});
    var okA=!n||dset[li.getAttribute('data-d')];
    li.style.display=(okP&&okT&&okH&&okA)?'':'none';
  }});
}}
function applySb(){{ var w=document.getElementById('sbwrap'); if(w) w.style.display='block'; setToggle('sbwrap','收起列表 ▴'); filterSb(); }}
function applyPd(){{ var w=document.getElementById('pdwrap'); if(w) w.style.display='block'; setToggle('pdwrap','收起列表 ▴'); filterPd(); }}
function setToggle(wrapId, txt){{ document.querySelectorAll('.tbtn').forEach(function(b){{ if((b.getAttribute('onclick')||'').indexOf(wrapId)>=0) b.textContent=txt; }}); }}
function resetSb(){{
  var a=document.getElementById('sb_fmin'); if(a) a.value='';
  var b=document.getElementById('sb_fmax'); if(b) b.value='';
  document.querySelectorAll('.sb_t,.sb_h,.sb_d').forEach(function(c){{ c.checked=false; }});
  if(window.__sbRange) window.__sbRange();
  filterSb();
}}
function resetPd(){{
  var a=document.getElementById('pd_fmin'); if(a) a.value='';
  var b=document.getElementById('pd_fmax'); if(b) b.value='';
  document.querySelectorAll('.pd_h,.pd_m,.pd_s').forEach(function(c){{ c.checked=false; }});
  filterPd();
}}
function bindRange(pfx){{
  var smin=document.getElementById(pfx+'_rsmin'), smax=document.getElementById(pfx+'_rsmax');
  var fmin=document.getElementById(pfx+'_fmin'), fmax=document.getElementById(pfx+'_fmax');
  var fill=document.getElementById(pfx+'_rfill');
  if(!smin||!smax||!fmin||!fmax) return function(){{}};
  var lo=parseInt(smin.min,10)||0, hi=parseInt(smin.max,10)||20000;
  function cb(){{ if(pfx==='sb') filterSb(); else filterPd(); }}
  function draw(){{
    var a=parseFloat(smin.value), b=parseFloat(smax.value);
    var p1=(a-lo)/(hi-lo)*100, p2=(b-lo)/(hi-lo)*100;
    if(fill){{ fill.style.left=p1+'%'; fill.style.width=Math.max(0,p2-p1)+'%'; }}
  }}
  smin.addEventListener('input', function(){{
    if(parseFloat(smin.value)>parseFloat(smax.value)) smin.value=smax.value;
    var a=parseFloat(smin.value), b=parseFloat(smax.value);
    fmin.value=(a<=lo?'':a); fmax.value=(b>=hi?'':b); draw(); cb();
  }});
  smax.addEventListener('input', function(){{
    if(parseFloat(smax.value)<parseFloat(smin.value)) smax.value=smin.value;
    var a=parseFloat(smin.value), b=parseFloat(smax.value);
    fmin.value=(a<=lo?'':a); fmax.value=(b>=hi?'':b); draw(); cb();
  }});
  function fromNums(){{
    var a=parseFloat(fmin.value); if(isNaN(a)) a=lo;
    var b=parseFloat(fmax.value); if(isNaN(b)) b=hi;
    if(a<lo)a=lo; if(b>hi)b=hi; if(a>b){{ var t=a;a=b;b=t; }}
    smin.value=a; smax.value=b; draw(); cb();
  }}
  fmin.addEventListener('input', fromNums); fmax.addEventListener('input', fromNums);
  draw();
  return function(){{ smin.value=lo; smax.value=hi; fmin.value=''; fmax.value=''; draw(); }};
}}
function filterPd(){{
  var mn=parseFloat((document.getElementById('pd_fmin')||{{}}).value); if(isNaN(mn)) mn=0;
  var mx=parseFloat((document.getElementById('pd_fmax')||{{}}).value); if(isNaN(mx)) mx=Infinity;
  var mset={{}}; document.querySelectorAll('.pd_m:checked').forEach(function(c){{ mset[c.value]=1; }});
  var mkeys=Object.keys(mset); var mkn=mkeys.length;
  var msum=document.getElementById('pd_msum'); if(msum) msum.textContent='地铁：'+(mkn?('已选 '+mkn+' 个'):'全部');
  var sset={{}}; document.querySelectorAll('.pd_s:checked').forEach(function(c){{ sset[c.value]=1; }});
  var skeys=Object.keys(sset); var skn=skeys.length;
  var ssum=document.getElementById('pd_ssum'); if(ssum) ssum.textContent='状态：'+(skn?('已选 '+skn+' 个'):'全部');
  var hset={{}}; document.querySelectorAll('.pd_h:checked').forEach(function(c){{ hset[c.value]=1; }});
  var hkeys=Object.keys(hset); var hn=hkeys.length;
  var hsum=document.getElementById('pd_hsum'); if(hsum) hsum.textContent='户型：'+(hn?('已选 '+hn+' 个'):'全部');
  document.querySelectorAll('#pdlist .pditem').forEach(function(li){{
    var pmin=parseFloat(li.getAttribute('data-pmin'))||0;
    var pmax=parseFloat(li.getAttribute('data-pmax'))||0;
    var okP=(pmax>=mn)&&(pmin<=mx);
    var mstr=li.getAttribute('data-metro')||'';
    var okM=!mkn||mkeys.some(function(t){{ return mstr.indexOf(t)>=0; }});
    var stv=li.getAttribute('data-status')||'';
    var okS=!skn||skeys.some(function(t){{ return stv===t; }});
    var fy=li.getAttribute('data-fy')||'';
    var okF=!hn||hkeys.some(function(t){{ return fy.indexOf(t)>=0; }});
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
var compareList=[];
try{{ var _c=localStorage.getItem('cmp_list'); if(_c) compareList=JSON.parse(_c)||[]; }}catch(e){{}}
function cmpSave(){{ try{{ localStorage.setItem('cmp_list', JSON.stringify(compareList)); }}catch(e){{}} }}
function cmpKeyOf(li){{
  var name=li.getAttribute('data-name')||'';
  var src=li.closest('#sblist')?'随申办':'明珠在线';
  var right=((li.querySelector('.pdright')||{{}}).textContent||'').trim();
  var addr=(right.split('·')[0]||'').trim();
  return src+'|'+name+'|'+addr;
}}
function afterCmpChange(){{ cmpSave(); renderCompare(); syncCompareButtons(); }}
function syncCompareButtons(){{
  document.querySelectorAll('.cmp-add').forEach(function(b){{
    var li=b.closest('.pditem'); if(!li) return;
    var k=cmpKeyOf(li);
    b.textContent = compareList.some(function(x){{ return x.key===k; }}) ? '已加入' : '加入比较';
  }});
}}
function removeCompareAt(idx){{ compareList.splice(idx,1); afterCmpChange(); }}
function addCompare(ev, btn){{
  if(ev) ev.stopPropagation();
  var li=btn.closest('.pditem'); if(!li) return;
  var key=cmpKeyOf(li);
  var pos=-1; compareList.forEach(function(x,i){{ if(x.key===key) pos=i; }});
  if(pos>=0){{ removeCompareAt(pos); return; }}
  var name=li.getAttribute('data-name')||'';
  var src=li.closest('#sblist')?'随申办':'明珠在线';
  var right=((li.querySelector('.pdright')||{{}}).textContent||'').trim();
  var parts=right.split('·').map(function(s){{ return s.trim(); }});
  var addr=parts[0]||'', tel=parts[1]||'';
  var kz=((li.querySelector('.pdkz')||{{}}).textContent||'').trim();
  var fields={{}};
  li.querySelectorAll('.pdgrid .pdcell').forEach(function(c){{
    var b=c.querySelector('b'); var lab=b?b.textContent.trim():'';
    fields[lab]=c.textContent.substring((b?b.textContent:'').length).trim();
  }});
  compareList.push({{key:key,name:name,src:src,kz:kz,addr:addr,tel:tel,fields:fields}});
  afterCmpChange();
}}
var CMP_COLS=["套数","租金","户型","地铁","板块","状态","供应","受理","发布","地址","电话","介绍"];
function renderCompare(){{
  var thead=document.getElementById('cmpThead'), tbody=document.getElementById('cmpTbody');
  if(!thead||!tbody) return;
  var n=compareList.length;
  var e1=document.getElementById('cmpN'); if(e1) e1.textContent=n;
  var e2=document.getElementById('cmpFabN'); if(e2) e2.textContent=n;
  var emp=document.getElementById('cmpEmpty'); if(emp) emp.style.display=n?'none':'block';
  thead.innerHTML='<tr><th class="c-x"></th><th class="c-name">名称</th>'+CMP_COLS.map(function(c){{ return '<th>'+c+'</th>'; }}).join('')+'</tr>';
  tbody.innerHTML='';
  compareList.forEach(function(it, idx){{
    var tr=document.createElement('tr'); tr.setAttribute('draggable','true'); tr.dataset.idx=idx;
    var tdx=document.createElement('td'); tdx.className='c-x';
    var x=document.createElement('button'); x.className='cmp-x'; x.textContent='×';
    x.addEventListener('click', function(e){{ e.stopPropagation(); removeCompareAt(idx); }});
    tdx.appendChild(x); tr.appendChild(tdx);
    var tdn=document.createElement('td'); tdn.className='c-name'; tdn.textContent=it.name; tdn.title=it.name;
    var sc=document.createElement('span'); sc.className='cmp-src'; sc.textContent=it.src; tdn.appendChild(sc); tr.appendChild(tdn);
    CMP_COLS.forEach(function(c){{
      var td=document.createElement('td');
      var v=(c==='套数')?it.kz:(c==='地址')?it.addr:(c==='电话')?it.tel:(it.fields[c]||'');
      if(c==='介绍'){{
        td.className='c-intro';
        td.textContent=v;
        if(v && v.length>24){{
          var a=document.createElement('span'); a.className='c-expand'; a.textContent='展开';
          a.addEventListener('click', function(e){{ e.stopPropagation(); td.classList.toggle('expanded'); a.textContent=td.classList.contains('expanded')?'收起':'展开'; }});
          td.appendChild(a);
        }}
      }} else {{ td.textContent=v; if(v) td.title=v; }}
      tr.appendChild(td);
    }});
    tbody.appendChild(tr);
  }});
}}
var cmpDragIdx=null;
document.addEventListener('dragstart', function(e){{ var r=e.target.closest&&e.target.closest('.cmptab tr'); if(r){{ cmpDragIdx=+r.dataset.idx; r.classList.add('cmp-dragging'); }} }});
document.addEventListener('dragend', function(e){{ var r=e.target.closest&&e.target.closest('.cmptab tr'); if(r) r.classList.remove('cmp-dragging'); }});
document.addEventListener('dragover', function(e){{ if(e.target.closest&&e.target.closest('.cmp-scroll')) e.preventDefault(); }});
document.addEventListener('drop', function(e){{
  var r=e.target.closest&&e.target.closest('.cmptab tr'); if(!r||cmpDragIdx===null) return;
  e.preventDefault(); var over=+r.dataset.idx;
  if(over!==cmpDragIdx){{ var it=compareList.splice(cmpDragIdx,1)[0]; compareList.splice(over,0,it); cmpSave(); renderCompare(); }}
  cmpDragIdx=null;
}});
function toggleCompare(){{ var p=document.getElementById('cmpPanel'); if(p) p.classList.toggle('open'); }}
function clearCompare(){{ compareList=[]; afterCmpChange(); }}
renderCompare(); syncCompareButtons();
function jesc(t){{ return String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
function loadComments(c){{
  if(!c || c.dataset.loaded) return;
  c.dataset.loaded='1';
  var key=c.getAttribute('data-key');
  c.innerHTML='<div class="cmt-title">评论</div><div class="cmt-empty">加载中…</div>';
  fetch('/api/comments?key='+encodeURIComponent(key)).then(function(r){{return r.json();}}).then(function(list){{
    renderComments(c, key, list||[]);
  }}).catch(function(){{ renderComments(c, key, []); }});
}}
function renderComments(c, key, list){{
  var h='<div class="cmt-title">评论 '+list.length+'</div>';
  if(!list.length) h+='<div class="cmt-empty">还没有评论，来写第一条吧</div>';
  list.forEach(function(cm){{
    h+='<div class="cmt"><div class="cmt-meta">'+(cm.time||'')+'</div>';
    if(cm.text) h+='<div class="cmt-text">'+jesc(cm.text)+'</div>';
    if(cm.images&&cm.images.length){{ h+='<div class="cmt-imgs">'; cm.images.forEach(function(im){{ h+='<a href="/uploads/'+encodeURIComponent(im)+'" target="_blank"><img src="/uploads/'+encodeURIComponent(im)+'" loading="lazy"></a>'; }}); h+='</div>'; }}
    h+='</div>';
  }});
  c.innerHTML=h;
  var form=document.createElement('div'); form.className='cmt-form';
  form.innerHTML='<textarea rows="2" placeholder="写点对这套房源的描述 / 看房感受…"></textarea><div class="cmt-row"><input type="file" accept="image/*" multiple><button type="button" class="cmt-send">发布</button></div><div class="cmt-hint"></div>';
  c.appendChild(form);
  var ta=form.querySelector('textarea'), fi=form.querySelector('input[type=file]'), btn=form.querySelector('.cmt-send'), hint=form.querySelector('.cmt-hint');
  btn.addEventListener('click', function(){{
    if(!ta.value.trim() && !fi.files.length){{ hint.textContent='请输入文字或选择图片'; return; }}
    var fd=new FormData(); fd.append('key',key); fd.append('text',ta.value);
    for(var i=0;i<fi.files.length;i++) fd.append('images', fi.files[i]);
    btn.disabled=true; hint.textContent='发布中…';
    fetch('/api/comment',{{method:'POST',body:fd}}).then(function(r){{return r.json();}}).then(function(res){{
      if(res&&res.ok){{ c.dataset.loaded=''; loadComments(c); }} else {{ btn.disabled=false; hint.textContent=(res&&res.msg)||'发布失败'; }}
    }}).catch(function(){{ btn.disabled=false; hint.textContent='发布失败'; }});
  }});
}}
document.querySelectorAll('.pdhead').forEach(function(h){{ h.addEventListener('click', function(){{
  var item=h.parentNode; item.classList.toggle('open');
  if(item.classList.contains('open')){{ var c=item.querySelector('.cmts'); if(c) loadComments(c); }}
}}); }});
document.querySelectorAll('.pd_h,.pd_m,.pd_s').forEach(function(c){{ c.addEventListener('change', filterPd); }});
['pd_fmin','pd_fmax'].forEach(function(id){{ var el=document.getElementById(id); if(el) el.addEventListener('input', filterPd); }});
filterPd();
document.querySelectorAll('.sb_t,.sb_h,.sb_d').forEach(function(c){{ c.addEventListener('change', filterSb); }});
['sb_fmin','sb_fmax'].forEach(function(id){{ var el=document.getElementById(id); if(el) el.addEventListener('input', filterSb); }});
filterSb();
function initAmap(){{
  if(window.__amap || typeof AMap==='undefined') return;
  try{{ window.__amap=new AMap.Map('amap',{{zoom:11,center:[121.4737,31.2304]}}); }}catch(e){{}}
}}
function mapPin(color){{
  return '<div style="width:20px;height:20px;border-radius:50% 50% 50% 0;background:'+color+';transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)"></div>';
}}
function mapSuggest(){{
  var box=document.getElementById('map_sug');
  var q=(document.getElementById('map_q').value||'').trim();
  mapSel=null;
  if(q.length<2){{ box.style.display='none'; return; }}
  fetch('/api/geosuggest?q='+encodeURIComponent(q)).then(function(r){{return r.json();}}).then(function(res){{
    if(res&&res.ok===false){{
      var mb=document.getElementById('map_msg'); if(mb) mb.textContent=res.msg||'查询失败';
      box.style.display='none'; return;
    }}
    var items=(res&&res.items)||[];
    if(!items.length){{ box.style.display='none'; return; }}
    items=items.slice(0,8); box.__items=items;
    var h='';
    items.forEach(function(it,i){{
      h+='<div data-i="'+i+'"><div class="sg-n">'+jesc(it.name)+'</div><div class="sg-a">'+jesc(it.district)+' '+jesc(it.addr)+'</div></div>';
    }});
    box.innerHTML=h; box.style.display='block';
    box.querySelectorAll('div[data-i]').forEach(function(el){{
      el.addEventListener('click', function(){{
        var it=box.__items[+el.getAttribute('data-i')];
        mapSel=it;
        document.getElementById('map_q').value=it.name;
        box.style.display='none';
        doFind();
      }});
    }});
  }}).catch(function(){{ box.style.display='none'; }});
}}
function doFind(){{
  var q=(document.getElementById('map_q').value||'').trim();
  var msg=document.getElementById('map_msg');
  if(!mapSel && !q){{ msg.textContent='请输入地址'; return; }}
  var box=document.getElementById('map_sug'); if(box) box.style.display='none';
  var url = mapSel ? ('/api/nearby?lng='+mapSel.lng+'&lat='+mapSel.lat+'&n=10')
                   : ('/api/nearby?q='+encodeURIComponent(q)+'&n=10');
  msg.textContent='查询中…';
  fetch(url).then(function(r){{return r.json();}}).then(function(res){{
    if(!res||!res.ok){{ msg.textContent=(res&&res.msg)||'查询失败'; return; }}
    msg.textContent='找到 '+res.houses.length+' 套最近房源（按直线距离）';
    renderMapList(res.houses);
    if(typeof AMap==='undefined'){{ msg.textContent='地图脚本未加载（检查高德Key）'; return; }}
    initAmap();
    var mp=window.__amap; if(!mp) return;
    mp.clearMap();
    var o=res.origin;
    var m0=new AMap.Marker({{position:[o.lng,o.lat],content:mapPin('#111827'),offset:new AMap.Pixel(-10,-28),label:{{content:'搜索地址',direction:'top'}}}});
    m0.setMap(mp);
    res.houses.forEach(function(h){{
      var color=(h.src==='随申办')?'#2f6fed':'#f59e0b';
      var mk=new AMap.Marker({{position:[h.lng,h.lat],content:mapPin(color),offset:new AMap.Pixel(-10,-28),title:h.name}});
      var d=(h.dist<1000)?(h.dist+'米'):((h.dist/1000).toFixed(2)+'公里');
      var info='<div style="font-size:13px;line-height:1.7;min-width:180px"><b>'+jesc(h.name)+'</b><br>'+jesc(h.addr)+'<br>来源：'+h.src+' ｜ 距离 '+d+'<br>在售/可租 '+h.val+' 套 ｜ '+jesc(h.rent||'')+'</div>';
      mk.infoWindow=new AMap.InfoWindow({{content:info,offset:new AMap.Pixel(0,-30)}});
      mk.on('click',function(){{ mk.infoWindow.open(mp,mk.getPosition()); }});
      mk.setMap(mp);
    }});
    if(mp.setFitView) mp.setFitView();
  }}).catch(function(){{ msg.textContent='查询失败'; }});
}}
function renderMapList(hs){{
  var el=document.getElementById('map_list'); if(!el) return;
  var h='';
  hs.forEach(function(x,i){{
    var d=(x.dist<1000)?(x.dist+' 米'):((x.dist/1000).toFixed(2)+' 公里');
    var cls=(x.src==='随申办')?'tag-sb':'tag-pd';
    h+='<div class="mapitem"><span class="mapidx">'+(i+1)+'</span><div><div class="mapname">'+jesc(x.name)+'<span class="maptag '+cls+'">'+x.src+'</span></div><div class="mapmeta">'+jesc(x.addr)+' ｜ 距离 '+d+' ｜ 在售/可租 '+x.val+' 套 ｜ '+jesc(x.rent||'')+'</div></div></div>';
  }});
  el.innerHTML=h;
}}
var mapSel=null, mapDeb=null;
window.addEventListener('load', function(){{
  initAmap();
  var mq=document.getElementById('map_q');
  if(mq) mq.addEventListener('input', function(){{ mapSel=null; clearTimeout(mapDeb); mapDeb=setTimeout(mapSuggest,300); }});
  document.addEventListener('click', function(e){{
    var box=document.getElementById('map_sug');
    if(box && (!e.target.closest || !e.target.closest('.mapsb'))) box.style.display='none';
  }});
  var m=(location.search.match(/[?&]q=([^&]*)/));
  if(m){{ mq.value=decodeURIComponent(m[1]); doFind(); }}
}});
function hxPE(s){{ return String(s==null?'':s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}}); }}
function hxBtnClick(e){{
  var w=e.target.closest('.hxwrap'); if(!w) return;
  var pid=w.getAttribute('data-pid');
  var btn=w.querySelector('.hxbtn'); var st=w.querySelector('.hxstate');
  if(w._hxData){{ hxShow(w,null); return; }}
  btn.disabled=true; btn.textContent='加载户型/房源明细…';
  fetch('/api/hx?projectId='+encodeURIComponent(pid)).then(function(r){{return r.json();}}).then(function(d){{
    if(!d||!d.ok){{ btn.disabled=false; btn.textContent='该项目明细未采集'; st.textContent=(d&&d.msg)||''; return; }}
    w._hxData=d; hxRender(w);
  }}).catch(function(){{ btn.disabled=false; btn.textContent='加载失败，重试'; }});
}}
function hxRender(w){{
  var d=w._hxData;
  var btn=w.querySelector('.hxbtn'), st=w.querySelector('.hxstate'), box=w.querySelector('.hxbox');
  btn.style.display='none';
  st.innerHTML='已采集 '+d.houseCnt+' 套房源 · 含单套租金 '+d.detailCnt+' 套 · 更新 '+(d.updated||'—')+
    '　<button type="button" class="ghost" onclick="hxShow(this.closest(\'.hxwrap\'),null)">打开全部明细 ▸</button>';
  var h='<div class="hxglm">';
  (d.types||[]).forEach(function(t,i){{
    var s=t.stats||{{}}; var hasImg=t.imgs&&t.imgs.length;
    h+='<div class="hxcard" data-i="'+i+'">';
    h+='<div class="hxt">'+hxPE(t.name||('户型'+t.code))+'</div>';
    h+='<div class="hxmeta">可租 <b>'+(t.online==null?'—':t.online)+'</b> / 共 '+(t.total==null?'—':t.total)+(t.off?(' · 离线 '+t.off):'')+'</div>';
    h+='<div class="hxmeta">面积 '+(t.areaLow==null?'—':t.areaLow)+'~'+(t.areaHigh==null?'—':t.areaHigh)+'㎡　租金 '+(t.rentLow&&t.rentHigh?t.rentLow+'~'+t.rentHigh+'元':'—')+'</div>';
    h+='<div class="hxmeta">明细：可租 '+s.free+' / 已租 '+s.rented+(s.lock?(' / 锁定 '+s.lock):'')+'</div>';
    if(hasImg) h+='<img class="hximg" loading="lazy" src="'+t.imgs[0]+'">';
    else h+='<div class="hxnoimg">（户型图暂未获取到）</div>';
    h+='<div class="hxmeta" style="color:#2563eb">点击查看 '+(t.name||'')+' 房源列表 →</div>';
    h+='</div>';
  }});
  h+='</div>';
  box.innerHTML=h;
}}
function hxShow(w,t){{
  var modal=document.getElementById('hxModal'); var body=document.getElementById('hxBody');
  if(!modal) return;
  hxShow._cur={{w:w,t:t}};
  var d=w._hxData, pid=w.getAttribute('data-pid'), name=w.getAttribute('data-name');
  document.getElementById('hxTitle').textContent=(t&&t.name?('「'+t.name+'」 房源明细'):'全部房源明细')+' · '+name;
  body.innerHTML='<div class="muted" style="margin:10px 0">加载中…</div>';
  modal.style.display='flex';
  var url='/api/hxhouses?projectId='+encodeURIComponent(pid)+'&limit=200'+(hxShow._free?'&free=1':'');
  if(t) url+='&dt='+encodeURIComponent(t.code||'');
  fetch(url).then(function(r){{return r.json();}}).then(function(d){{
    if(!d||!d.ok){{ body.innerHTML='<div class="muted">'+((d&&d.msg)||'加载失败')+'</div>'; return; }}
    var rows=d.rows||[]; var nfree=0;
    var h='<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:4px 0 8px">'+
      '<button type="button" class="ghost" onclick="hxOnlyFree()">'+(hxShow._free?'看全部':'仅看未出租')+'</button>'+
      '<span class="muted">列表 '+(t?('户型「'+t.name+'」'):'全部')+' · 显示 '+rows.length+' 条</span></div>';
    if(rows.length){{
      h+='<table><thead><tr><th>门牌号</th><th>户型</th><th>面积</th><th>整租/合租</th><th>月租金</th><th>租赁状态</th><th>锁定</th></tr></thead><tbody>';
      rows.forEach(function(r){{
        if(r.rentStatus==='未出租') nfree++;
        h+='<tr><td>'+hxPE(r.room||'—')+'</td><td>'+hxPE(r.dtName||r.dt)+'</td><td>'+hxPE(r.area)+'㎡</td>'+
          '<td>'+hxPE(r.rentType||'—')+'</td>'+
          '<td>'+(r.rent!==''&&r.rent!=null?hxPE(r.rent)+' 元':'明细未采集')+'</td>'+
          '<td class="'+(r.rentStatus==='未出租'?'stfree':'strent')+'">'+hxPE(r.rentStatus||'—')+'</td>'+
          '<td>'+(r.lock?'是':'否')+'</td></tr>';
      }});
      h+='</tbody></table>';
      h='<div class="muted" style="margin:0 0 6px">其中未出租 <b>'+nfree+'</b> 套（绿色）· 租金为「明细未采集」的单套未抓取详情</div>'+h;
    }} else {{
      h='<div class="muted">（该户型暂无缓存房源）</div>';
    }}
    body.innerHTML=h;
  }}).catch(function(){{ body.innerHTML='<div class="muted">加载失败</div>'; }});
}}
function hxOnlyFree(){{
  hxShow._free=!hxShow._free;
  var c=hxShow._cur; if(c) hxShow(c.w,c.t);
}}
function hxClose(){{ document.getElementById('hxModal').style.display='none'; }}
document.addEventListener('click', function(e){{
  var t=e.target; if(!t||!t.classList) return;
  if(t.classList.contains('hxbtn')) hxBtnClick(e);
  else if(t.classList.contains('hxcard')) hxShow(t.closest('.hxwrap'), (t.closest('.hxwrap')._hxData&&t.closest('.hxwrap')._hxData.types||[])[+t.getAttribute('data-i')]);
  else if(t.id==='hxModal') hxClose();
  else if(t.closest&&t.closest('#hxModal')&&t.textContent.trim()==='关闭') hxClose();
}});
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
