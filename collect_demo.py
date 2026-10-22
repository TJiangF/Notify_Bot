import os
import sys
import json

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

ENVF = "/opt/ssb-monitor/env.sysd"
if os.path.exists(ENVF):
    for line in open(ENVF):
        line = line.strip()
        if not line or "=" not in line or line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        if len(v) >= 2 and v[0] == v[-1] == "\"":
            v = v[1:-1]
        os.environ[k] = v

import houses as H

pid = sys.argv[1] if len(sys.argv) > 1 else "4922"

print(f"== 采集项目 {pid} ==")
info = H.collect(pid, page_size=500, max_pages=4, detail_n=0)
print("户型数:", len(info["types"]), "| 已缓存房源:", len(info["houses"]), "| 接口 totalCount:", info["total"])
for t in info["types"]:
    print(f"  户型 {t.get('doorTypeName')}(code={t.get('doorTypeCode')}) 在线 {t.get('onlineFlatNum')} / 总 {t.get('totalFlatNum')} / 离线 {t.get('offlineFlatNum')} "
          f"| 租金 {t.get('onlineRentLow')}~{t.get('onlineRentHigh')} | 图 {len(t.get('files') or [])}个")

samp = H.pick_sample(pid, n_total=10, free=5)
print("== 选出 10 套样例房，抓单套详情 ==")
ids = [str(h.get("houseId")) for h in samp]
det = H.collect_details(pid, ids)
ph = H.collect_photos(pid)
print("户型图下载成功:", ph.get("ok"), "失败:", ph.get("fail"))

print("== 10 套样例 ==")
for h in samp:
    d = det.get(str(h.get("houseId"))) or {}
    loc = " ".join(str(d.get(k)) for k in ("roadName", "laneName", "streetNumber", "buildingNumber") if d.get(k))
    print(f"  [{h.get('rentStatus')}] {h.get('doorTypeNmae')} 门牌 {h.get('roomNumber')}{('+'+str(h.get('subRoomNumber'))) if h.get('subRoomNumber') else ''}"
          f" 面积 {h.get('area')}㎡ 整合租 {d.get('rentTypeName') or '—'} 月租 {d.get('monthRent') or '—'} "
          f"供应状态 {d.get('supplyStatusValue') or '—'} 位置 {loc}")
