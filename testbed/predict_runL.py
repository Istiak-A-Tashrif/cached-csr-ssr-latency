#!/usr/bin/env python3
"""Per-run predictions BEFORE each run (experiments Q, R): frozen per-level v7 calibration
(results/modelL<MODEL_TAG>.frozen.json), declared workload, pre-run TCP RTT and race probability.
With several levels (R: CPU rate) the prediction is linear in the run's level value between the
neighbouring levels (end segments extended)."""
import hashlib, json, os, sys, time
from model7 import analytic_outcomes, predict

TAG = os.environ["MODEL_TAG"]
here = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(here, "results", f"modelL{TAG}.frozen.json")))
for f in ("model2.py", "model4.py", "model5.py", "model7.py"):
    assert hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest() == F[f.replace(".py", "_sha256")], f"{f} changed after freeze"
run = json.loads(sys.argv[1]); pre = run["tcpPre"]
lv = sorted(F["levels"].items(), key=lambda kv: float(kv[0]))
x = float(run.get(F["levelKey"], 1)) if F["levelKey"] else float(lv[0][0])

def pred_level(L, mode, action, o):
    T0 = {tuple(k.split("|")): v for k, v in L["T0"].items()}; tcp0 = L["tcp0"]
    crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
    irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
    p = run["raceP"] if run.get("raceP") is not None else L["p_netem"]
    return predict(mode, action, o, crtt, irtt, T0, L["bytes"], 10e6, L["curves"], L["correction"], p)

def pred(mode, action, o):
    if len(lv) == 1: return pred_level(lv[0][1], mode, action, o)
    i = next((k for k in range(1, len(lv)) if x <= float(lv[k][0])), len(lv) - 1)
    (x0, L0), (x1, L1) = (float(lv[i - 1][0]), lv[i - 1][1]), (float(lv[i][0]), lv[i][1])
    y0, y1 = pred_level(L0, mode, action, o), pred_level(L1, mode, action, o)
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)

preds = [{"user": u, "step": s, "page": pg, "o": o, "pred": pred(run["mode"], "initial" if s == 0 else "nav", o)}
         for u, s, pg, o in analytic_outcomes(run["mode"], run["fe"], run["be"], run["users"])]
with open(os.path.join(here, "results", f"predictions{TAG}.jsonl"), "a") as fh:
    fh.write(json.dumps({"runId": run["runId"], "writtenAt": time.time(), "level": x, "raceP": run.get("raceP"), "preds": preds}) + "\n")
