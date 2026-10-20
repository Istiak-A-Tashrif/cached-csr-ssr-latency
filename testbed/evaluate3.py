#!/usr/bin/env python3
"""Evaluate prospective3 against the per-run predictions written before each run."""
import json, os, random
from collections import defaultdict
from lib import R, jl, load, mean

acts, runs, errors, unc = load("prosp3.jsonl", "prosp3-runs.jsonl")
preds = {p["runId"]: p for p in jl("predictions3.jsonl")}
v1 = json.load(open(os.path.join(R, "predictions.frozen.json")))
line = lambda ab, x: ab[0] + ab[1] * x
print(f"runs={len(runs)} actions={len(acts)} errors={len(errors)} unclassified={len(unc)} predicted runs={len(preds)}")

# Prospective check: every prediction written before the run's first request.
# The first action of a run always reaches the API (caches start cold), so the
# earliest API log entry tagged with the run marks the run's start.
first_ts = defaultdict(lambda: float("inf"))
for x in jl("api.jsonl"):
    if x.get("runId") in runs: first_ts[x["runId"]] = min(first_ts[x["runId"]], x["ts"] / 1000)
late = [r for r in runs if r not in preds or preds[r]["writtenAt"] >= first_ts[r]]
print(f"predictions written before their run started: {len(runs) - len(late)}/{len(runs)}")

# Outcome agreement and drift.
pmap = {(r, x["user"], x["step"]): x for r, p in preds.items() for x in p["preds"]}
agree = sum(pmap[(a["runId"], a["user"], a["step"])]["o"] == a["o"] for a in acts)
print(f"analytic outcomes vs measured: {agree}/{len(acts)}")
drift = defaultdict(list)
for r in runs.values():
    for l in ("client_web", "client_api", "web_api"):
        drift[l].append(r["tcpPost"][l] - r["tcpPre"][l])
print("TCP RTT drift post-pre (ms): " + ", ".join(f"{l} mean {mean(v):+.2f} max |{max(map(abs, v)):.2f}|" for l, v in drift.items()))

def boot(xs, it=4000, seed=1):
    r = random.Random(seed); n = len(xs)
    ms = sorted(mean(xs[r.randrange(n)] for _ in range(n)) for _ in range(it))
    return ms[int(.025 * it)], ms[int(.975 * it)]

cells = defaultdict(lambda: defaultdict(lambda: {"obs": [], "v3": [], "Bn": [], "Bm": []}))
for a in acts:
    act = a["action"]; p = preds[a["runId"]]
    x = p["crttIn"]
    c = cells[(a["mode"], a["fe"], a["rtt"], a["irtt"], act)][a["seed"]]
    c["obs"].append(a["latencyMs"]); c["v3"].append(pmap[(a["runId"], a["user"], a["step"])]["pred"])
    c["Bn"].append(line(v1["costLines"][f"{a['mode']}|{act}|db"], x))
    c["Bm"].append(line(v1["baselineMeanLines"][f"{a['mode']}|{act}"], x))

print("\n== Mean data-visible latency per cell (runs are units) ==")
err = defaultdict(list)
for k in sorted(cells):
    seeds = cells[k]
    obs = [mean(s["obs"]) for s in seeds.values()]
    o = mean(obs); lo, hi = boot(obs)
    row = {m: mean(mean(s[m]) for s in seeds.values()) for m in ("v3", "Bn", "Bm")}
    for m, v in row.items(): err[m].append((abs(v - o), abs(v - o) / o, lo <= v <= hi))
    print(f"  {k[4]:7} {k[0]} caches={'on ' if k[1] else 'off'} crtt={k[2]:3} irtt={k[3]:2}: obs {o:7.1f} [{lo:7.1f},{hi:7.1f}]  v3 {row['v3']:7.1f} ({100 * (row['v3'] - o) / o:+5.1f}%)  B_nocache {row['Bn']:7.1f}  B_mean {row['Bm']:7.1f}")
print()
for m, name in (("v3", "v3"), ("Bn", "B_nocache"), ("Bm", "B_mean")):
    v = err[m]
    print(f"  {name:10} MAE={mean(e for e, _, _ in v):6.1f} ms  mean rel={100 * mean(r for _, r, _ in v):5.1f}%  max rel={100 * max(r for _, r, _ in v):5.1f}%  inside run-CI: {sum(i for _, _, i in v)}/{len(v)}")

print("\n== SSR - CSR (paired by seed) ==")
for crtt in sorted({k[2] for k in cells}):
    for irtt in sorted({k[3] for k in cells}):
        for fe in (False, True):
            for act in ("initial", "nav"):
                c, s = cells.get(("csr", fe, crtt, irtt, act)), cells.get(("ssr", fe, crtt, irtt, act))
                if not c or not s: continue
                ks = [x for x in c if x in s]
                d_obs = [mean(s[x]["obs"]) - mean(c[x]["obs"]) for x in ks]
                d_pred = mean(mean(s[x]["v3"]) - mean(c[x]["v3"]) for x in ks)
                lo, hi = boot(d_obs)
                print(f"  {act:7} crtt={crtt:3} irtt={irtt:2} caches={'on ' if fe else 'off'}: obs {mean(d_obs):8.1f} [{lo:7.1f},{hi:7.1f}]  v3 {d_pred:8.1f} {'(in CI)' if lo <= d_pred <= hi else f'({d_pred - mean(d_obs):+.1f})'}")
