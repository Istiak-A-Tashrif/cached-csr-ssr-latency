#!/usr/bin/env python3
"""Called by the harness BEFORE each realH/repH run (home path). Inputs: frozen modelH
(hardware-split calibration), declared workload, pre-run TCP RTT, pre-run race probability."""
import hashlib, json, os, sys, time
from model7 import analytic_outcomes, predict

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "modelH.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
T0 = {tuple(k.split("|")): v for k, v in F["T0"].items()}; tcp0 = F["tcp0"]
run = json.loads(sys.argv[1]); pre = run["tcpPre"]
crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
p = run["raceP"] if run.get("raceP") is not None else F["p_netem"]
preds = [{"user": u, "step": s, "page": pg, "o": o,
          "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, T0, F["bytes"], 10e6, F["curves"], F["correction"], p)}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", "predictionsH.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "raceP": p,
                        "bwBps": run.get("bwBps"), "preds": preds}) + "\n")
