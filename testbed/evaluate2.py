#!/usr/bin/env python3
"""Compare the prospective2 runs with the frozen model-v2 predictions."""
import json, os, random
from collections import defaultdict
from lib import R, load, mean
from model2 import analytic_outcomes

pred = json.load(open(os.path.join(R, "predictions2.frozen.json")))
acts, runs, errors, unc = load("prosp2.jsonl", "prosp2-runs.jsonl")
print(f"runs={len(runs)} actions={len(acts)} errors={len(errors)} unclassified={len(unc)}  (frozen {pred['frozenAt']})")
irtts = defaultdict(list)
for r in runs.values(): irtts[r["irtt"]].append(r["measuredRtt"]["web_api"])
print("measured web<->api RTT by nominal:", {k: round(mean(v), 1) for k, v in irtts.items()})

by_run = defaultdict(dict)
for a in acts: by_run[a["runId"]][(a["user"], a["step"])] = a["o"]
agree = total = 0
for rid, r in runs.items():
    for u, s, _p, o in analytic_outcomes(r["mode"], r["fe"], r["be"], r["users"]):
        if (u, s) in by_run[rid]: total += 1; agree += by_run[rid][(u, s)] == o
print(f"analytic outcomes vs measured: {agree}/{total}")

def boot(xs, it=4000, seed=1):
    r = random.Random(seed); n = len(xs)
    ms = sorted(mean(xs[r.randrange(n)] for _ in range(n)) for _ in range(it))
    return ms[int(.025 * it)], ms[int(.975 * it)]

def run_means(mode, fe, be, crtt, irtt, action):
    per = defaultdict(list)
    for a in acts:
        if (a["mode"], a["fe"], a["be"], a["rtt"], a["irtt"], a["action"]) == (mode, fe, be, crtt, irtt, action):
            per[a["seed"]].append(a["latencyMs"])
    return {s: mean(v) for s, v in per.items()}

MODELS = ("v2", "v1", "B_nocache", "B_mean")
print("\n== Mean data-visible latency (ms): observed [95% CI] vs predictions ==")
err = defaultdict(list)
for c in pred["cells"]:
    rm = run_means(c["mode"], c["fe"], c["be"], c["crtt"], c["irtt"], c["action"])
    if not rm: continue
    obs = mean(rm.values()); lo, hi = boot(list(rm.values()))
    for k in MODELS: err[k].append((abs(c[k] - obs), abs(c[k] - obs) / obs))
    print(f"  {c['action']:7} {c['mode']} caches={'on ' if c['fe'] else 'off'} crtt={c['crtt']:3} irtt={c['irtt']:2}: "
          f"obs {obs:7.1f} [{lo:7.1f},{hi:7.1f}] | v2 {c['v2']:7.1f} ({100 * (c['v2'] - obs) / obs:+5.1f}%)  v1 {c['v1']:7.1f}  B_nocache {c['B_nocache']:7.1f}  B_mean {c['B_mean']:7.1f}")
print()
for k in MODELS:
    v = err[k]
    print(f"  {k:10} MAE={mean(e for e, _ in v):7.1f} ms  mean rel={100 * mean(r for _, r in v):5.1f}%  max rel={100 * max(r for _, r in v):5.1f}%  (n={len(v)})")

print("\n== SSR - CSR, paired by seed (ms) ==")
for d in pred["ssrMinusCsr"]:
    c = run_means("csr", d["fe"], d["be"], d["crtt"], d["irtt"], d["action"])
    s = run_means("ssr", d["fe"], d["be"], d["crtt"], d["irtt"], d["action"])
    diffs = [s[k] - c[k] for k in c if k in s]
    if not diffs: continue
    lo, hi = boot(diffs); m = mean(diffs)
    flag = lambda p: ("in CI" if lo <= p <= hi else f"{p - m:+.1f}")
    print(f"  {d['action']:7} crtt={d['crtt']:3} irtt={d['irtt']:2} caches={'on ' if d['fe'] else 'off'}: obs {m:8.1f} [{lo:7.1f},{hi:7.1f}] | "
          + "  ".join(f"{k} {d[k]:7.1f} ({flag(d[k])})" for k in MODELS))
