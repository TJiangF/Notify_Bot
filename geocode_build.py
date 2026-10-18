import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import report  # noqa: E402
import geocode  # noqa: E402


def main():
    cur = report.load_current()
    seen = {}
    for x in cur.get("ssb", []):
        if x.get("addr"):
            seen[x["addr"]] = x.get("district") or ""
    for x in cur.get("pd", []):
        if x.get("addr"):
            seen.setdefault(x["addr"], "浦东新区")
    items = list(seen.items())
    print("待地理编码地址数:", len(items))
    geocode.build(items)


if __name__ == "__main__":
    main()
