#!/usr/bin/env python3
"""Freeze model v4: model4.py + calib3 (RTT 0) + diag (RTT 170) parameters."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0, predict

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load("calib3.jsonl", "calib3-runs.jsonl")
diag, druns, e2, u2 = load("diag.jsonl", "diag-runs.jsonl")
assert not (e1 or u1 or e2 or u2)
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
B, T0 = calibrate_bytes(calib, diag), calibrate_T0(calib)
inputs = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                      max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))
res = defaultdict(list)
for a in diag:
    c, i = inputs(druns[a["runId"]])
    res[f"{a['mode']}|{a['action']}"].append(a["latencyMs"] - predict(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6))
kappa = {k: mean(v) for k, v in res.items()}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "model4_sha256": sha("model4.py"), "model2_sha256": sha("model2.py"),
     "bytes": B, "T0": {"|".join(k): v for k, v in T0.items()}, "tcp0": tcp0, "kappa": kappa}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "model4.frozen.json"), "w").write(blob)
print("frozen model4; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "kappa", {k: round(v, 1) for k, v in kappa.items()})
