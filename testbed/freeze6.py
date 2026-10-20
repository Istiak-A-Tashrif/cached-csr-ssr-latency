#!/usr/bin/env python3
"""Freeze model v6 = v5 equations (model5.py, unchanged) recalibrated on server with
netem only: T0/bytes/tcp0 from calib6 (RTT 0), bundle dispatch from grid6 (RTT > 0),
correction grid from grid6 residuals (client RTT 120-550 ms). No relay data is used."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0, predict as predict4

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load("calib6.jsonl", "calib6-runs.jsonl")
grid, gruns, e2, u2 = load("grid6.jsonl", "grid6-runs.jsonl")
assert not (e1 or u1 or e2 or u2), (len(e1), len(u1), len(e2), len(u2))
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
for a in grid:
    p = gruns[a["runId"]]["tcpPre"]
    c = (p["client_web"] - tcp0["client_web"] + p["client_api"] - tcp0["client_api"]) / 2
    i = max(0.0, p["web_api"] - tcp0["web_api"])
    g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
    g["c"].append(c); g["r"].append(a["latencyMs"] - predict4(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6))
corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(lv.items())] for k, lv in cells.items()}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": B, "T0": {"|".join(k): v for k, v in T0.items()},
     "tcp0": tcp0, "correction": corr, "calibratedRtts": sorted({a["rtt"] for a in grid}),
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "model6.frozen.json"), "w").write(blob)
print("frozen model6; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "tcp0", {k: round(v, 2) for k, v in tcp0.items()})
