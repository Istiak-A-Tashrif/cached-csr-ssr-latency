#!/usr/bin/env python3
"""CSR initial-load phases in RTT units: netem grid (400/550 ms) vs the real path (diag6)."""
import json
from lib import R, load, mean

F = json.load(open(f"{R}/model6.frozen.json")); t0 = F["tcp0"]


def rows(tag, rtts=None):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl"); out = []
    for a in acts:
        if a["mode"] != "csr" or a["action"] != "initial" or not a.get("res"): continue
        r = runs[a["runId"]]
        if rtts and r["rtt"] not in rtts: continue
        p = r["tcpPre"]; c = (p["client_web"] - t0["client_web"] + p["client_api"] - t0["client_api"]) / 2
        res = a["res"]; d = res[0]
        sc = [x for x in res if x["type"] in ("script", "link")]
        api = [x for x in res if x["type"] == "fetch"][0]
        be = max(x["responseEnd"] for x in sc)
        big = max(sc, key=lambda x: x["transfer"])
        out.append(dict(rtt=c, doc=d["responseEnd"], bundle=be - d["responseEnd"], exec=api["start"] - be,
                        api_conn=api["connectEnd"] - api["connectStart"], api_ttfb=api["responseStart"] - api["requestStart"],
                        api_dl=api["responseEnd"] - api["responseStart"], tail=a["latencyMs"] - api["responseEnd"],
                        vis=a["latencyMs"], big_new=big["newConn"], big_ttfb=big["responseStart"] - big["requestStart"],
                        big_dl=big["responseEnd"] - big["responseStart"], newconns=sum(x["newConn"] for x in sc)))
    return out


for name, tag, rt in (("netem 400", "grid6", [400]), ("netem 550", "grid6", [550]), ("REAL path", "diag6", None)):
    X = rows(tag, rt); c = mean(x["rtt"] for x in X); f = lambda k: mean(x[k] for x in X)
    print(f"{name:9} n={len(X):2} rtt={c:6.1f} | doc {f('doc') / c:4.2f}R  bundle {f('bundle') / c:4.2f}R  exec {f('exec'):5.1f}ms  "
          f"api conn {f('api_conn') / c:4.2f}R ttfb {f('api_ttfb') / c:4.2f}R dl {f('api_dl'):5.1f}ms tail {f('tail'):5.1f}ms | "
          f"total {f('vis') / c:4.2f}R | big chunk: new-conn {f('big_new'):.2f} ttfb {f('big_ttfb') / c:4.2f}R dl {f('big_dl') / c:4.2f}R | new conns {f('newconns'):.1f}")
