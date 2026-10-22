#!/usr/bin/env python3
"""Post-hoc diagnosis (not a test) of criterion O1 misses: predicted vs observed P(db) per policy and
probability band, for a scored revision block. usage: python3 diag_o1.py <tag> [R|RC]"""
import collections, json, os, sys
tag = sys.argv[1]; kind = sys.argv[2] if len(sys.argv) > 2 else "R"
src = open("evaluateR.py" if kind == "R" else "evaluateRC.py").read()
src = src.split("runs, views, preds, W, lags, errors, ahead, unl = load_block(tag)")[0]
g = {"__name__": "diag", "__file__": os.path.abspath("evaluateR.py")}
sys.argv = [sys.argv[0], tag]
exec(compile(src, "ev", "exec"), g)
runs, views, preds, *_ = g["load_block"](tag)
acc = collections.defaultdict(lambda: [0, 0.0, 0])
for rid, vs in views.items():
    pl = {(x["user"], x["step"]): x["dist"] for x in preds[rid]["views"]}
    pol = g["cell"](runs[rid]).split("-a")[0]
    for v in vs:
        d = pl.get((v["u"], v["s"]))
        if d and v["y"] and 0 < d["db"] < 1:
            band = "0.1-0.4" if d["db"] < 0.4 else "0.4-0.7" if d["db"] < 0.7 else "0.7-1"
            a = acc[(pol, band)]; a[0] += 1; a[1] += d["db"]; a[2] += v["y"] == "db"
for (pol, band), (n, p, o) in sorted(acc.items()):
    if n >= 50: print(f"{pol:32s} {band:8s} n={n:5d} pred {p / n:.3f} obs {o / n:.3f} diff {o / n - p / n:+.3f}")
