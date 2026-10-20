#!/usr/bin/env python3
"""Diagnostic: bundle-phase simulation vs observation, split by where the big chunk ran."""
import json
from collections import defaultdict
from lib import R, load, mean
from model4 import bundle_load

F = json.load(open(f"{R}/model6.frozen.json")); t0 = F["tcp0"]; B = F["bytes"]
for tag, rtts in (("grid6", [400, 550]), ("diag6", None)):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
    g = defaultdict(lambda: {"obs": [], "sim": [], "ex": None})
    for a in acts:
        if a["mode"] != "csr" or a["action"] != "initial" or not a.get("res"): continue
        r = runs[a["runId"]]
        if rtts and r["rtt"] not in rtts: continue
        p = r["tcpPre"]; c = (p["client_web"] - t0["client_web"] + p["client_api"] - t0["client_api"]) / 2
        res = a["res"]; d = res[0]; sc = sorted([x for x in res if x["type"] in ("script", "link")], key=lambda x: x["requestStart"])
        load_ = [[x["transfer"], bool(x["newConn"])] for x in sc]
        big = max(sc, key=lambda x: x["transfer"])
        key = (tag, r["rtt"], "new" if big["newConn"] else "reused")
        g[key]["obs"].append((max(x["responseEnd"] for x in sc) - d["responseEnd"]) / c)
        g[key]["sim"].append(bundle_load(load_, c, 10e6, B["doc_csr"]) / c)
        if g[key]["ex"] is None:
            g[key]["ex"] = [(x["transfer"] // 1000, int(x["newConn"]), round((x["requestStart"] - d["responseEnd"]) / c, 2),
                             round((x["responseEnd"] - d["responseEnd"]) / c, 2)) for x in sc]
    for k, v in sorted(g.items()):
        print(f"{k[0]} rtt={k[1]:3} big-chunk on {k[2]:6}: n={len(v['obs']):2}  observed {mean(v['obs']):4.2f} RTT  simulated {mean(v['sim']):4.2f} RTT")
        print(f"      example (KB, newConn, request@RTT, end@RTT): {v['ex']}")
