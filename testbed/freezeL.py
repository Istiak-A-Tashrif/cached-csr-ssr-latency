#!/usr/bin/env python3
"""Generic v7 freeze per LEVEL (experiments Q and R), from netem data only.
usage: python3 freezeL.py <tag> <calib tag> <grid tag> [level key]
One v7 calibration (T0, bytes, race-split bundle curves, correction) per value of the level key
(e.g. cpuRate for R; a single level when no key). Written to results/modelL<tag>.frozen.json."""
import hashlib, json, os, sys, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs

tag, ctag, gtag = sys.argv[1:4]; key = sys.argv[4] if len(sys.argv) > 4 else None
here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load(f"{ctag}.jsonl", f"{ctag}-runs.jsonl")
grid, gruns, e2, u2 = load(f"{gtag}.jsonl", f"{gtag}-runs.jsonl")
# Calibration only: sessions that ended in an error record (runner wait timeout) contribute their
# completed actions and nothing else; the count is reported. Unclassified actions are not allowed.
assert not (u1 or u2), (len(u1), len(u2))
if e1 or e2: print(f"note: {len(e1)} + {len(e2)} error records in calibration data (failed sessions excluded)")
lv_of = lambda run: run.get(key, 1) if key else 1

def level(calib, cruns, grid, gruns):
    links = ("client_web", "client_api", "web_api")
    tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
    B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
    inputs = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                          max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))
    rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
    lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
    for a in grid:
        if a["mode"] == "csr" and a["action"] == "initial":
            b, new = bundle_obs(a); c, _ = inputs(gruns[a["runId"]])
            g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
    curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(l.items())] for grp, l in lv.items()}
    for grp in ("new", "reused"):
        curves.setdefault(grp, curves["reused" if grp == "new" else "new"])
    cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
    for a in grid:
        c, i = inputs(gruns[a["runId"]])
        p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
        g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
        g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6, curves, p))
    corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
    return {"bytes": B, "T0": {"|".join(k): v for k, v in T0.items()}, "tcp0": tcp0, "curves": curves, "correction": corr,
            "p_netem": mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")}

levels = {}
for v in sorted({lv_of(r) for r in cruns.values()}):
    sel = lambda acts, runs: ([a for a in acts if lv_of(runs[a["runId"]]) == v], {k: r for k, r in runs.items() if lv_of(r) == v})
    levels[str(v)] = level(*sel(calib, cruns), *sel(grid, gruns))
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "levelKey": key, "levels": levels,
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, f"modelL{tag}.frozen.json"), "w").write(blob)
print(f"frozen modelL{tag}; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "levels", list(levels))
for v, L in levels.items():
    print(f"  level {v}: p_netem {L['p_netem']:.2f}  T0 " + ", ".join(f"{k}={x:.0f}" for k, x in sorted(L["T0"].items()) if "initial" in k or "nav|db" in k))
