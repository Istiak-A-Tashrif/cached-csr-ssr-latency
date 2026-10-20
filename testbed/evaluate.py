#!/usr/bin/env python3
"""Compare the Week 3 evaluation runs with the frozen predictions."""
import json, os, random
from collections import Counter, defaultdict
from lib import R, load, mean

pred = json.load(open(os.path.join(R, "predictions.frozen.json")))
acts, runs, errors, unc = load("prosp.jsonl", "prosp-runs.jsonl")
print(f"runs={len(runs)} actions={len(acts)} errors={len(errors)} unclassified={len(unc)}  (predictions frozen {pred['frozenAt']})")

def boot(xs, it=4000, seed=1):
    r = random.Random(seed); n = len(xs)
    ms = sorted(mean(xs[r.randrange(n)] for _ in range(n)) for _ in range(it))
    return ms[int(.025 * it)], ms[int(.975 * it)]

def run_means(mode, fe, be, rtt, action):
    per = defaultdict(list)
    for a in acts:
        if (a["mode"], a["fe"], a["be"], a["rtt"], a["action"]) == (mode, fe, be, rtt, action):
            per[a["seed"]].append(a["latencyMs"])
    return {s: mean(v) for s, v in per.items()}

print("\n== Outcome mix: calibration (RTT 0) vs measured here ==")
for c in pred["cells"]:
    if c["rtt"] != 40 and c["rtt"] != 300: continue
    got = Counter(a["o"] for a in acts if (a["mode"], a["fe"], a["be"], a["rtt"], a["action"]) ==
                  (c["mode"], c["fe"], c["be"], c["rtt"], c["action"]))
    n = sum(got.values())
    if c["action"] == "nav":
        print(f"  {c['mode']} fe={int(c['fe'])} rtt={c['rtt']:3}: calib {dict((k, round(v, 2)) for k, v in c['mix'].items())}  measured {dict((k, round(v / n, 2)) for k, v in got.items())}")

print("\n== Mean data-visible latency: predicted vs observed (ms) ==")
err = defaultdict(list)
for c in pred["cells"]:
    rm = run_means(c["mode"], c["fe"], c["be"], c["rtt"], c["action"])
    if not rm: continue
    obs = mean(rm.values()); lo, hi = boot(list(rm.values()))
    for k in ("model", "B_nocache", "B_mean"):
        err[k].append((abs(c[k] - obs), abs(c[k] - obs) / obs))
    print(f"  {c['action']:7} {c['mode']} fe={int(c['fe'])} rtt={c['rtt']:3}: obs {obs:8.1f} [{lo:7.1f},{hi:7.1f}]  model {c['model']:8.1f}  B_nocache {c['B_nocache']:8.1f}  B_mean {c['B_mean']:8.1f}")
for k, v in err.items():
    print(f"  {k:10} MAE={mean(e for e, _ in v):7.1f} ms   mean rel={100 * mean(r for _, r in v):5.1f}%   max rel={100 * max(r for _, r in v):5.1f}%")

print("\n== SSR - CSR (paired by seed): predicted vs observed (ms) ==")
for d in pred["ssrMinusCsr"]:
    c = run_means("csr", d["fe"], d["be"], d["rtt"], d["action"]); s = run_means("ssr", d["fe"], d["be"], d["rtt"], d["action"])
    diffs = [s[k] - c[k] for k in c if k in s]
    if not diffs: continue
    lo, hi = boot(diffs)
    inside = lo <= d["model"] <= hi
    print(f"  {d['action']:7} rtt={d['rtt']:3} fe={int(d['fe'])} be={int(d['be'])}: obs {mean(diffs):8.1f} [{lo:7.1f},{hi:7.1f}]  "
          f"model {d['model']:8.1f}{' (in CI)' if inside else ''}  B_nocache {d['B_nocache']:7.1f}  B_mean {d['B_mean']:7.1f}  sign {'OK' if (mean(diffs) > 0) == (d['model'] > 0) else 'WRONG'}")
