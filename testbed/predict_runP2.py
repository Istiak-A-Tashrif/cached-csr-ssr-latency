#!/usr/bin/env python3
"""Called BEFORE each concP2/repP2 run: per-action predictions from the frozen modelP2."""
import hashlib, json, os, sys, time
from modelP2 import analytic_outcomes, predict_run

here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", "modelP2.frozen.json")))
for f in ("modelP2.py", "model5.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
run = json.loads(sys.argv[1])
outs = analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])
acts = [(run["mode"], "initial" if s == 0 else "nav", o) for _, s, _, o in outs]
pred = predict_run(acts, run["n"], F["R1"], F["D"], F["P"], F["C1"])
preds = [{"user": u, "step": s, "page": pg, "o": o, "pred": p} for (u, s, pg, o), p in zip(outs, pred)]
with open(os.path.join(here, "results", "predictionsP2.jsonl"), "a") as f:
    f.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "n": run["n"], "preds": preds}) + "\n")
