#!/usr/bin/env python3
"""Freeze model-v2 predictions for `harness.mjs prospective2` (run BEFORE it).

Inputs: calib2 (RTT 0: T0 per outcome, byte sizes), pilot runs (nominal -> effective
RTT), the evaluation workloads (generated from their declared seeds), and the
Week-3 frozen v1 predictions (for the v1 and baseline comparisons).
Outcomes come from `analytic_outcomes`; nothing is measured from the evaluation.
"""
import hashlib, json, os, subprocess, time
from collections import defaultdict
from lib import R, load, linfit, mean
from model2 import analytic_outcomes, calibrate_bytes, calibrate_T0, predict

BW = 10e6
SEEDS, CRTTS, IRTTS = (31, 32, 33, 34), (80, 230), (0, 60)
here = os.path.dirname(os.path.abspath(__file__))

calib, _, cerr, cunc = load("calib2.jsonl", "calib2-runs.jsonl")
assert not cerr and not cunc
B, T0 = calibrate_bytes(calib), calibrate_T0(calib)
pilot_runs = load("pilot.jsonl", "pilot-runs.jsonl")[1]
xs = [r["rtt"] for r in pilot_runs.values()]
ys = [(r["measuredRtt"]["client_web"] + r["measuredRtt"]["client_api"]) / 2 for r in pilot_runs.values()]
ra, rb = linfit(xs, ys)
eff = lambda nominal: ra + rb * nominal if nominal else 0.2  # same netem overshoot on every link

v1 = json.load(open(os.path.join(R, "predictions.frozen.json")))
v1mix = {(c["mode"], c["fe"], c["be"], c["action"]): c["mix"] for c in v1["cells"] if c["rtt"] == 40}
line = lambda ab, x: ab[0] + ab[1] * x

workloads = {}
for s in SEEDS:
    js = f"import('./harness.mjs').then(h=>console.log(JSON.stringify(h.makeWorkload({{...h.WORKLOADS.revisit, seed: {s} * 1000 + 'revisit'.length}}))))"
    workloads[s] = json.loads(subprocess.check_output(["node", "-e", js, "noop"], cwd=here).decode().strip().splitlines()[-1])

cells = defaultdict(lambda: defaultdict(list))
for s, users in workloads.items():
    for crtt in CRTTS:
        for irtt in IRTTS:
            for mode in ("csr", "ssr"):
                for fe, be in ((False, False), (True, True)):
                    for u, step, page, o in analytic_outcomes(mode, fe, be, users):
                        action = "initial" if step == 0 else "nav"
                        key = (mode, fe, be, crtt, irtt, action)
                        cells[key]["v2"].append(predict(mode, action, o, eff(crtt), eff(irtt), T0, B, BW))
                        cells[key]["outcomes"].append(o)

out_cells = []
for (mode, fe, be, crtt, irtt, action), d in sorted(cells.items()):
    x = eff(crtt)
    mix = v1mix[(mode, fe, be, action)]
    out_cells.append({
        "mode": mode, "fe": fe, "be": be, "crtt": crtt, "irtt": irtt, "action": action,
        "v2": mean(d["v2"]),
        "v1": sum(p * line(v1["costLines"][f"{mode}|{action}|{o}"], x) for o, p in mix.items()),
        "B_nocache": line(v1["costLines"][f"{mode}|{action}|db"], x),
        "B_mean": line(v1["baselineMeanLines"][f"{mode}|{action}"], x),
        "outcomeMix": {o: d["outcomes"].count(o) / len(d["outcomes"]) for o in set(d["outcomes"])},
    })

diffs = []
for crtt in CRTTS:
    for irtt in IRTTS:
        for fe, be in ((False, False), (True, True)):
            for action in ("initial", "nav"):
                g = {c["mode"]: c for c in out_cells if (c["crtt"], c["irtt"], c["fe"], c["be"], c["action"]) == (crtt, irtt, fe, be, action)}
                diffs.append({"crtt": crtt, "irtt": irtt, "fe": fe, "be": be, "action": action,
                              **{k: g["ssr"][k] - g["csr"][k] for k in ("v2", "v1", "B_nocache", "B_mean")}})

blob = json.dumps({"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "rttMap": [ra, rb], "bytes": B,
                   "T0": {"|".join(map(str, k)): v for k, v in T0.items()}, "cells": out_cells, "ssrMinusCsr": diffs},
                  indent=1, sort_keys=True)
open(os.path.join(R, "predictions2.frozen.json"), "w").write(blob)
print("frozen; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
for d in diffs:
    if d["action"] == "nav":
        print(f"  SSR-CSR nav crtt={d['crtt']:3} irtt={d['irtt']:2} caches={'on ' if d['fe'] else 'off'}: v2 {d['v2']:7.1f}  v1 {d['v1']:7.1f}  B_nocache {d['B_nocache']:6.1f}  B_mean {d['B_mean']:6.1f}")
