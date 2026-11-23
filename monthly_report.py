#!/usr/bin/env python3
"""生成 10-21 到 11-21 的上海保租房月报（可直接分享的静态 HTML）。"""
import os
import json
import glob
import time
import math
import html as html_lib
import collections
from datetime import date, datetime

import requests
import geocode

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(DATA, "monthly.html")
MAP_OUT = os.path.join(DATA, "monthly_map.png")
START = "2026-10-21"
END = "2026-11-21"


def _load(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default if default is not None else {}


def _ids(items):
    return {str(x.get("id")): x for x in (items or []) if x.get("id")}


def _num(v):
    try:
        return int(round(float(v)))
    except Exception:
        return 0


MAP_W, MAP_H = 1200, 820


def _merc_y(lat):
    return (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2


def _unmerc_y(y):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))


def _fit(points):
    if not points:
        return (121.50, 31.24), 9
    xs, ys = [], []
    for lng, lat in points:
        xs.append((lng + 180) / 360)
        ys.append(_merc_y(lat))
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    center = ((minx + maxx) / 2 * 360 - 180, _unmerc_y((miny + maxy) / 2))
    zoom = 8
    for z in range(11, 7, -1):
        world = 256 * (2 ** z)
        if (maxx - minx) * world <= MAP_W * 0.92 and (maxy - miny) * world <= MAP_H * 0.88:
            zoom = z
            break
    return center, zoom


def _project(lng, lat, center, zoom):
    world = 256 * (2 ** zoom)
    x = (lng + 180) / 360 * world
    y = _merc_y(lat) * world
    cx = (center[0] + 180) / 360 * world
    cy = _merc_y(center[1]) * world
    return 50 + (x - cx) / MAP_W * 100, 50 + (y - cy) / MAP_H * 100


def _delta(n):
    return f"+{n:,}" if n > 0 else (f"{n:,}" if n < 0 else "0")


