#!/usr/bin/env python3
"""Freeze model v7 from netem data only: calib6 (RTT 0) + grid6 (netem 120-550 ms)."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load("calib6.jsonl", "calib6-runs.jsonl")
grid, gruns, e2, u2 = load("grid6.jsonl", "grid6-runs.jsonl")
assert not (e1 or u1 or e2 or u2)
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
inputs = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                      max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))

# Bundle curves per race group: RTT-0 point from calib6, then each grid level.
rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
for a in grid:
    if a["mode"] == "csr" and a["action"] == "initial":
        b, new = bundle_obs(a); c, _ = inputs(gruns[a["runId"]])
        g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(levels.items())] for grp, levels in lv.items()}

# Correction residuals with each calibration action's ACTUAL race group (p = 1 or 0).
cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
for a in grid:
    c, i = inputs(gruns[a["runId"]])
    p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
    g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
    g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6, curves, p))
corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(levels.items())] for k, levels in cells.items()}
p_netem = mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": B, "T0": {"|".join(k): v for k, v in T0.items()},
     "tcp0": tcp0, "curves": curves, "correction": corr, "p_netem": p_netem, "calibratedRtts": sorted({a["rtt"] for a in grid}),
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "model7.frozen.json"), "w").write(blob)
print("frozen model7; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "p_netem", round(p_netem, 2))
print("bundle curves (ms):", {g: [[round(x), round(y)] for x, y in pts] for g, pts in curves.items()})
print("csr|initial corrections:", {k: [[round(x), round(y, 1)] for x, y in v] for k, v in corr.items() if k.startswith("csr|initial")})
