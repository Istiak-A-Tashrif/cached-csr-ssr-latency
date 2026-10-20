#!/usr/bin/env python3
"""Called by the harness BEFORE each realH2/repH2 run (home path). Inputs: frozen modelH2,
declared workload, request-level RTT, measured bandwidth and race probability (all pre-run)."""
import hashlib, json, os, sys, time
from modelH2 import analytic_outcomes, predict

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "modelH2.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py", "modelH2.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
run = json.loads(sys.argv[1])
crtt = max(0.0, run["httpPre"]["mean"] - F["http0"])
irtt = max(0.0, run["tcpPre"]["web_api"] - F["web_api0"])
p = run["raceP"] if run.get("raceP") is not None else F["levels"]["10mbit"]["p_netem"]
bw = run.get("bwBps")
preds = [{"user": u, "step": s, "page": pg, "o": o,
          "pred": predict(run["mode"], "initial" if s == 0 else "nav", o, crtt, irtt, F["levels"], bw, p)}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", "predictionsH2.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "crttIn": crtt, "irttIn": irtt, "raceP": p,
                        "bwBps": bw, "preds": preds}) + "\n")
