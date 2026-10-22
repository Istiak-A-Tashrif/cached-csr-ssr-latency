#!/usr/bin/env python3
"""Model RC (Conduit, B5): per-run prediction, written BEFORE the run. As predict_runR.py, with the
Conduit calibration (results/modelRC.frozen.json from cdCal) or, for the zero-recalibration
predictions, the catalogue's (results/modelR.frozen.json), and popularity-weighted writes.
usage: predict_runRC.py <run.json> [--zero]"""
import hashlib, json, os, sys, time
from modelRC import layer_cfg, simulate, stale_fraction, page_p0

here = os.path.dirname(os.path.abspath(__file__))
zero = "--zero" in sys.argv
M = json.load(open(os.path.join(here, "results", "modelR.frozen.json" if zero else "modelRC.frozen.json")))
F = json.load(open(os.path.join(here, "results", "modelRC.frozen.json")))   # code hashes and popularity
for f, h in F["files"].items():
    if hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()[:16] != h: raise SystemExit(f"{f} changed since freeze")
run = json.loads(open(sys.argv[1]).read())
crtt = run["tcpPre"]["client_web"]
fit = lambda tab: (lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt)
probs = {int(k): v for k, v in F["page_probs"].items()}
p0 = page_p0(run["proc"], probs)
v = simulate(run["users"], fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0)
steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
out = "predictionsRC0.jsonl" if zero else "predictionsRC.jsonl"
with open(os.path.join(here, "results", out), "a") as fh:
    fh.write(json.dumps({"runId": run["runId"], "ts": time.time() * 1000, "sha": F["sha"], "zero": zero, "stale": stale_fraction(v, p0),
                         "views": [{"user": u, "step": s, "ms": 1000 * l, "dist": d} for (u, s), (_, l, d, _) in zip(steps, v)]}) + "\n")
print(f"predicted stale {stale_fraction(v, p0):.3f}{' (zero recalibration)' if zero else ''}")
