#!/usr/bin/env python3
"""Retrospective checks for model v2 (NOT validation: this data informed its design)."""
from collections import defaultdict
from lib import load, mean
from model2 import analytic_outcomes, calibrate_bytes, calibrate_T0, predict

BW = 10e6
calib, calib_runs, _, _ = load("calib2.jsonl", "calib2-runs.jsonl")
B = calibrate_bytes(calib)
print("calibrated bytes:", {k: v for k, v in B.items() if k != "scripts"}, "scripts:", B["scripts"], "sum", sum(B["scripts"]))

# 1. analytic outcomes vs measured
for name in (("pilot.jsonl", "pilot-runs.jsonl"), ("prosp.jsonl", "prosp-runs.jsonl"), ("calib2.jsonl", "calib2-runs.jsonl")):
    acts, runs, _, _ = load(*name)
    by_run = defaultdict(dict)
    for a in acts: by_run[a["runId"]][(a["user"], a["step"])] = a["o"]
    agree = total = 0
    for rid, r in runs.items():
        for u, s, _p, o in analytic_outcomes(r["mode"], r["fe"], r["be"], r["users"]):
            if (u, s) in by_run[rid]:
                total += 1; agree += by_run[rid][(u, s)] == o
    print(f"analytic outcomes vs measured, {name[0]:12}: {agree}/{total} agree")

# 2. retrospective latency check
def check(acts, T0, label):
    cells = defaultdict(list)
    for a in acts:
        if a["rtt"] == 0: continue
        cells[(a["mode"], a["fe"], a["be"], a["rtt"], a["wl"], a["action"])].append(a)
    rel = []
    print(f"\n-- {label}: cell mean observed vs v2 --")
    for k in sorted(cells):
        g = cells[k]
        obs = mean(a["latencyMs"] for a in g)
        pred = mean(predict(a["mode"], a["action"], a["o"], a["crtt"], a["irtt_m"], T0, B, BW) for a in g)
        rel.append(abs(pred - obs) / obs)
        print(f"  {k[0]} fe={int(k[1])} be={int(k[2])} rtt={k[3]:3} {k[4]:7} {k[5]:7}: obs {obs:7.1f} pred {pred:7.1f} ({100 * (pred - obs) / obs:+5.1f}%)")
    print(f"  mean rel {100 * mean(rel):.1f}%  max rel {100 * max(rel):.1f}%")

prosp, _, _, _ = load("prosp.jsonl", "prosp-runs.jsonl")
check(prosp, calibrate_T0(calib), "Week-3 data (revisit workload), T0 from calib2")
pilot, _, _, _ = load("pilot.jsonl", "pilot-runs.jsonl")
for wl in ("reuse", "spread"):
    T0 = calibrate_T0([a for a in pilot if a["wl"] == wl and a["rtt"] == 0])
    check([a for a in pilot if a["wl"] == wl], T0, f"pilot {wl}, T0 from pilot RTT 0")
