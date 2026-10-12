import sys
from mitmproxy.io import FlowReader
from mitmproxy import http

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src + ".txt"

out = []
with open(src, "rb") as f:
    for flow in FlowReader(f).stream():
        if not isinstance(flow, http.HTTPFlow):
            continue
        req = flow.request
        out.append("=" * 80)
        out.append(f"{req.method} {req.pretty_url}")
        out.append("--- REQUEST HEADERS ---")
        for k, v in req.headers.items():
            out.append(f"{k}: {v}")
        out.append("--- REQUEST BODY ---")
        try:
            out.append(req.get_text(strict=False) if req.content else "")
        except Exception:
            out.append(repr(req.content))
        if flow.response:
            resp = flow.response
            out.append(f"--- RESPONSE {resp.status_code} ---")
            for k, v in resp.headers.items():
                out.append(f"{k}: {v}")
            out.append("--- RESPONSE BODY ---")
            try:
                out.append(resp.get_text(strict=False) if resp.content else "")
            except Exception:
                out.append(repr(resp.content))

with open(dst, "w") as f:
    f.write("\n".join(out))
print(f"written: {dst}")
