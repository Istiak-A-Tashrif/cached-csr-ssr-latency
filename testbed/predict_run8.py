#!/usr/bin/env python3
"""Called by the harness after network setup and the race + bandwidth probes, BEFORE each
real8/rep8 run. Inputs: frozen model8 (netem-calibrated at two bandwidths), the declared
workload, pre-run TCP RTT, pre-run race probability and pre-run bandwidth."""
import hashlib, json, os, sys, time
from model8 import analytic_outcomes, predict, x_of

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "model8.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py", "model8.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
tcp0 = F["tcp0"]
run = json.loads(sys.argv[1]); pre = run["tcpPre"]
crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
p = run["raceP"] if run.get("raceP") is not None else F["cap"]["p_netem"]
bw = run.get("bwBps")
preds = [{"user": u, "step": s, "page": pg, "o": o, "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, F, bw, p)}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", "predictions8.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "raceP": p,
                        "bwBps": bw, "x": x_of(bw), "preds": preds}) + "\n")
