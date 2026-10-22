#!/usr/bin/env python3
"""Post-hoc diagnosis (not a test) of staleness misses in the revision blocks:
(1) per cell, is the prediction inside the run-bootstrap 95% interval of the observed stale share?
(2) trace cells: realized write rate per replayed segment vs the training-window rate the model used."""
import bisect, collections, json, random, sys
R = "results"
W = collections.defaultdict(lambda: collections.defaultdict(list))
wn = collections.Counter()
for w in map(json.loads, open(f"{R}/writes.jsonl")):
    W[w["runId"]][w["productId"]].append(w["committed"]); wn[w["runId"]] += 1
for d in W.values():
    for v in d.values(): v.sort()
preds = {p["runId"]: p["stale"] for p in map(json.loads, open(f"{R}/predictionsR.jsonl")) if "stale" in p}
rng = random.Random(3); out = {}
for tag in sys.argv[1:]:
    runs = {r["runId"]: r for r in map(json.loads, open(f"{R}/{tag}-runs.jsonl"))}
    per = collections.defaultdict(list)
    for v in map(json.loads, open(f"{R}/{tag}.jsonl")):
        if v.get("runId") not in runs or "error" in v: continue
        run = runs[v["runId"]]
        st = any(s != run["stock0"][str(p)] + bisect.bisect_right(W[v["runId"]][p], v["wall"]) for p, s in v["rows"])
        per[v["runId"]].append(st)
    cells = collections.defaultdict(list)
    for rid, vs in per.items():
        r = runs[rid]; k = r["cellName"]
        rate = wn[rid] / (r["wallMs"] / 1000)
        cells[k].append((sum(vs) / len(vs), preds[rid], rate, r["proc"].get("lam")))
    inside = 0
    for k, xs in sorted(cells.items()):
        o = sum(x[0] for x in xs) / len(xs); p = sum(x[1] for x in xs) / len(xs)
        bs = sorted(sum(rng.choice(xs)[0] for _ in xs) / len(xs) for _ in range(4000))
        lo, hi = bs[100], bs[3899]; inside += lo <= p <= hi
        if "trace" in k or abs(o - p) > 0.05:
            print(f"{tag} {k:44s} obs {o:.3f} [{lo:.3f},{hi:.3f}] pred {p:.3f} write rate/s {sum(x[2] for x in xs)/len(xs):.2f} (declared {xs[0][3]})")
    print(f"{tag}: prediction inside run-bootstrap 95% interval in {inside}/{len(cells)} cells")
    tr = [sum(x[2] for x in xs) / len(xs) for k, xs in cells.items() if "trace" in k]
    out[tag] = {"inside": inside, "cells": len(cells), "trace_rate_min": min(tr) if tr else None, "trace_rate_max": max(tr) if tr else None,
                "declared": next(iter(cells.values()))[0][3]}
json.dump(out, open(f"{R}/revision/diag-stale.json", "w"), indent=1)
