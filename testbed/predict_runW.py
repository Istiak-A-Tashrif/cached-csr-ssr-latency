"""Item 8: per-run stale-fraction prediction, written BEFORE the run starts."""
import hashlib, json, sys, time
from staleness import layer_cfg, simulate, predicted_stale_fraction

M = json.load(open("results/modelW.frozen.json"))
for f, h in M["files"].items():
    if hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] != h: raise SystemExit(f"{f} changed since freeze")
run = json.loads(sys.argv[1])
crtt_ms = run["tcpPre"]["client_web"]

def gap(mode, action, outcome):
    g = M["gap"][f"{mode}|{action}|{outcome}"]
    return g["a"] + g["b"] * crtt_ms

w = simulate(run["users"], gap, layer_cfg(run), crtt_ms / 1000)
pred = predicted_stale_fraction(w, run["lam"] / run["pages"])
with open(f"results/predictionsW.jsonl", "a") as fh:
    fh.write(json.dumps({"runId": run["runId"], "ts": time.time() * 1000, "sha": M["sha"], "pred": pred, "n": len(w)}) + "\n")
print(f"predicted stale {pred:.3f}")
