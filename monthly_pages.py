#!/usr/bin/env python3
"""生成 A4 竖版月报页面（不含地图），供截图/分享。"""
import os
import json
import glob
import html as H
import collections

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUTDIR = os.path.join(DATA, "monthly_pages")
START, END = "2026-10-25", "2026-11-25"
TITLE = "10-11月上海保租房+人才补贴住房情况更新"


def load(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default if default is not None else {}


def ids(items):
    return {str(x.get("id")): x for x in (items or []) if x.get("id")}


def num(v):
    try:
        return int(round(float(v)))
    except Exception:
        return 0


def delta(n):
    return f"+{n:,}" if n > 0 else f"{n:,}"


CSS = r"""
:root{--ink:#0f172a;--muted:#64748b;--line:#e6eaf0;--blue:#0b5cff;--orange:#ff7a00;--red:#e11d48}
*{box-sizing:border-box}
html,body{margin:0;padding:0;width:1240px;height:1754px;overflow:hidden;background:#fff;color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.page{width:1240px;height:1754px;padding:44px 48px 32px;position:relative;display:flex;flex-direction:column}
.pageno{position:absolute;right:48px;bottom:22px;font-size:16px;color:#94a3b8}
.topline{font-size:17px;color:#94a3b8;letter-spacing:.04em;margin-bottom:18px}
.cover{background:linear-gradient(135deg,#0d2b5c 0%,#14508f 55%,#1c74b8 100%);color:#fff;
 border-radius:0 0 26px 26px;margin:-44px -48px 0;padding:54px 48px 42px}
.tag{display:inline-block;font-size:15px;letter-spacing:.16em;background:rgba(255,255,255,.14);
 border:1px solid rgba(255,255,255,.28);padding:8px 16px;border-radius:999px}
h1{font-size:54px;line-height:1.24;margin:20px 0 14px;letter-spacing:-.01em}
.date{font-size:23px;color:#d7e7fa;line-height:1.7}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:28px 0 20px}
.kpi{border:1px solid var(--line);border-radius:14px;padding:16px;background:#fff}
.kpi-label{font-size:17px;color:var(--muted)}
.kpi-num{font-size:38px;font-weight:750;line-height:1.2;margin-top:3px}
.kpi-delta{font-size:16px;color:var(--muted);margin-top:2px}
.kpi-delta.up{color:#0f9d58}.kpi-delta.down{color:var(--red)}
h2{font-size:42px;margin:0 0 6px;letter-spacing:-.01em}
.sub{font-size:21px;color:var(--muted);line-height:1.65;margin:0 0 16px}
.summary{font-size:25px;line-height:1.85;color:#334155;border:1px solid var(--line);border-radius:16px;padding:25px 28px;background:#fff}
.summary p{margin:0 0 12px}.summary p:last-child{margin-bottom:0}.summary b{color:var(--ink)}
.foot{margin-top:auto;border-top:1px solid var(--line);padding-top:14px;font-size:15px;color:#94a3b8;line-height:1.7}
.chart-block{margin-top:14px}
.chart-title{font-size:25px;font-weight:650;margin:0 0 8px;color:#334155}
.chart-holder{height:620px;border:1px solid var(--line);border-radius:16px;padding:10px 12px;background:#fff}
.chart-row{display:grid;grid-template-columns:1.35fr .9fr;gap:16px;margin-top:8px}
.chart-row .chart-holder{height:700px}
.insights{margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:12px}
.insight{border:1px solid var(--line);border-radius:14px;padding:17px 19px;font-size:21px;line-height:1.7;color:#334155;background:#fff}
.insight b{color:var(--ink)}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}
.card{border:1px solid var(--line);border-radius:14px;padding:16px 18px;background:#fff;min-height:210px;display:flex;flex-direction:column;justify-content:center}
.card-top{display:flex;justify-content:space-between;align-items:center}
.badge{font-size:14px;color:#fff;border-radius:999px;padding:4px 11px}
.badge.ssb{background:var(--blue)}.badge.pd{background:var(--orange)}
.dist{font-size:16px;color:var(--muted)}
.name{font-size:26px;font-weight:700;line-height:1.35;margin:8px 0 4px}
.metric{font-size:22px;color:var(--muted)}.metric b{font-size:34px;color:var(--ink)}
.addr{font-size:17px;color:#94a3b8;line-height:1.5;margin-top:6px;max-height:52px;overflow:hidden}
.rent{font-size:17px;color:#b45309;margin-top:5px}
.removed{display:grid;gap:10px;margin-top:10px}
.gone{display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-radius:12px;padding:16px 19px;font-size:21px;color:#334155}
.gone .dot{width:11px;height:11px;border-radius:50%;background:var(--red);flex:0 0 auto}
.gone em{margin-left:auto;font-style:normal;color:#94a3b8}
.note{font-size:16px;color:#94a3b8;line-height:1.75;margin-top:14px}
.takeaways{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px}
.takeaways.three{grid-template-columns:repeat(3,1fr)}
.takeaway{border:1px solid var(--line);border-radius:16px;padding:20px 22px;background:#fff}
.tk-num{font-size:54px;font-weight:800;line-height:1;color:var(--blue)}
.takeaway:nth-child(2) .tk-num{color:var(--orange)}
.takeaway:nth-child(4) .tk-num{color:var(--red)}
.tk-label{font-size:23px;font-weight:650;margin-top:9px}
.tk-sub{font-size:18px;color:var(--muted);margin-top:3px}
.conclusion{margin-top:18px;border:1px solid #cfe0ff;background:#f5f9ff;border-radius:16px;padding:20px 24px;font-size:25px;line-height:1.75;color:#334155}
.conclusion b{color:#0b5cff}
.pgroup{margin-top:10px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}
.pgroup-head{display:flex;align-items:baseline;gap:12px;background:#eef5ff;padding:7px 16px;font-size:21px;font-weight:700;color:#0d2b5c}
.pgroup-head .cnt{font-size:16px;color:#64748b;font-weight:500;margin-left:auto}
.prows{display:flex;flex-direction:column}
.prow{display:flex;align-items:center;gap:18px;padding:7px 16px;border-top:1px solid #eef2f7}
.prow-main{flex:1;min-width:0}
.pname{font-size:23px;font-weight:650;line-height:1.28;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.paddr{font-size:16px;color:#94a3b8;line-height:1.45;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.prow-side{flex:0 0 330px;text-align:right}
.pmetric{font-size:18px;color:#64748b}.pmetric b{font-size:30px;color:var(--ink)}
.prent{font-size:16px;color:#b45309;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
"""


def page(title, body, scripts="", no=1, top=True):
    head = f'<div class="topline">{H.escape(TITLE)}</div>' if top else ""
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=1240, initial-scale=1">
<title>{H.escape(title)}</title><style>{CSS}</style></head><body>
<div class="page">{head}{body}<div class="pageno">{no} / 7</div></div>
{scripts}</body></html>'''


def main():
    b = load(os.path.join(DATA, START + ".json"))
    l = load(os.path.join(DATA, END + ".json"))
    bs, ls = ids(b.get("ssb")), ids(l.get("ssb"))
    bp, lp = ids(b.get("pd")), ids(l.get("pd"))
    new_ssb = [ls[k] for k in ls if k not in bs]
    gone_ssb = [bs[k] for k in bs if k not in ls]
    new_pd = [lp[k] for k in lp if k not in bp]
    gone_pd = [bp[k] for k in bp if k not in lp]
    new_pd.sort(key=lambda x: -num(x.get("kzts")))
    new_ssb.sort(key=lambda x: -num(x.get("online")))

    dist = collections.Counter((x.get("district") or "未知") for x in new_ssb + new_pd)
    dist_order = [d for d, _ in dist.most_common()]
    ssb_online_b = sum(num(x.get("online")) for x in bs.values())
    ssb_online_l = sum(num(x.get("online")) for x in ls.values())
    pd_kzts_b = sum(num(x.get("kzts")) for x in bp.values())
    pd_kzts_l = sum(num(x.get("kzts")) for x in lp.values())

    all_dates = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(DATA, "20*.json")))
    dates = [d for d in all_dates if START <= d <= END]
    trend = []
    for d in dates:
        cur = load(os.path.join(DATA, d + ".json"))
        i = all_dates.index(d)
        prev = load(os.path.join(DATA, all_dates[i - 1] + ".json")) if i > 0 else {}
        cs, ps = ids(cur.get("ssb")), ids(prev.get("ssb"))
        cp, pp = ids(cur.get("pd")), ids(prev.get("pd"))
        trend.append({"d": d,
                      "ssb": len(cs), "pd": len(cp),
                      "online": sum(num(x.get("online")) for x in cs.values()),
                      "kzts": sum(num(x.get("kzts")) for x in cp.values()),
                      "ssb_change": sum(1 for k in cs if k not in ps) - sum(1 for k in ps if k not in cs),
                      "pd_change": sum(1 for k in cp if k not in pp) - sum(1 for k in pp if k not in cp)})

    top_dist = "、".join(f"{d} {n} 个" for d, n in dist.most_common(4))
    ssb_d = len(ls) - len(bs)
    pd_d = len(lp) - len(bp)
    so_d = ssb_online_l - ssb_online_b
    pk_d = pd_kzts_l - pd_kzts_b
    new_online = sum(num(x.get("online")) for x in new_ssb)
    new_kzts = sum(num(x.get("kzts")) for x in new_pd)

    summary = f'''<div class="summary">
<p>过去一个月，随申办项目从 <b>{len(bs)}</b> 增至 <b>{len(ls)}</b>（{delta(ssb_d)}），在线房源从 <b>{ssb_online_b:,}</b> 增至 <b>{ssb_online_l:,}</b>（{delta(so_d)}）；新增 <b>{len(new_ssb)}</b> 个、下架 <b>{len(gone_ssb)}</b> 个。</p>
<p>明珠在线项目从 <b>{len(bp)}</b> 增至 <b>{len(lp)}</b>（{delta(pd_d)}），可租套数从 <b>{pd_kzts_b:,}</b> 变为 <b>{pd_kzts_l:,}</b>（{delta(pk_d)}）；新增 <b>{len(new_pd)}</b> 个、下架 <b>{len(gone_pd)}</b> 个。</p>
<p>新增供应集中在 <b>{top_dist}</b>；新增项目合计带来约 <b>{new_online:,}</b> 套随申办在线房源和 <b>{new_kzts:,}</b> 套明珠可租房源。</p>
<p>明珠新增全部位于浦东，其中 2 个为预供应；整体看，随申办供应仍在扩张，明珠在线保持平稳。</p>
</div>'''

    kpis = f'''<div class="kpis">
<div class="kpi"><div class="kpi-label">随申办项目</div><div class="kpi-num">{len(ls)}</div><div class="kpi-delta up">{delta(ssb_d)}</div></div>
<div class="kpi"><div class="kpi-label">随申办在线</div><div class="kpi-num">{ssb_online_l:,}</div><div class="kpi-delta up">{delta(so_d)}</div></div>
<div class="kpi"><div class="kpi-label">明珠项目</div><div class="kpi-num">{len(lp)}</div><div class="kpi-delta up">{delta(pd_d)}</div></div>
<div class="kpi"><div class="kpi-label">明珠可租</div><div class="kpi-num">{pd_kzts_l:,}</div><div class="kpi-delta down">{delta(pk_d)}</div></div>
<div class="kpi"><div class="kpi-label">新增项目</div><div class="kpi-num">{len(new_ssb)+len(new_pd)}</div><div class="kpi-delta">{len(new_ssb)} 随申办 · {len(new_pd)} 明珠</div></div>
</div>'''

    p1 = page(TITLE, f'''<div class="cover"><span class="tag">上海保租房 · 月度观察</span>
<h1>{TITLE}</h1><div class="date">2026-10-25 — 2026-11-25　｜　随申办 × 明珠在线</div></div>
{kpis}{summary}
<div class="takeaways">
<div class="takeaway"><div class="tk-num">16</div><div class="tk-label">杨浦区新增项目</div><div class="tk-sub">全市最多，领跑本月供应</div></div>
<div class="takeaway"><div class="tk-num">9</div><div class="tk-label">浦东新区新增项目</div><div class="tk-sub">明珠在线 3 个，2 个为预供应</div></div>
<div class="takeaway"><div class="tk-num">+2,811</div><div class="tk-label">随申办在线房源净增</div><div class="tk-sub">在线总量升至 313,321 套</div></div>
<div class="takeaway"><div class="tk-num">3</div><div class="tk-label">本月下架项目</div><div class="tk-sub">整体供应仍在净扩张</div></div>
</div>
<div class="conclusion"><b>一句话总结：</b>随申办供应继续放量，杨浦与浦东贡献近六成新增；明珠在线保持平稳。</div>
<div class="note" style="font-size:16px;color:#64748b">关键词：杨浦领跑 · 浦东扩容 · 在线净增 · 供应扩张</div>
<div class="foot">数据来源：随申办 · 明珠在线　｜　统计区间：{START} 至 {END}　｜　关注新增、下架、在线与可租变化。</div>''', no=1, top=False)

    tr = {"labels": [x["d"][5:] for x in trend],
          "ssb_change": [x["ssb_change"] for x in trend],
          "pd_change": [x["pd_change"] for x in trend],
          "online": [x["online"] for x in trend],
          "kzts": [x["kzts"] for x in trend]}

    chart_js = '''<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const TREND=%s;
Chart.defaults.font.family='-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif';
Chart.defaults.color='#64748b';
new Chart(document.getElementById('changeChart'),{type:'line',data:{labels:TREND.labels,datasets:[
{label:'随申办净增',data:TREND.ssb_change,borderColor:'#0b5cff',backgroundColor:'rgba(11,92,255,.08)',fill:false,tension:.25,borderWidth:4,pointRadius:4,pointBackgroundColor:'#0b5cff'},
{label:'明珠在线净增',data:TREND.pd_change,borderColor:'#ff7a00',backgroundColor:'rgba(255,122,0,.08)',fill:false,tension:.25,borderWidth:4,pointRadius:4,pointBackgroundColor:'#ff7a00'}
]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:12,boxHeight:12,font:{size:20}}}},scales:{x:{ticks:{maxTicksLimit:8,font:{size:18}}},y:{beginAtZero:true,ticks:{font:{size:18}}}}}});
new Chart(document.getElementById('supplyChart'),{type:'line',data:{labels:TREND.labels,datasets:[
{label:'随申办在线',data:TREND.online,borderColor:'#0f9d58',backgroundColor:'rgba(15,157,88,.08)',fill:true,tension:.3,borderWidth:4,pointRadius:0,yAxisID:'y'},
{label:'明珠可租',data:TREND.kzts,borderColor:'#8b5cf6',backgroundColor:'rgba(139,92,246,.08)',fill:true,tension:.3,borderWidth:4,pointRadius:0,yAxisID:'y1'}
]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:12,boxHeight:12,font:{size:20}}}},scales:{x:{ticks:{maxTicksLimit:8,font:{size:18}}},y:{position:'left',ticks:{font:{size:18}}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{font:{size:18}}}}}});
</script>''' % json.dumps(tr, ensure_ascii=False)

    p2 = page("一个月走势", '''<h2>一个月走势</h2><p class="sub">逐日项目数变化，以及在线房源与明珠可租房源走势。</p>
