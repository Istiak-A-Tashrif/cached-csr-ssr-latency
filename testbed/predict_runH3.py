#!/usr/bin/env python3
"""Called by the harness BEFORE each realH3/repH3 run (home path, server pinned).
Inputs, all measured on the path before the run: request-level RTT (mean of keep-alive HTTP
requests), race probability p and the bundle time of the 8 race-probe page loads. The
bandwidth input is the bandwidth at which the frozen model's expected bundle time equals the
measured one (piecewise linear in x = 10 Mbit/s / bw across the calibrated levels)."""
import hashlib, json, os, sys, time
from lib import mean
from model7 import bundle_obs, expected_bundle
from modelH2 import analytic_outcomes, predict, LEVELS

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "modelH3.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py", "modelH2.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
run = json.loads(sys.argv[1])
crtt = max(0.0, run["httpPre"]["mean"] - F["http0"])
irtt = max(0.0, run["tcpPre"]["web_api"] - F["web_api0"])
p = run["raceP"] if run.get("raceP") is not None else F["levels"]["10mbit"]["p_netem"]
loads = [json.loads(l) for l in open(os.path.join(here, "results", "probeloads.jsonl"))]
meas = mean(bundle_obs(x)[0] for x in loads if x["runId"] == f"{run['runId']}-probe")

def bundle_at(x):
    ys = [(xl, expected_bundle(F["levels"][name]["curves"], crtt, p)) for name, _, xl in LEVELS]
    i = next((k for k in range(1, len(ys)) if x <= ys[k][0]), len(ys) - 1)
    (x0, y0), (x1, y1) = ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)

x_eq = min((k / 100 for k in range(0, 601)), key=lambda x: abs(bundle_at(x) - meas))
bw = 10e6 / x_eq if x_eq > 0 else 1e12
preds = [{"user": u, "step": s, "page": pg, "o": o,
          "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, F["levels"], bw, p)}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", "predictionsH3.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "raceP": p,
                        "bundleMeas": meas, "bwEq": bw, "preds": preds}) + "\n")
