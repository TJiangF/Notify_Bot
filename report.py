import os
import json
import glob
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "report.html")


def load_snapshots():
    snaps = []
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        with open(f) as fh:
            snaps.append(json.load(fh))
    return snaps


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


def build():
    snaps = load_snapshots()
    if not snaps:
        raise SystemExit("没有 data/*.json，先运行 snapshot.py")
    latest = snaps[-1]
    prev = snaps[-2] if len(snaps) >= 2 else {"ssb": [], "pd": []}

    ssb_ch = diff(prev["ssb"], latest["ssb"], "online")
    pd_ch = diff(prev["pd"], latest["pd"], "kzts")
    ssb_dist = district_stats(latest["ssb"], ssb_ch)
    pd_dist = district_stats(latest["pd"], pd_ch)

    tot_ssb = len(latest["ssb"])
    tot_ssb_online = sum(x["online"] for x in latest["ssb"])
    tot_pd = len(latest["pd"])
    tot_pd_kzts = sum(x["kzts"] for x in latest["pd"])
    date_from = snaps[0]["date"]
    date_to = latest["date"]

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
                       f"<td>{('-' + str(s['gone'])) if s['gone'] else ''}</td>"
                       f"<td>{dtag(s['d'])}</td></tr>")
    pd_table = "\n".join(pd_rows)

    def detail(source, ch):
        new, gone, inc, dec, renamed = ch
        h = []
        if new:
            h.append(f'<h4>🆕 新增（{len(new)}）</h4><ul>')
            for x in new:
                extra = f"　{esc(x.get('addr'))}　电话 {esc(x.get('tel'))}"
                h.append(f"<li><b>{esc(x['name'])}</b>（{esc(x['district'])}）{extra}</li>")
            h.append("</ul>")
        if gone:
            h.append(f'<h4>❌ 下架（{len(gone)}）</h4><ul>')
            for x in gone:
                h.append(f"<li>{esc(x['name'])}（{esc(x['district'])}）</li>")
            h.append("</ul>")
        if inc:
            h.append(f'<h4>➕ 增加（{len(inc)}）</h4><ul>')
            for x, pv, cv in inc:
                h.append(f"<li>{esc(x['name'])}（{esc(x['district'])}）：{pv} → <b>{cv}</b></li>")
            h.append("</ul>")
        if dec:
            h.append(f'<h4>➖ 减少（{len(dec)}）</h4><ul>')
            for x, pv, cv in dec:
                h.append(f"<li>{esc(x['name'])}（{esc(x['district'])}）：{pv} → <b>{cv}</b></li>")
            h.append("</ul>")
        if renamed:
            h.append(f'<h4>✏️ 改名（{len(renamed)}）</h4><ul>')
            for x, old in renamed:
                h.append(f"<li>{esc(old)} → <b>{esc(x['name'])}</b></li>")
            h.append("</ul>")
        if not h:
            h.append("<p>无变动</p>")
        return f"<h3>{source}</h3>" + "".join(h)

    trend = []
    for s in snaps:
        trend.append(f"<tr><td>{s['date']}</td><td>{len(s['ssb'])}</td>"
                     f"<td>{sum(x['online'] for x in s['ssb'])}</td>"
                     f"<td>{len(s['pd'])}</td><td>{sum(x['kzts'] for x in s['pd'])}</td></tr>")
    trend_table = "\n".join(trend)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>上海房源变化报表</title>
<style>
 body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#222}}
 .wrap{{max-width:960px;margin:0 auto;padding:24px}}
 h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#888;font-size:13px;margin-bottom:18px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
 .card{{background:#fff;border-radius:10px;padding:14px 18px;flex:1;min-width:150px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
 .card .n{{font-size:24px;font-weight:700}} .card .l{{color:#888;font-size:12px;margin-top:2px}}
 table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:22px}}
 th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #eee;font-size:14px}}
 th{{background:#fafafa;color:#666;font-weight:600}}
 .up{{color:#d33;font-weight:700}} .down{{color:#1a8f43;font-weight:700}}
 h2{{font-size:17px;margin:26px 0 10px}} h3{{font-size:15px;margin:18px 0 6px}}
 h4{{margin:10px 0 4px;font-size:13px;color:#555}} ul{{margin:4px 0 10px;padding-left:22px}} li{{font-size:13px;margin:3px 0;line-height:1.5}}
 .box{{background:#fff;border-radius:10px;padding:6px 18px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
</style></head><body><div class="wrap">
<h1>上海房源变化报表</h1>
<div class="sub">数据范围：{date_from} ~ {date_to}　｜　最新快照：{latest['date']}　｜　对比上一份快照</div>
<div class="cards">
 <div class="card"><div class="n">{tot_ssb}</div><div class="l">随申办 项目数</div></div>
 <div class="card"><div class="n">{tot_ssb_online}</div><div class="l">随申办 在线房源数</div></div>
 <div class="card"><div class="n">{tot_pd}</div><div class="l">明珠在线 项目数</div></div>
 <div class="card"><div class="n">{tot_pd_kzts}</div><div class="l">明珠在线 可租套数</div></div>
</div>

<h2>随申办 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>在线房源</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{dist_table}</tbody></table>

<h2>明珠在线 · 按行政区</h2>
<table><thead><tr><th>行政区</th><th>项目数</th><th>可租套数</th><th>新增</th><th>下架</th><th>套数变化</th></tr></thead>
<tbody>{pd_table}</tbody></table>

<h2>最新变动明细（{date_to}）</h2>
<div class="box">
{detail("随申办", ssb_ch)}
{detail("明珠在线", pd_ch)}
</div>

<h2>逐日趋势</h2>
<table><thead><tr><th>日期</th><th>随申办项目</th><th>随申办在线</th><th>明珠项目</th><th>明珠可租</th></tr></thead>
<tbody>{trend_table}</tbody></table>
</div></body></html>"""

    with open(OUT, "w") as f:
        f.write(html)
    print("已生成", OUT)
    return OUT


if __name__ == "__main__":
    build()
