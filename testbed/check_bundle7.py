#!/usr/bin/env python3
"""Diagnostic: v7 bundle simulator vs observation per group (calibration grid and used real path)."""
import json
from collections import defaultdict
from lib import R, load, mean
from model7 import bundle_load, calibration_loads, big_on_new

t0 = json.load(open(f"{R}/model6.frozen.json"))["tcp0"]
doc = json.load(open(f"{R}/model6.frozen.json"))["bytes"]["doc_csr"]
for tag, rtts in (("grid6", [120, 250, 400, 550]), ("diag6", None)):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
    g = defaultdict(lambda: {"obs": [], "sim": []})
    for a in acts:
        if a["mode"] != "csr" or a["action"] != "initial" or not a.get("res"): continue
        r = runs[a["runId"]]
        if rtts and r["rtt"] not in rtts: continue
        p = r["tcpPre"]; c = (p["client_web"] - t0["client_web"] + p["client_api"] - t0["client_api"]) / 2
        l = calibration_loads([a], runs, t0)[0]
        d = a["res"][0]["responseEnd"]
        obs = max(x["responseEnd"] for x in a["res"] if x["type"] in ("script", "link")) - d
        k = (tag, r["rtt"], "new" if big_on_new(l) else "reused")
        g[k]["obs"].append(obs / c); g[k]["sim"].append(bundle_load(l, c, 10e6, doc) / c)
    for k, v in sorted(g.items()):
        print(f"{k[0]} rtt={k[1]:3} big on {k[2]:6}: n={len(v['obs']):2} observed {mean(v['obs']):4.2f} RTT  simulated {mean(v['sim']):4.2f} RTT")
