import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import report  # noqa: E402
import geocode  # noqa: E402


def main():
    cur = report.load_current()
    addrs = set()
    for x in cur.get("ssb", []):
        if x.get("addr"):
            addrs.add(x["addr"])
    for x in cur.get("pd", []):
        if x.get("addr"):
            addrs.add(x["addr"])
    addrs = sorted(addrs)
    print("待地理编码地址数:", len(addrs))
    geocode.build(addrs)


if __name__ == "__main__":
    main()
