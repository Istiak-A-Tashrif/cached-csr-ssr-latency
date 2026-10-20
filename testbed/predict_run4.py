#!/usr/bin/env python3
"""Called by the harness after network setup and BEFORE each prospective4 run.
Appends per-action predictions for that run to results/predictions4.jsonl,
using only: frozen model4 parameters, the run's declared workload, and the
pre-run TCP RTT measurement. Refuses to run if model2.py changed since freezing."""
import hashlib, json, os, sys, time
from model4 import analytic_outcomes, predict

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "model4.frozen.json")))
for f in ("model2.py", "model4.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
T0 = {tuple(k.split("|")): v for k, v in F["T0"].items()}
B, tcp0 = F["bytes"], F["tcp0"]

run = json.loads(sys.argv[1])
pre = run["tcpPre"]
crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
preds = [{"user": u, "step": s, "page": p, "o": o,
          "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, T0, B, 10e6, F["kappa"])}
         for u, s, p, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", "predictions4.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "preds": preds}) + "\n")
