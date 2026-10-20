"""Experiment X: per-run prediction (stale share and per-view latency), written BEFORE the run."""
import hashlib, json, sys, time
from modelX import layer_cfg, simulate, stale_fraction

M = json.load(open("results/modelX.frozen.json"))
for f, h in M["files"].items():
    if hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] != h: raise SystemExit(f"{f} changed since freeze")
run = json.loads(sys.argv[1])
crtt = run["tcpPre"]["client_web"]
fit = lambda tab: (lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt)
lam_p = run["lam"] / run["pages"]
v = simulate(run["users"], fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, lam_p)
steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
with open("results/predictionsX.jsonl", "a") as fh:
    fh.write(json.dumps({"runId": run["runId"], "ts": time.time() * 1000, "sha": M["sha"], "stale": stale_fraction(v, lam_p),
                         "lat": [{"user": u, "step": s, "ms": 1000 * l} for (u, s), (_, l, _) in zip(steps, v)]}) + "\n")
print(f"predicted stale {stale_fraction(v, lam_p):.3f}")