def main():
    b = _load(os.path.join(DATA, f"{START}.json"))
    l = _load(os.path.join(DATA, f"{END}.json"))
    coords = _load(os.path.join(DATA, "house_coords.json"))

    bs, ls = _ids(b.get("ssb")), _ids(l.get("ssb"))
    bp, lp = _ids(b.get("pd")), _ids(l.get("pd"))
    new_ssb = [ls[k] for k in ls if k not in bs]
    gone_ssb = [bs[k] for k in bs if k not in ls]
    new_pd = [lp[k] for k in lp if k not in bp]
    gone_pd = [bp[k] for k in bp if k not in lp]

    ssb_online_b = sum(_num(x.get("online")) for x in bs.values())
    ssb_online_l = sum(_num(x.get("online")) for x in ls.values())
    pd_kzts_b = sum(_num(x.get("kzts")) for x in bp.values())
    pd_kzts_l = sum(_num(x.get("kzts")) for x in lp.values())

    dist_new = collections.Counter((x.get("district") or "未知") for x in new_ssb + new_pd)
    dist_gone = collections.Counter((x.get("district") or "未知") for x in gone_ssb + gone_pd)
    dist_order = [d for d, _ in dist_new.most_common()]

    # 所有“变化项目”：新增 + 下架；地图按所有点自适应范围
    changed = []

    def add_points(src, items, kind):
        for x in items:
            pid = str(x.get("id"))
            key = f"{src}:{pid}"
            c = coords.get(key) or {}
            if c.get("lng") is None:
                c = geocode.geocode(x.get("addr") or "", x.get("district") or "")
                if c:
                    coords[key] = {"addr": x.get("addr"), "lng": c["lng"], "lat": c["lat"]}
                    time.sleep(0.12)
            if c.get("lng") is None:
                continue
            is_pd = src == "pd"
            metric = _num(x.get("kzts") if is_pd else x.get("online"))
            rent = (x.get("price") if is_pd else
                    (f'{x.get("rent_low")}–{x.get("rent_high")} 元'
                     if x.get("rent_low") is not None else ""))
            changed.append({"src": src, "id": pid, "name": x.get("name"),
                            "district": x.get("district") or "未知",
                            "addr": x.get("addr") or "", "metric": metric,
                            "rent": rent, "lng": c["lng"], "lat": c["lat"],
                            "kind": kind})

    add_points("ssb", new_ssb, "new")
    add_points("pd", new_pd, "new")
    add_points("ssb", gone_ssb, "gone")
    add_points("pd", gone_pd, "gone")

    center, zoom = _fit([(p["lng"], p["lat"]) for p in changed])
    for p in changed:
        left, top = _project(p["lng"], p["lat"], center, zoom)
        p["left"], p["top"] = round(left, 2), round(top, 2)

    try:
        json.dump(coords, open(os.path.join(DATA, "house_coords.json"), "w"), ensure_ascii=False)
    except Exception:
        pass

    try:
        map_url = ("https://restapi.amap.com/v3/staticmap"
                   f"?location={center[0]},{center[1]}&zoom={zoom}"
                   f"&size={MAP_W}*{MAP_H}&scale=2&key=" + geocode.AMAP_WEB_KEY)
        mr = requests.get(map_url, timeout=30)
        if mr.ok and mr.headers.get("content-type", "").startswith("image"):
            open(MAP_OUT, "wb").write(mr.content)
        else:
            print("静态地图下载失败：", mr.status_code, mr.text[:100])
    except Exception as e:
        print("静态地图下载失败：", repr(e))

    all_dates = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(DATA, "20*.json")))
    dates = [d for d in all_dates if START <= d <= END]
    trend = []
    for d in dates:
        cur = _load(os.path.join(DATA, d + ".json"))
        idx = all_dates.index(d)
        prev = _load(os.path.join(DATA, all_dates[idx - 1] + ".json")) if idx > 0 else {}
        cs, ps = _ids(cur.get("ssb")), _ids(prev.get("ssb"))
        cp, pp = _ids(cur.get("pd")), _ids(prev.get("pd"))
        ssb_new = sum(1 for k in cs if k not in ps)
        ssb_gone = sum(1 for k in ps if k not in cs)
        pd_new = sum(1 for k in cp if k not in pp)
        pd_gone = sum(1 for k in pp if k not in cp)
        trend.append({"d": d,
                      "ssb": len(cs), "pd": len(cp),
                      "online": sum(_num(x.get("online")) for x in cs.values()),
                      "kzts": sum(_num(x.get("kzts")) for x in cp.values()),
                      "ssb_change": ssb_new - ssb_gone,
                      "pd_change": pd_new - pd_gone})

    def cards(items, is_pd):
        h = []
        for x in sorted(items, key=lambda y: -_num(y.get("kzts") if is_pd else y.get("online"))):
            src = "明珠在线" if is_pd else "随申办"
            cls = "pd" if is_pd else "ssb"
            metric = _num(x.get("kzts") if is_pd else x.get("online"))
            label = "可租" if is_pd else "在线"
            rent = (x.get("price") if is_pd else
                    (f'{x.get("rent_low")}–{x.get("rent_high")} 元'
                     if x.get("rent_low") is not None else ""))
            h.append(
                f'<div class="new-card"><div class="new-top"><span class="badge {cls}">{src}</span>'
                f'<span class="dist">{x.get("district") or "未知"}</span></div>'
                f'<div class="new-name">{x.get("name") or ""}</div>'
                f'<div class="new-metric"><b>{metric:,}</b> 套{label}</div>'
                f'<div class="new-addr">{x.get("addr") or ""}</div>'
                f'<div class="new-rent">{rent or ""}</div></div>')
        return "".join(h)

    ssb_cards = cards(new_ssb, False)
    pd_cards = cards(new_pd, True)

    def gone_list(items):
        if not items:
            return '<div class="muted">本月无下架项目</div>'
        return "".join(
            f'<div class="gone-item"><span class="gone-dot"></span><b>{x.get("name")}</b>'
            f'<span>{x.get("district") or ""}</span>'
            f'<em>{_num(x.get("online") if x in gone_ssb else x.get("kzts")):,} 套</em></div>'
            for x in items)

    new_online = sum(_num(x.get("online")) for x in new_ssb)
    new_kzts = sum(_num(x.get("kzts")) for x in new_pd)
    top_dist = "、".join(f"{d}{n}个" for d, n in dist_new.most_common(4))
    ssb_delta = len(ls) - len(bs)
    pd_delta = len(lp) - len(bp)
    ssb_online_delta = ssb_online_l - ssb_online_b
    pd_kzts_delta = pd_kzts_l - pd_kzts_b

    summary = (
        f'<p>过去一个月，随申办项目从 <b>{len(bs)}</b> 增至 <b>{len(ls)}</b>'
        f'（{_delta(ssb_delta)}），在线房源从 <b>{ssb_online_b:,}</b> 增至 '
        f'<b>{ssb_online_l:,}</b>（{_delta(ssb_online_delta)}）；'
        f'新增 <b>{len(new_ssb)}</b> 个、下架 <b>{len(gone_ssb)}</b> 个。</p>'
        f'<p>明珠在线项目从 <b>{len(bp)}</b> 增至 <b>{len(lp)}</b>'
        f'（{_delta(pd_delta)}），可租套数从 <b>{pd_kzts_b:,}</b> 变为 '
        f'<b>{pd_kzts_l:,}</b>（{_delta(pd_kzts_delta)}）；'
        f'新增 <b>{len(new_pd)}</b> 个、下架 <b>{len(gone_pd)}</b> 个。</p>'
        f'<p>新增供应集中在 <b>{top_dist}</b>。新增项目合计带来约 '
        f'<b>{new_online:,}</b> 套随申办在线房源和 <b>{new_kzts:,}</b> 套明珠可租房源。</p>'
        f'<p>明珠新增全部位于浦东，其中 2 个为预供应项目；整体看，随申办供应仍在扩张，'
        f'明珠在线保持平稳。</p>'
    )

    kpis = f'''
    <div class="kpi"><div class="kpi-label">随申办项目</div><div class="kpi-num">{len(ls)}</div><div class="kpi-delta up">{_delta(ssb_delta)}</div></div>
    <div class="kpi"><div class="kpi-label">随申办在线</div><div class="kpi-num">{ssb_online_l:,}</div><div class="kpi-delta up">{_delta(ssb_online_delta)}</div></div>
    <div class="kpi"><div class="kpi-label">明珠项目</div><div class="kpi-num">{len(lp)}</div><div class="kpi-delta up">{_delta(pd_delta)}</div></div>
    <div class="kpi"><div class="kpi-label">明珠可租</div><div class="kpi-num">{pd_kzts_l:,}</div><div class="kpi-delta down">{_delta(pd_kzts_delta)}</div></div>
    <div class="kpi"><div class="kpi-label">新增项目</div><div class="kpi-num">{len(new_ssb)+len(new_pd)}</div><div class="kpi-delta">{len(new_ssb)} 随申办 · {len(new_pd)} 明珠</div></div>
    '''

    trend_data = {
        "labels": [x["d"][5:] for x in trend],
        "ssb": [x["ssb"] for x in trend],
        "pd": [x["pd"] for x in trend],
        "online": [x["online"] for x in trend],
        "kzts": [x["kzts"] for x in trend],
        "ssb_change": [x["ssb_change"] for x in trend],
        "pd_change": [x["pd_change"] for x in trend],
    }
    dist_data = {
        "labels": dist_order,
        "ssb": [sum(1 for x in new_ssb if (x.get("district") or "未知") == d) for d in dist_order],
        "pd": [sum(1 for x in new_pd if (x.get("district") or "未知") == d) for d in dist_order],
    }
    source_data = {"ssb": len(new_ssb), "pd": len(new_pd)}

    dots = "".join(
        f'<span class="map-dot {("gone" if p["kind"]=="gone" else p["src"])}" style="left:{p["left"]}%;top:{p["top"]}%" title="{html_lib.escape(p["name"])}"></span>'
        for p in changed)
    html = PAGE
    html = html.replace("<!--SUMMARY-->", summary)
    html = html.replace("<!--KPIS-->", kpis)
    html = html.replace("<!--NEW_SSB-->", ssb_cards)
    html = html.replace("<!--NEW_PD-->", pd_cards)
    html = html.replace("<!--SSB_NEW_COUNT-->", str(len(new_ssb)))
    html = html.replace("<!--PD_NEW_COUNT-->", str(len(new_pd)))
    html = html.replace("<!--GONE-->", gone_list(gone_ssb + gone_pd))
    html = html.replace("<!--MAP_COUNT-->", str(len(changed)))
    html = html.replace("<!--NEW_COUNT-->", str(len(new_ssb) + len(new_pd)))
    html = html.replace("<!--TREND_DATA-->", json.dumps(trend_data, ensure_ascii=False))
    html = html.replace("<!--DIST_DATA-->", json.dumps(dist_data, ensure_ascii=False))
    html = html.replace("<!--SOURCE_DATA-->", json.dumps(source_data, ensure_ascii=False))
    html = html.replace("<!--PROJECTS_DATA-->", json.dumps(changed, ensure_ascii=False))
    html = html.replace("<!--MAP_DOTS-->", dots)
    html = html.replace("<!--START-->", START)
    html = html.replace("<!--END-->", END)
    html = html.replace("<!--GENERATED-->", datetime.now().strftime("%Y-%m-%d %H:%M"))
    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"已生成 {OUT} · 变化项目地图 {len(changed)} 个 · 新增 {len(new_ssb)+len(new_pd)}")