<div class="chart-block"><div class="chart-title">项目数每日变化（新增 - 下架）</div><div class="chart-holder"><canvas id="changeChart"></canvas></div></div>
<div class="chart-block"><div class="chart-title">在线 / 可租房源走势</div><div class="chart-holder"><canvas id="supplyChart"></canvas></div></div>
<div class="conclusion"><b>观察：</b>项目数在 11 月中旬出现集中新增，在线房源同步抬升；月末明珠可租小幅回落。</div>''', chart_js, no=2)

    dist_data = {"labels": dist_order,
                 "ssb": [sum(1 for x in new_ssb if (x.get("district") or "未知") == d) for d in dist_order],
                 "pd": [sum(1 for x in new_pd if (x.get("district") or "未知") == d) for d in dist_order]}
    dist_js = '''<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const DIST=%s;
Chart.defaults.font.family='-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif';
new Chart(document.getElementById('districtChart'),{type:'bar',data:{labels:DIST.labels,datasets:[
{label:'随申办',data:DIST.ssb,backgroundColor:'#0b5cff',borderRadius:5},
{label:'明珠在线',data:DIST.pd,backgroundColor:'#ff7a00',borderRadius:5}
]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:13,boxHeight:13,font:{size:20}}}},scales:{x:{stacked:true,ticks:{font:{size:18}}},y:{stacked:true,beginAtZero:true,ticks:{font:{size:18}}}}}});
new Chart(document.getElementById('sourceChart'),{type:'doughnut',data:{labels:['随申办','明珠在线'],datasets:[{data:[%d,%d],backgroundColor:['#0b5cff','#ff7a00'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%%',plugins:{legend:{position:'bottom',labels:{boxWidth:13,boxHeight:13,font:{size:20}}}}}});
</script>''' % (json.dumps(dist_data, ensure_ascii=False), len(new_ssb), len(new_pd))

    p3 = page("新增项目分布", f'''<h2>新增项目分布</h2><p class="sub">全区新增 {len(new_ssb)+len(new_pd)} 个项目，随申办 {len(new_ssb)} 个、明珠在线 {len(new_pd)} 个。</p>
<div class="chart-row"><div><div class="chart-title">行政区新增</div><div class="chart-holder"><canvas id="districtChart"></canvas></div></div>
<div><div class="chart-title">新增来源占比</div><div class="chart-holder"><canvas id="sourceChart"></canvas></div></div></div>
<div class="insights"><div class="insight"><b>杨浦区</b>新增最多，共 16 个，主要集中在新江湾城周边。</div>
<div class="insight"><b>浦东新区</b>新增 9 个，其中明珠在线 3 个，2 个为预供应。</div>
<div class="insight"><b>奉贤区</b>新增 5 个，是外环外新增供应的主要区域。</div>
<div class="insight"><b>整体节奏</b>新增项目 43 个，下架仅 3 个，供应仍在净扩张。</div></div>
<div class="conclusion"><b>一句话总结：</b>杨浦领跑新增，浦东继续扩容；随申办在线房源净增 2,811 套，整体供应保持扩张。</div>
<div class="takeaways three" style="margin-top:14px">
<div class="takeaway"><div class="tk-num">40</div><div class="tk-label">随申办新增</div><div class="tk-sub">占新增项目 93%</div></div>
<div class="takeaway"><div class="tk-num">3</div><div class="tk-label">明珠在线新增</div><div class="tk-sub">全部位于浦东</div></div>
<div class="takeaway"><div class="tk-num">3</div><div class="tk-label">本月下架</div><div class="tk-sub">净增远大于下架</div></div>
</div>''', dist_js, no=3)

    # card pages: 14, 13, 13
    def card(x, is_pd):
        src = "明珠在线" if is_pd else "随申办"
        cls = "pd" if is_pd else "ssb"
        metric = num(x.get("kzts") if is_pd else x.get("online"))
        label = "可租" if is_pd else "在线"
        rent = x.get("price") if is_pd else (
            f'{x.get("rent_low")}–{x.get("rent_high")} 元' if x.get("rent_low") is not None else "")
        return f'''<div class="card"><div class="card-top"><span class="badge {cls}">{src}</span><span class="dist">{H.escape(x.get("district") or "未知")}</span></div>
<div class="name">{H.escape(x.get("name") or "")}</div><div class="metric"><b>{metric:,}</b> 套{label}</div>
<div class="addr">{H.escape(x.get("addr") or "")}</div><div class="rent">{H.escape(rent or "")}</div></div>'''

    ssb_dist = collections.Counter((x.get("district") or "未知") for x in new_ssb)
    ssb_order = [d for d, _ in ssb_dist.most_common()]
    flat_ssb = []
    for d in ssb_order:
        items = [x for x in new_ssb if (x.get("district") or "未知") == d]
        items.sort(key=lambda x: -num(x.get("online")))
        flat_ssb.extend(items)

    def prow(x):
        metric = num(x.get("online"))
        rent = (f'{x.get("rent_low")}–{x.get("rent_high")} 元'
                if x.get("rent_low") is not None else "")
        return f'''<div class="prow"><div class="prow-main"><div class="pname">{H.escape(x.get("name") or "")}</div><div class="paddr">{H.escape(x.get("addr") or "")}</div></div><div class="prow-side"><div class="pmetric"><b>{metric:,}</b> 套在线</div><div class="prent">{H.escape(rent)}</div></div></div>'''

    chunks = [flat_ssb[0:14], flat_ssb[14:27], flat_ssb[27:40]]
    prev_district = None
    for idx, chunk in enumerate(chunks, start=1):
        groups = []
        i = 0
        while i < len(chunk):
            d = chunk[i].get("district") or "未知"
            j = i
            while j < len(chunk) and (chunk[j].get("district") or "未知") == d:
                j += 1
            items = chunk[i:j]
            cont = (i == 0 and d == prev_district)
            label = f"{H.escape(d)}（续）" if cont else H.escape(d)
            cnt = f"本页 {len(items)} 个" if cont else f"{len(items)} 个"
            groups.append(f'''<div class="pgroup"><div class="pgroup-head"><span>{label}</span><span class="cnt">{cnt}</span></div><div class="prows">{''.join(prow(x) for x in items)}</div></div>''')
            i = j
        prev_district = (chunk[-1].get("district") or "未知") if chunk else prev_district
        body = f'''<h2>随申办新增 · 按行政区 {idx}/3</h2><p class="sub">共 {len(new_ssb)} 个新增项目，按行政区分组展示；本页 {len(chunk)} 个。</p>
{''.join(groups)}'''
        title = f"随申办新增 · 按行政区 {idx}/3"
        with open(os.path.join(OUTDIR, f"{3+idx}.html"), "w") as f:
            f.write(page(title, body, no=3+idx))

    pd_body = f'''<h2>明珠在线新增 · {len(new_pd)} 个</h2><p class="sub">3 个项目均在浦东新区，其中 2 个为预供应。</p>
<div class="cards">{''.join(card(x, True) for x in new_pd)}</div>
<h2 style="margin-top:26px">本月下架 · {len(gone_ssb)+len(gone_pd)} 个</h2>
<div class="removed">{''.join(f'<div class="gone"><span class="dot"></span><b>{H.escape(x.get("name") or "")}</b><span>{H.escape(x.get("district") or "")}</span><em>{num(x.get("online") if x in gone_ssb else x.get("kzts")):,} 套</em></div>' for x in (gone_ssb+gone_pd))}</div>
<div class="conclusion"><b>本期结论：</b>明珠新增 3 个项目全部位于浦东，其中 2 个为预供应；本月仅 3 个项目下架，整体保持稳定。</div>
<div class="takeaways three" style="margin-top:14px">
<div class="takeaway"><div class="tk-num">3</div><div class="tk-label">明珠新增</div><div class="tk-sub">全部位于浦东</div></div>
<div class="takeaway"><div class="tk-num">2</div><div class="tk-label">预供应项目</div><div class="tk-sub">提前释放供应信号</div></div>
<div class="takeaway"><div class="tk-num">3</div><div class="tk-label">本月下架</div><div class="tk-sub">整体供应保持稳定</div></div>
</div>
<div class="note">说明：新增项目按当前在线/可租套数排序；下架项目按最后快照数据统计。数据来源为随申办与明珠在线公开房源信息。</div>'''
    with open(os.path.join(OUTDIR, "7.html"), "w") as f:
        f.write(page("明珠在线新增与本月下架", pd_body, no=7))

    with open(os.path.join(OUTDIR, "1.html"), "w") as f:
        f.write(p1)
    with open(os.path.join(OUTDIR, "2.html"), "w") as f:
        f.write(p2)
    with open(os.path.join(OUTDIR, "3.html"), "w") as f:
        f.write(p3)
    print(f"生成 {OUTDIR} / 7 页")


if __name__ == "__main__":
    os.makedirs(OUTDIR, exist_ok=True)
    main()
