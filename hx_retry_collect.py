import os,sys,json,time
BASE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,BASE)
ENVF="/opt/ssb-monitor/env.sysd"
for line in open(ENVF):
    line=line.strip()
    if not line or "=" not in line or line.startswith("#"): continue
    k,v=line.split("=",1)
    if len(v)>=2 and v[0]==v[-1]=="\"": v=v[1:-1]
    os.environ[k]=v
import houses as H

PID=os.environ.get("HX_PID","4922")
LOG=lambda *a: print(time.strftime("%H:%M:%S"),*a,flush=True)

for rnd in range(200):
    try:
        d=H.house_list(H._cookie(),PID,1,10)
        if d.get("results"):
            LOG("接口恢复，开始采集…")
            break
        LOG("仍空,total=",d.get("totalCount"))
    except Exception as e:
        LOG("ERR",repr(e)[:80])
    time.sleep(600)
else:
    LOG("放弃"); sys.exit(1)

info=H.collect(PID)
LOG("户型",len(info["types"]),"房源缓存",len(info["houses"]),"total",info["total"])
samp=H.pick_sample(PID,10,5)
ids=[str(h.get("houseId")) for h in samp]
det=H.collect_details(PID,ids)
time.sleep(1)
ph=H.collect_photos(PID)
LOG("样例详情",len(det),"户型图ok",ph.get("ok"),"fail",len(ph.get("fail") or []))
cache=H.load_cache().get(PID) or {}
print("== 10 套样例 ==")
for h in samp:
    d2=det.get(str(h.get("houseId"))) or {}
    loc=" ".join(str(d2.get(k)) for k in ("roadName","laneName","streetNumber","buildingNumber") if d2.get(k))
    print(f"[{h.get('rentStatus')}] {h.get('doorTypeNmae')} 门牌{h.get('roomNumber')}{('+'+str(h.get('subRoomNumber'))) if h.get('subRoomNumber') else ''} "
          f"{h.get('area')}㎡ {(d2.get('rentTypeName') or '—')} 月租{d2.get('monthRent') or '—'} {d2.get('supplyStatusValue') or ''} {loc}")
LOG("DONE")
