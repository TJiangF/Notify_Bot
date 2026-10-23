import sys
import time

import report
import doortypes


def main():
    args = sys.argv[1:]
    n = int(args[0]) if args and args[0].isdigit() else 5
    explicit = [a for a in args[1:] if a.isdigit()]
    cur = report.load_current()
    ids = explicit or [str(x.get("id")) for x in cur.get("ssb", [])][:n]
    print("待抓取项目数:", len(ids))
    ok = fail = 0
    fails = []
    for pid in ids:
        try:
            rec = doortypes.fetch(pid)
            if rec is None:
                fail += 1
                fails.append((pid, "empty"))
                print(pid, "EMPTY")
            else:
                ok += 1
                print(pid, "OK 户型", len(rec.get("doorTypes", [])))
        except Exception as e:
            fail += 1
            fails.append((pid, repr(e)))
            print(pid, "FAIL", repr(e))
        time.sleep(0.4)
    print(f"=== 完成: 成功 {ok} / 失败 {fail}")
    if fails:
        print("失败列表:", fails)


if __name__ == "__main__":
    main()
