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

PID=os.environ.get("HX_PIDS","4407,4922")
LOG=lambda *a: print(time.strftime("%H:%M:%S"),*a,flush=True)

todo=[p.strip() for p in PID.split(",") if p.strip()]
done=set()
for rnd in range(300):
    for pid in list(todo):
        try:
            d=H.house_list(H._cookie(),pid,1,10)
            if d.get("results"):
                LOG(f"{pid} 接口恢复，开始采集…")
                info=H.collect(pid)
                LOG(f"{pid} 户型",len(info["types"]),"房源缓存",len(info["houses"]),"total",info["total"])
                samp=H.pick_sample(pid,10,5)
                ids=[str(h.get("houseId")) for h in samp]
                det=H.collect_details(pid,ids)
                time.sleep(1)
                ph=H.collect_photos(pid)
                LOG(f"{pid} 样例详情",len(det),"户型图ok",ph.get("ok"),"fail",len(ph.get("fail") or []))
                print(f"== {pid} 10 套样例 ==")
                cache=H.load_cache().get(pid) or {}
                for h in samp:
                    d2=(cache.get("details") or {}).get(str(h.get("houseId"))) or {}
                    loc=" ".join(str(d2.get(k)) for k in ("roadName","laneName","streetNumber","buildingNumber") if d2.get(k))
                    print(f"[{h.get('rentStatus')}] {h.get('doorTypeNmae')} 门牌{h.get('roomNumber')}{('+'+str(h.get('subRoomNumber'))) if h.get('subRoomNumber') else ''} "
                          f"{h.get('area')}㎡ {(d2.get('rentTypeName') or '—')} 月租{d2.get('monthRent') or '—'} {d2.get('supplyStatusValue') or ''} {loc}")
                todo.remove(pid); done.add(pid)
            else:
                LOG(f"{pid} 仍空,total={d.get('totalCount')}")
        except Exception as e:
            LOG(pid,"ERR",repr(e)[:90])
    if not todo:
        LOG("ALL DONE"); break
    time.sleep(600)
