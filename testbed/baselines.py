#!/usr/bin/env python3
"""Compare a frozen model's prospective predictions with naive baselines on the same test.

Baselines are fitted on calibration data available before the model was frozen:
  B_mean     latency = a + b * client RTT per (mode, action), all cache configurations pooled
             (knows the rendering path and the network, ignores which cache layer answers)
  B_nocache  the same line fitted on runs with every cache off (assumes caches do not matter)
usage: python3 baselines.py <test tag> <predictions file> <calib tag> [<calib tag> ...]
"""
import sys
from collections import defaultdict
from lib import jl, load, mean

tag, pred_file, calib_tags = sys.argv[1], sys.argv[2], sys.argv[3:]


def fit(points):
    n = len(points); mx = mean(x for x, _ in points); my = mean(y for _, y in points)
    sxx = sum((x - mx) ** 2 for x, _ in points)
    b = sum((x - mx) * (y - my) for x, y in points) / sxx if sxx > 1e-9 else 0.0
    return my - b * mx, b


pts_all, pts_none = defaultdict(list), defaultdict(list)
for t in calib_tags:
    acts, _, _, _ = load(f"{t}.jsonl", f"{t}-runs.jsonl")
    for a in acts:
        k = (a["mode"], a["action"])
        pts_all[k].append((a["crtt"], a["latencyMs"]))
        if not a["fe"] and not a["be"]: pts_none[k].append((a["crtt"], a["latencyMs"]))
L_all = {k: fit(v) for k, v in pts_all.items()}
L_none = {k: fit(v) for k, v in pts_none.items()}

acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
preds = {p["runId"]: p for p in jl(pred_file)}
pmap = {(r, x["user"], x["step"]): x["pred"] for r, p in preds.items() for x in p["preds"]}
M = ("model", "B_mean", "B_nocache")
cells = defaultdict(lambda: defaultdict(lambda: {m: [] for m in ("obs",) + M}))
for a in acts:
    c = cells[(a["mode"], a["fe"], a["rtt"], a["irtt"], a["action"])][a["seed"]]
    k = (a["mode"], a["action"])
    c["obs"].append(a["latencyMs"])
    c["model"].append(pmap[(a["runId"], a["user"], a["step"])])
    c["B_mean"].append(L_all[k][0] + L_all[k][1] * a["crtt"])
    c["B_nocache"].append(L_none[k][0] + L_none[k][1] * a["crtt"])

cm = {k: {m: mean(mean(v[m]) for v in s.values()) for m in ("obs",) + M} for k, s in cells.items()}
print(f"{tag}: {len(cells)} cells, {len(acts)} actions; baselines fitted on {', '.join(calib_tags)}")
for m in M:
    rel = [abs(c[m] - c["obs"]) / c["obs"] for c in cm.values()]
    mae = mean(abs(c[m] - c["obs"]) for c in cm.values())
    # SSR - CSR navigation/initial differences: sign agreement where |observed| >= 10 ms
    diffs = []
    for (mode, fe, rtt, irtt, act), c in cm.items():
        s = cm.get(("ssr", fe, rtt, irtt, act))
        if mode == "csr" and s:
            d_obs, d_m = s["obs"] - c["obs"], s[m] - c[m]
            if abs(d_obs) >= 10: diffs.append((d_obs > 0) == (d_m > 0))
    print(f"  {m:10s} mean rel {100*mean(rel):6.2f}%  max rel {100*max(rel):6.2f}%  MAE {mae:7.1f} ms  "
          f"SSR-CSR sign {sum(diffs)}/{len(diffs)}")
