#!/usr/bin/env python3
"""Freeze prospective predictions for the Week 3 test (run BEFORE `harness.mjs prospective`).

Inputs used (and only these):
  - pilot, workload "reuse": per (mode, action, outcome) cost line C = a + b * client_RTT
  - pilot runs: nominal -> measured RTT mapping (netem overshoot)
  - calibration run (seed 11, RTT 0, workload "revisit"): outcome mix per (mode, fe, be, action)
Outputs results/predictions.json with model and baseline predictions of mean
data-visible latency for every evaluation cell, plus the SSR - CSR difference.
"""
import hashlib, json, os, time
from collections import Counter, defaultdict
from lib import R, load, linfit, mean

pilot, pilot_runs, _, unc = load("pilot.jsonl", "pilot-runs.jsonl")
assert not unc
calib, _, cerr, cunc = load("calib.jsonl", "calib-runs.jsonl")
assert not cerr and not cunc

train = [a for a in pilot if a["wl"] == "reuse"]

# Cost lines per (mode, action, outcome) and baseline lines.
def fit(group):
    xs = [a["crtt"] for a in group]; ys = [a["latencyMs"] for a in group]
    return linfit(xs, ys) if len({round(x) for x in xs}) > 1 else None

by_o, by_m = defaultdict(list), defaultdict(list)
for a in train:
    by_o[(a["mode"], a["action"], a["o"])].append(a)
    by_m[(a["mode"], a["action"])].append(a)
cost = {"|".join(k): fit(v) for k, v in by_o.items()}
basemean = {"|".join(k): fit(v) for k, v in by_m.items()}

# Effective RTT for a nominal setting (netem overshoot), from pilot runs.
xs = [r["rtt"] for r in pilot_runs.values()]
ys = [(r["measuredRtt"]["client_web"] + r["measuredRtt"]["client_api"]) / 2 for r in pilot_runs.values()]
rtt_a, rtt_b = linfit(xs, ys)
eff = lambda nominal: rtt_a + rtt_b * nominal

# Outcome mixes from calibration.
mix = defaultdict(Counter)
for a in calib:
    mix[(a["mode"], a["fe"], a["be"], a["action"])][a["o"]] += 1

line = lambda ab, x: ab[0] + ab[1] * x
cells = []
for rtt in (40, 300):
    x = eff(rtt)
    for (mode, fe, be, action), cnt in sorted(mix.items()):
        n = sum(cnt.values())
        model = sum(c / n * line(cost[f"{mode}|{action}|{o}"], x) for o, c in cnt.items())
        cells.append({
            "rtt": rtt, "effRtt": x, "mode": mode, "fe": fe, "be": be, "action": action,
            "mix": {o: c / n for o, c in cnt.items()},
            "model": model,
            "B_nocache": line(cost[f"{mode}|{action}|db"], x),
            "B_mean": line(basemean[f"{mode}|{action}"], x),
        })

diffs = []
for rtt in (40, 300):
    for fe, be in ((False, False), (True, True)):
        for action in ("initial", "nav"):
            g = {c["mode"]: c for c in cells if c["rtt"] == rtt and c["fe"] == fe and c["be"] == be and c["action"] == action}
            if "csr" in g and "ssr" in g:
                diffs.append({"rtt": rtt, "fe": fe, "be": be, "action": action,
                              **{k: g["ssr"][k] - g["csr"][k] for k in ("model", "B_nocache", "B_mean")}})

out = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "rttMap": [rtt_a, rtt_b],
       "costLines": cost, "baselineMeanLines": basemean, "cells": cells, "ssrMinusCsr": diffs}
blob = json.dumps(out, indent=1, sort_keys=True)
out_path = os.path.join(R, "predictions.json")
open(out_path, "w").write(blob)
print("frozen", out["frozenAt"], "sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
print(f"effective RTT: 40 -> {eff(40):.1f}, 300 -> {eff(300):.1f}")
for d in diffs:
    print(f"  SSR-CSR {d['action']:7} rtt={d['rtt']:3} fe={int(d['fe'])} be={int(d['be'])}: model {d['model']:8.1f}  B_nocache {d['B_nocache']:8.1f}  B_mean {d['B_mean']:8.1f}")
for c in cells:
    if c["action"] == "nav":
        print(f"  nav {c['mode']} rtt={c['rtt']} fe={int(c['fe'])}: mix={ {k: round(v, 2) for k, v in c['mix'].items()} } model={c['model']:.1f}")
