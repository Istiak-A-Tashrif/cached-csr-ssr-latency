#!/usr/bin/env python3
"""Freeze model v5: model4 parameters + correction grid from all already-used RTT>0 data."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, mean
from residuals5 import pooled

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
F4 = json.load(open(os.path.join(R, "model4.frozen.json")))
P = pooled(("prosp3", "prosp4", "diag"))
grid = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
for a in P:
    g = grid[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
    g["c"].append(a["c"]); g["r"].append(a["res"])
corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(levels.items())] for k, levels in grid.items()}
F = {k: F4[k] for k in ("bytes", "T0", "tcp0")}
F.update(frozenAt=time.strftime("%Y-%m-%dT%H:%M:%S"), correction=corr, calibratedRtts=sorted({a["rtt"] for a in P}),
         **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5")})
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "model5.frozen.json"), "w").write(blob)
print("frozen model5; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "from", len(P), "actions at RTTs", F["calibratedRtts"])
