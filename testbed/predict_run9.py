#!/usr/bin/env python3
"""Called by the harness BEFORE each real9/rep9 run (HTTPS + HTTP/2). Inputs: frozen model9
(netem-calibrated), the declared workload, and the pre-run TCP RTT."""
import hashlib, json, os, sys, time
TAG = os.environ.get("MODEL_TAG", "9")   # v9b: MODEL_TAG=9b
from model9 import analytic_outcomes, predict

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", f"model{TAG}.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py", "model9.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
T0 = {tuple(k.split("|")): v for k, v in F["T0"].items()}; tcp0 = F["tcp0"]
run = json.loads(sys.argv[1]); pre = run["tcpPre"]
crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
preds = [{"user": u, "step": s, "page": pg, "o": o,
          "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, T0, F["bytes"], 10e6, F["curve"], F["correction"])}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", f"predictions{TAG}.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "preds": preds}) + "\n")
