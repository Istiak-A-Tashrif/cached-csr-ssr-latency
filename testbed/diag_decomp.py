#!/usr/bin/env python3
"""Post-hoc staleness error decomposition (not a test; 'known-schedule' diagnostic). Per cell:
  total error      = observed stale share - frozen prediction (declared write process)
  write-rate part  = prediction with the run's REALIZED write rate (Poisson at writes / run time) - frozen prediction
  remainder        = observed - prediction with the realized rate (cache state, timing, display age)
Summaries: pooled MAE and worst cell before and after replacing the declared by the realized rate.
usage: python3 diag_decomp.py <tag> ..."""
import bisect, collections, json, sys
from modelR import layer_cfg, simulate, stale_fraction
from writeproc import p0_factory
M = json.load(open("results/modelR.frozen.json"))
W = collections.defaultdict(lambda: collections.defaultdict(list)); nw = collections.Counter()
for w in map(json.loads, open("results/writes.jsonl")):
    W[w["runId"]][w["productId"]].append(w["committed"]); nw[w["runId"]] += 1
for d in W.values():
    for v in d.values(): v.sort()
preds = {p["runId"]: p["stale"] for p in map(json.loads, open("results/predictionsR.jsonl")) if "stale" in p}
OUT = {}
for tag in sys.argv[1:]:
    runs = {r["runId"]: r for r in map(json.loads, open(f"results/{tag}-runs.jsonl"))}
    obs = collections.defaultdict(list)
    for v in map(json.loads, open(f"results/{tag}.jsonl")):
        if v.get("runId") not in runs or "error" in v: continue
        r = runs[v["runId"]]
        obs[v["runId"]].append(any(s != r["stock0"][str(p)] + bisect.bisect_right(W[v["runId"]][p], v["wall"]) for p, s in v["rows"]))
    cells = collections.defaultdict(lambda: [[], [], []])
    for rid, run in runs.items():
        crtt = run["tcpPre"]["client_web"]
        fit = lambda tab: (lambda mm, a, o: tab[f"{mm}|{a}|{o}"]["a"] + tab[f"{mm}|{a}|{o}"]["b"] * crtt)
        lam = nw[rid] / (run["wallMs"] / 1000)
        p0 = p0_factory({"kind": "poisson", "lam": lam}, run["pages"])
        v = simulate(run["users"], fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0)
        c = cells[run["cellName"]]
        c[0].append(sum(obs[rid]) / len(obs[rid])); c[1].append(preds[rid]); c[2].append(stale_fraction(v, p0))
    mean = lambda x: sum(x) / len(x)
    e0 = {k: mean(c[0]) - mean(c[1]) for k, c in cells.items()}
    e1 = {k: mean(c[0]) - mean(c[2]) for k, c in cells.items()}
    rate = {k: mean(c[2]) - mean(c[1]) for k, c in cells.items()}
    print(f"{tag}: pooled MAE declared {mean([abs(x) for x in e0.values()]):.4f} (worst {max(map(abs, e0.values())):.3f})  ->  realized rate {mean([abs(x) for x in e1.values()]):.4f} (worst {max(map(abs, e1.values())):.3f});"
          f" mean |write-rate part| {mean([abs(x) for x in rate.values()]):.4f}")
    OUT[tag] = {"mae_declared": mean([abs(x) for x in e0.values()]), "worst_declared": max(map(abs, e0.values())),
                "mae_realized": mean([abs(x) for x in e1.values()]), "worst_realized": max(map(abs, e1.values())),
                "cells": {k: {"total": e0[k], "rate": rate[k], "remainder": e1[k]} for k in cells}}
    for k in sorted(cells, key=lambda k: -abs(e0[k]))[:4]:
        print(f"    {k:44s} total {e0[k]:+.3f} = write rate {rate[k]:+.3f} + remainder {e1[k]:+.3f}")
json.dump(OUT, open("results/revision/diag-decomp.json", "w"), indent=1)
