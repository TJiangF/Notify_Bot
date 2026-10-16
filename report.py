import os
import json
import glob
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "report.html")


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
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        ssb_d = sorted({x["district"] for x in ssb})
        ssb_filter = "".join(f'<label><input type="checkbox" class="ga" value="{esc(d)}"> {esc(d)}</label>' for d in ssb_d)
        ssb_items = "".join(
            f'<li data-d="{esc(x["district"])}"><b>{esc(x["name"])}</b>（{esc(x["district"])}）'
            f'　在线 {x["online"]} 套　{esc(x.get("addr"))}　电话 {esc(x.get("tel"))}</li>'
            for x in sorted(ssb, key=lambda a: (a["district"], -(a["online"] or 0))))
        pd = latest["pd"]
        pd_d = sorted({x["district"] for x in pd})
        pd_filter = "".join(f'<label><input type="checkbox" class="ga" value="{esc(d)}"> {esc(d)}</label>' for d in pd_d)
        pd_items = "".join(
            f'<li data-d="{esc(x["district"])}"><b>{esc(x["name"])}</b>（{esc(x["district"])}）'
            f'　可租 {x["kzts"]} 套　{esc(x.get("addr"))}　电话 {esc(x.get("tel"))} [{esc(x.get("status"))}]</li>'
            for x in sorted(pd, key=lambda a: -(a["kzts"] or 0)))
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
 body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#222}}
 .wrap{{max-width:960px;margin:0 auto;padding:24px}}
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
 .filters{{display:flex;flex-wrap:wrap;gap:8px 16px;padding:10px 0;border-bottom:1px solid #eee;margin-bottom:6px}}
 .filters label{{font-size:13px;cursor:pointer;user-select:none;white-space:nowrap}}
 .filters input{{margin-right:4px;vertical-align:middle}}
 .grp{{margin:6px 0}} .alllist{{margin:6px 0 2px;padding-left:22px}} .alllist li{{font-size:13px;margin:3px 0;line-height:1.5}}
 .emptyhint{{color:#999;font-size:13px;padding:8px 0}}
</style></head><body><div class="wrap">
<h1>上海房源变化报表</h1>
<div class="sub">{selector if opts else ''}<div>{sent}　｜　数据每 30 分钟更新，页面每 30 分钟自动刷新</div></div>
<div class="cards">
 <div class="card"><div class="n">{c_ssb}</div><div class="l">随申办 项目数</div></div>
 <div class="card"><div class="n">{c_ssb_online}</div><div class="l">随申办 在线房源数</div></div>
 <div class="card"><div class="n">{c_pd}</div><div class="l">明珠在线 项目数</div></div>
 <div class="card"><div class="n">{c_pd_kzts}</div><div class="l">明珠在线 可租套数</div></div>
 <div class="card"><div class="n">{c_notice}</div><div class="l">随申办 供应预告</div></div>
</div>

<h2>随申办 · 供应预告（{len(notice)}）</h2>
<table><thead><tr><th>项目</th><th>计划供应日</th><th>租金</th><th>地址</th><th>电话</th><th>运营单位</th></tr></thead>
<tbody>{notice_table}</tbody></table>

<h2>随申办 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>在线房源</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{dist_table}</tbody></table>

<h2>明珠在线 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>可租套数</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{pd_table}</tbody></table>

<h2>变动明细（当前 vs 基线）</h2>
<div class="box">
{detail("随申办", ssb_ch)}
{detail("明珠在线", pd_ch)}
</div>

<h2>全部房源明细</h2>
<div class="box">
<div class="allbox">
<h3>随申办</h3>
<div class="filters">{ssb_filter}</div>
<div class="emptyhint">勾选上方行政区以显示对应房源</div>
<ul class="alllist">{ssb_items}</ul>
</div>
<div class="allbox">
<h3>明珠在线</h3>
<div class="filters">{pd_filter}</div>
<div class="emptyhint">勾选上方行政区以显示对应房源</div>
<ul class="alllist">{pd_items}</ul>
</div>
</div>

<h2>逐日趋势</h2>
<table><thead><tr><th>日期</th><th>随申办项目</th><th>随申办在线</th><th>明珠项目</th><th>明珠可租</th></tr></thead>
<tbody>{trend_table}</tbody></table>
</div>
<script>
function applyAll(){{
  document.querySelectorAll('.allbox').forEach(function(box){{
    var checked = new Set([].slice.call(box.querySelectorAll('input.ga:checked')).map(function(x){{return x.value;}}));
    box.querySelectorAll('li[data-d]').forEach(function(li){{
      li.style.display = checked.has(li.getAttribute('data-d')) ? '' : 'none';
    }});
    var hint = box.querySelector('.emptyhint');
    if (hint) hint.style.display = checked.size > 0 ? 'none' : '';
  }});
}}
document.querySelectorAll('input.ga').forEach(function(el){{ el.addEventListener('change', applyAll); }});
applyAll();
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