PAGE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>上海保租房月报 · <!--START--> 至 <!--END--></title>
<meta name="description" content="过去一个月，随申办与明珠在线房源变化一览：新增项目地图、项目数量走势、在线与可租变化、区域分布。">
<style>
:root{--ink:#0f172a;--muted:#64748b;--line:#e6eaf0;--blue:#0b5cff;--orange:#ff7a00;--red:#e11d48;--bg:#f5f7fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:0 18px 40px}
.hero{background:linear-gradient(135deg,#0f2b5b 0%,#184a8c 55%,#1f6fb2 100%);color:#fff;border-radius:0 0 28px 28px;padding:42px 0 54px;margin-bottom:-34px}
.hero .wrap{padding-bottom:0}
.tag{display:inline-block;font-size:12px;letter-spacing:.14em;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);padding:6px 12px;border-radius:999px}
h1{font-size:34px;line-height:1.2;margin:14px 0 8px}
.sub{color:#cfe0f5;font-size:15px;line-height:1.8;max-width:720px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:28px}
.kpi{background:#fff;color:var(--ink);border-radius:14px;padding:14px 16px;box-shadow:0 8px 26px rgba(15,23,42,.08)}
.kpi-label{color:var(--muted);font-size:12px}
.kpi-num{font-size:26px;font-weight:750;line-height:1.25;margin-top:2px}
.kpi-delta{font-size:12px;color:var(--muted);margin-top:2px}
.kpi-delta.up{color:#0f9d58}.kpi-delta.down{color:#e0533d}
.section{margin-top:30px}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:10px}
h2{font-size:19px;margin:0}
.hint{color:var(--muted);font-size:12px}
.card{background:#fff;border-radius:16px;box-shadow:0 8px 24px rgba(15,23,42,.06);overflow:hidden}
.story{padding:22px 24px;font-size:14px;line-height:1.95;color:#334155}
.story p{margin:0 0 10px}.story b{color:var(--ink)}
.map-static{background:#eef2f7;overflow:hidden}
.map-static img{display:block;width:100%;height:auto}
.map-dots{position:absolute;inset:0;pointer-events:none}
.map-dot{position:absolute;width:16px;height:16px;border-radius:50%;border:2.5px solid #fff;transform:translate(-50%,-50%);box-shadow:0 2px 9px rgba(15,23,42,.45)}
.map-dot.ssb{background:#0b5cff;box-shadow:0 0 0 5px rgba(11,92,255,.20),0 2px 9px rgba(15,23,42,.45)}
.map-dot.pd{background:#ff7a00;box-shadow:0 0 0 5px rgba(255,122,0,.22),0 2px 9px rgba(15,23,42,.45)}
.chart-card.full{grid-column:1/-1}
#map{height:470px;width:100%;background:#eef2f7}
.map-legend{position:absolute;left:14px;bottom:14px;z-index:20;background:rgba(255,255,255,.94);border-radius:10px;padding:8px 10px;font-size:12px;color:#475569;box-shadow:0 4px 16px rgba(15,23,42,.12)}
.legend-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:1px}
.map-wrap{position:relative}
.map-note{padding:11px 16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.chart-card{padding:16px 16px 10px}
.chart-title{font-size:13px;font-weight:650;color:#334155;margin:0 0 8px}
.chart-box{height:230px}
.new-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;padding:16px}
.new-grid.small{grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:8px;padding:12px}
.new-grid.small .new-card{padding:9px}
.new-grid.small .new-name{font-size:12px;min-height:34px}
.subhead{font-size:14px;font-weight:650;margin:14px 0 8px;color:#334155}
.subhead span{display:inline-block;background:#eef4ff;color:#2563eb;border-radius:999px;font-size:11px;padding:2px 8px;margin-left:4px}
.map-dot.gone{background:#e11d48;box-shadow:0 0 0 4px rgba(225,29,72,.18),0 2px 9px rgba(15,23,42,.45)}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.new-card{border:1px solid var(--line);border-radius:12px;padding:12px;background:#fff;min-width:0}
.new-top{display:flex;justify-content:space-between;align-items:center;gap:6px}
.badge{font-size:10px;color:#fff;border-radius:999px;padding:2px 7px;white-space:nowrap}
.badge.ssb{background:var(--blue)}.badge.pd{background:var(--orange)}
.dist{font-size:10px;color:var(--muted);white-space:nowrap}
.new-name{font-weight:650;font-size:13px;margin:8px 0 2px;line-height:1.45;min-height:38px}
.new-metric{font-size:12px;color:var(--muted)}.new-metric b{font-size:18px;color:var(--ink)}
.new-addr{font-size:10px;color:#94a3b8;line-height:1.5;margin-top:5px;max-height:30px;overflow:hidden}
.new-rent{font-size:10px;color:#b45309;margin-top:4px}
.removed{padding:16px 20px}
.gone-item{display:flex;align-items:center;gap:8px;font-size:13px;padding:7px 0;border-bottom:1px dashed #eef1f5;color:#475569}
.gone-item:last-child{border-bottom:0}
.gone-dot{width:7px;height:7px;border-radius:50%;background:#cbd5e1;flex:0 0 auto}
.gone-item b{font-weight:600;color:#334155}.gone-item span{color:var(--muted);font-size:12px}.gone-item em{margin-left:auto;font-style:normal;color:#94a3b8;font-size:12px}
.footer{text-align:center;color:#94a3b8;font-size:11px;line-height:1.8;padding:30px 0 0}
.footer a{color:#94a3b8}
@media(max-width:900px){.wrap{max-width:100%;padding:0 12px 28px}.hero{padding:30px 0 44px;border-radius:0 0 20px 20px}h1{font-size:28px}.sub{font-size:13px}.kpis{grid-template-columns:repeat(2,1fr);gap:8px}.kpi{padding:11px 12px}.kpi-num{font-size:22px}.new-grid{grid-template-columns:repeat(3,1fr)}.new-grid.small{grid-template-columns:repeat(3,1fr)}.chart-grid{grid-template-columns:1fr}.chart-box{height:220px}.section{margin-top:22px}}
@media(max-width:600px){.wrap{padding:0 10px 24px}.hero{padding:24px 0 38px}h1{font-size:24px;line-height:1.25}.tag{font-size:10px}.kpis{grid-template-columns:1fr 1fr}.kpi-label{font-size:11px}.kpi-num{font-size:20px}.kpi-delta{font-size:10px}.new-grid,.new-grid.small{grid-template-columns:1fr 1fr}.new-name{font-size:11px;min-height:auto}.new-card{padding:8px}.new-addr,.new-rent{font-size:9px}.chart-box{height:200px}.map-note{font-size:10px}.section-head{flex-direction:column;align-items:flex-start;gap:2px}h2{font-size:17px}.hint{font-size:10px}.story{padding:16px 14px;font-size:13px;line-height:1.85}}
</style>
</head>
<body>
<div class="hero"><div class="wrap">
<span class="tag">上海保租房 · 月度观察</span>
<h1>过去一个月，房源发生了什么？</h1>
<div class="sub"><!--START--> — <!--END-->　｜　随申办 × 明珠在线　｜　新增项目地图、数量走势与区域变化</div>
<div class="kpis"><!--KPIS--></div>
</div></div>
<div class="wrap">
<div class="section"><div class="card"><div class="story"><!--SUMMARY--></div></div></div>

<div class="section">
  <div class="section-head"><h2>变化项目地图</h2><div class="hint">地图展示 <!--MAP_COUNT--> 个变化项目（新增 + 下架）· 圆点标注</div></div>
  <div class="card">
    <div class="map-wrap map-static"><img src="/monthly/map.png" alt="上海新增房源项目地图">
      <div class="map-dots"><!--MAP_DOTS--></div>
      <div class="map-legend"><span class="legend-dot" style="background:#0b5cff"></span>随申办新增　<span class="legend-dot" style="background:#ff7a00"></span>明珠新增　<span class="legend-dot" style="background:#e11d48"></span>下架</div>
    </div>
    <div class="map-note">静态地图：蓝色/橙色为新增项目，灰色为下架项目；地图范围已按全部变化项目自适应。</div>
  </div>
</div>

<div class="section">
  <div class="section-head"><h2>一个月走势</h2><div class="hint">每日项目数量与房源供应变化</div></div>
  <div class="chart-grid">
    <div class="card chart-card full"><div class="chart-title">项目数每日变化（新增 - 下架）</div><div class="chart-box"><canvas id="changeChart"></canvas></div></div>
    <div class="card chart-card full"><div class="chart-title">在线 / 可租房源走势</div><div class="chart-box"><canvas id="supplyChart"></canvas></div></div>
  </div>
</div>

<div class="section">
  <div class="section-head"><h2>新增项目分布</h2><div class="hint">按行政区统计新增数量</div></div>
  <div class="chart-grid">
    <div class="card chart-card"><div class="chart-title">行政区新增</div><div class="chart-box"><canvas id="districtChart"></canvas></div></div>
    <div class="card chart-card"><div class="chart-title">新增来源占比</div><div class="chart-box"><canvas id="sourceChart"></canvas></div></div>
  </div>
</div>

<div class="section">
  <div class="section-head"><h2>新增亮点</h2><div class="hint">全量展示，按当前在线/可租套数排序</div></div>
  <div class="new-block"><div class="subhead">随申办新增 <span><!--SSB_NEW_COUNT--></span></div><div class="card"><div class="new-grid small"><!--NEW_SSB--></div></div></div>
  <div class="new-block"><div class="subhead">明珠在线新增 <span><!--PD_NEW_COUNT--></span></div><div class="card"><div class="new-grid small"><!--NEW_PD--></div></div></div>
</div>

<div class="section">
  <div class="section-head"><h2>本月下架</h2><div class="hint">下架项目数量较少，整体供应仍在扩张</div></div>
  <div class="card removed"><!--GONE--></div>
</div>

<div class="footer">数据来源：随申办 · 明珠在线　｜　统计区间 <!--START--> 至 <!--END-->　｜　生成时间 <!--GENERATED--><br>
<a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">苏ICP备2026080883号</a></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const TREND = <!--TREND_DATA-->;
const DIST = <!--DIST_DATA-->;
const SOURCE = <!--SOURCE_DATA-->;
const PROJECTS = <!--PROJECTS_DATA-->;
Chart.defaults.font.family = '-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif';
Chart.defaults.color = '#64748b';
new Chart(document.getElementById('changeChart'), {type:'line',data:{labels:TREND.labels,datasets:[
 {label:'随申办净增',data:TREND.ssb_change,borderColor:'#0b5cff',backgroundColor:'rgba(11,92,255,.08)',fill:false,tension:.25,borderWidth:2.5,pointRadius:2.5,pointBackgroundColor:'#0b5cff'},
 {label:'明珠在线净增',data:TREND.pd_change,borderColor:'#ff7a00',backgroundColor:'rgba(255,122,0,.08)',fill:false,tension:.25,borderWidth:2.5,pointRadius:2.5,pointBackgroundColor:'#ff7a00'}
]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{boxWidth:10,boxHeight:10}}},scales:{x:{ticks:{maxTicksLimit:8,font:{size:10}}},y:{beginAtZero:true,ticks:{maxTicksLimit:5,font:{size:10}}}}}});
new Chart(document.getElementById('supplyChart'), {type:'line',data:{labels:TREND.labels,datasets:[
 {label:'随申办在线',data:TREND.online,borderColor:'#0f9d58',backgroundColor:'rgba(15,157,88,.08)',fill:true,tension:.3,borderWidth:2,pointRadius:0,yAxisID:'y'},
 {label:'明珠可租',data:TREND.kzts,borderColor:'#8b5cf6',backgroundColor:'rgba(139,92,246,.08)',fill:true,tension:.3,borderWidth:2,pointRadius:0,yAxisID:'y1'}
]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{boxWidth:10,boxHeight:10}}},scales:{x:{ticks:{maxTicksLimit:7,font:{size:10}}},y:{position:'left',beginAtZero:false,ticks:{maxTicksLimit:5,font:{size:10}}},y1:{position:'right',beginAtZero:false,grid:{drawOnChartArea:false},ticks:{maxTicksLimit:5,font:{size:10}}}}}});
new Chart(document.getElementById('districtChart'), {type:'bar',data:{labels:DIST.labels,datasets:[
 {label:'随申办',data:DIST.ssb,backgroundColor:'#2563eb',borderRadius:4},
 {label:'明珠在线',data:DIST.pd,backgroundColor:'#f59e0b',borderRadius:4}
]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:10,boxHeight:10}}},scales:{x:{stacked:true,ticks:{font:{size:10}}},y:{stacked:true,beginAtZero:true,ticks:{maxTicksLimit:5,font:{size:10}}}}}});
new Chart(document.getElementById('sourceChart'), {type:'doughnut',data:{labels:['随申办','明珠在线'],datasets:[{data:[SOURCE.ssb,SOURCE.pd],backgroundColor:['#2563eb','#f59e0b'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom',labels:{boxWidth:10,boxHeight:10}}}}});
</script>
</body></html>
'''


if __name__ == "__main__":
    main()
