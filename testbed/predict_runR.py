#!/usr/bin/env python3
"""Revision model R: per-run prediction, written BEFORE the run (TWEB revision, B1/B2/B4).
Inputs: frozen modelR (= modelX calibration + declared write process), the run's declared
sessions, cache policy and TTLs, write process and server work d, and the pre-run TCP RTT.
Output (results/predictionsR.jsonl): stale share, per-view latency and outcome distribution."""
import hashlib, json, os, sys, time
from modelR import layer_cfg, simulate, stale_fraction
from writeproc import p0_factory

here = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(here, "results", "modelR.frozen.json")))
for f, h in M["files"].items():
    if hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()[:16] != h: raise SystemExit(f"{f} changed since freeze")
run = json.loads(open(sys.argv[1]).read()) if sys.argv[1].endswith(".json") else json.loads(sys.argv[1])
crtt = run["tcpPre"]["client_web"]
fit = lambda tab: (lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt)
p0 = p0_factory(run["proc"], run["pages"])
v = simulate(run["users"], fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0)
steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
with open(os.path.join(here, "results", "predictionsR.jsonl"), "a") as fh:
    fh.write(json.dumps({"runId": run["runId"], "ts": time.time() * 1000, "sha": M["sha"], "stale": stale_fraction(v, p0),
                         "views": [{"user": u, "step": s, "ms": 1000 * l, "dist": d} for (u, s), (_, l, d) in zip(steps, v)]}) + "\n")
print(f"predicted stale {stale_fraction(v, p0):.3f}")
