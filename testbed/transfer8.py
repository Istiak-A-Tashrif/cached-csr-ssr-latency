#!/usr/bin/env python3
"""Diagnostic: model-v8 residuals on all completed (used) real-path tests, per action type.
Inputs per run: TCP RTT, race p (if probed; else the calibration value), bandwidth
(measured if probed; else the 10 Mbit/s cap used in that test)."""
import json
from collections import defaultdict
from lib import R, load, mean
from model8 import predict

F = json.load(open(f"{R}/model8.frozen.json")); t0 = F["tcp0"]
res = defaultdict(lambda: defaultdict(list))
for tag in ("real6", "rep6", "real7", "rep7", "real8", "rep8"):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
    for a in acts:
        r = runs[a["runId"]]; p = r["tcpPre"]
        c = (p["client_web"] - t0["client_web"] + p["client_api"] - t0["client_api"]) / 2
        bw = r.get("bwBps") or 10e6
        race = r.get("raceP") if r.get("raceP") is not None else F["cap"]["p_netem"]
        res[f"{a['mode']}|{a['action']}"][tag].append(a["latencyMs"] - predict(a["mode"], a["action"], a["o"], c, 0, F, bw, race))
for k in sorted(res):
    print(f"{k:12} " + "  ".join(f"{t}:{mean(v):+6.1f}" for t, v in res[k].items()) + f"   | pooled mean {mean([x for v in res[k].values() for x in v]):+6.1f} ms")
