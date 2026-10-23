import sys

import report
import doortypes


def main():
    args = sys.argv[1:]
    if args and args[0].isdigit():
        n = int(args[0])
        explicit = [a for a in args[1:] if a.isdigit()]
    else:
        n = 5
        explicit = [a for a in args if a.isdigit()]
    cur = report.load_current()
    ids = explicit or [str(x.get("id")) for x in cur.get("ssb", [])][:n]
    print("待抓取项目:", ids)
    for pid in ids:
        try:
            rec = doortypes.fetch(pid, force=True)
            print(pid, "OK 户型数", len(rec.get("doorTypes", [])) if rec else 0)
        except Exception as e:
            print(pid, "FAIL", repr(e))


if __name__ == "__main__":
    main()
