#!/usr/bin/env python3
"""Stage A pilot analysis (stdlib only).

Joins every browser action to the cache outcome on its path, reports achieved
conditional hit ratios, latency per configuration, and a diagnostic check of the
path-based model against two baselines.

Outcome classes (mutually exclusive per action):
  CSR: tq_hit (TanStack served it) | redis_hit | db
  SSR: next_hit (Next data cache)  | redis_hit | db

Model:  E[T(m,a,rtt)] = sum_o P(o | config) * C(m,a,rtt,o)
  C is the mean latency of outcome o, estimated on TRAINING configs only.
  P(o | config) is the outcome mix MEASURED in the evaluated config, so this is
  a conditional diagnostic of the cost model, not a prospective prediction.
Baselines:
  B_nocache: every action costs C(db)            (cache-unaware path model)
  B_mean:    training mean latency for (m,a,rtt) (fixed mean cost)
Validation: cross-workload (fit on one workload, evaluate on the other).
"""
import json, os, random, statistics as st, sys
from collections import Counter, defaultdict

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
def jl(name):
    p = os.path.join(R, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

runs = {r["runId"]: r for r in jl("pilot-runs.jsonl")}
acts = [a for a in jl("pilot.jsonl") if a["runId"] in runs]
api_by_rid = {x["reqId"]: x for x in jl("api.jsonl") if x.get("reqId")}
api_by_resp = {x["respId"]: x for x in jl("api.jsonl") if x.get("respId")}
web_by_aid = {}
for w in jl("web.jsonl"):
    if w.get("aid"):
        web_by_aid.setdefault(w["aid"], w)  # first render for the action

errors = [a for a in acts if "error" in a]
acts = [a for a in acts if "error" not in a]
unclassified = []

def outcome(a):
    if a["mode"] == "csr":
        rids = a["tqRids"]
        if not rids:
            return "tq_hit"
        x = api_by_rid.get(rids[-1])
    else:
        w = web_by_aid.get(a["aid"])
        if w is None:
            return None
        if w["nextCache"] == "hit":
            return "next_hit"
        x = api_by_resp.get(w["respId"])
    if x is None:
        return None
    return "redis_hit" if x["redis"] == "hit" else "db"

for a in acts:
    c = runs[a["runId"]]
    a.update(fe=c["fe"], be=c["be"], rtt=c["rtt"], wl=c["wl"], seed=c["seed"])
    a["o"] = outcome(a)
    if a["o"] is None:
        unclassified.append(a)
acts = [a for a in acts if a["o"] is not None]

def mean(xs): return sum(xs) / len(xs) if xs else float("nan")
def q(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = int(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f) if xs else float("nan")

def cfg_key(a): return (a["mode"], a["fe"], a["be"], a["rtt"], a["wl"])

print(f"runs={len(runs)} actions={len(acts)} errors={len(errors)} unclassified={len(unclassified)}")
for e in errors[:5]:
    print("  error:", e["runId"], e.get("error", "")[:100])

# ---------- 1. achieved hit ratios (conditional on reaching the layer) ----------
print("\n== Achieved conditional hit ratios and DB work, navigations + initial loads ==")
print(f"{'mode':4} {'fe':2} {'be':2} {'wl':6} | {'P(front hit)':>12} {'P(redis hit|reach)':>18} {'DB/action':>9}  n")
groups = defaultdict(list)
for a in acts:
    groups[(a["mode"], a["fe"], a["be"], a["wl"])].append(a)
for k in sorted(groups):
    g = groups[k]; cnt = Counter(a["o"] for a in g); n = len(g)
    front = cnt["tq_hit"] + cnt["next_hit"]
    reach = n - front
    print(f"{k[0]:4} {int(k[1]):2} {int(k[2]):2} {k[3]:6} | {front / n:12.2f} "
          f"{(cnt['redis_hit'] / reach if reach and k[2] else float('nan')):18.2f} {cnt['db'] / n:9.2f}  {n}")

# ---------- 2. latency per configuration ----------
def boot_ci(xs, it=2000, seed=0):
    rnd = random.Random(seed); n = len(xs)
    ms = sorted(mean([xs[rnd.randrange(n)] for _ in range(n)]) for _ in range(it))
    return ms[int(0.025 * it)], ms[int(0.975 * it)]

for action in ("initial", "nav"):
    print(f"\n== {action}: data-visible latency (ms): mean [95% CI over runs], P50, P95 ==")
    print(f"{'rtt':>4} {'wl':6} {'fe':2} {'be':2} | {'CSR mean':>22} {'p50':>7} {'p95':>7} | {'SSR mean':>22} {'p50':>7} {'p95':>7}")
    for rtt in sorted({a["rtt"] for a in acts}):
        for wl in sorted({a["wl"] for a in acts}):
            for fe in (False, True):
                for be in (False, True):
                    row = f"{rtt:>4} {wl:6} {int(fe):2} {int(be):2} |"
                    for mode in ("csr", "ssr"):
                        g = [a for a in acts if a["action"] == action and a["mode"] == mode and a["rtt"] == rtt
                             and a["wl"] == wl and a["fe"] == fe and a["be"] == be]
                        if not g:
                            row += f" {'-':>22} {'-':>7} {'-':>7} |"; continue
                        # runs (seed) are the independent units for the CI
                        per_run = defaultdict(list)
                        for a in g: per_run[a["runId"]].append(a["latencyMs"])
                        rm = [mean(v) for v in per_run.values()]
                        lo, hi = boot_ci(rm) if len(rm) > 1 else (float("nan"),) * 2
                        lat = [a["latencyMs"] for a in g]
                        row += f" {mean(lat):7.1f} [{lo:6.1f},{hi:6.1f}] {q(lat, .5):7.1f} {q(lat, .95):7.1f} |"
                    print(row)

# ---------- 3. interactive vs visible on initial load ----------
print("\n== initial load: visible vs interactive (ms, mean) ==")
for rtt in sorted({a["rtt"] for a in acts}):
    for mode in ("csr", "ssr"):
        g = [a for a in acts if a["action"] == "initial" and a["mode"] == mode and a["rtt"] == rtt]
        print(f"rtt={rtt:>4} {mode}: visible={mean([a['latencyMs'] for a in g]):7.1f} "
              f"interactive={mean([a['interactiveMs'] for a in g if a['interactiveMs'] is not None]):7.1f} "
              f"ttfb={mean([a['ttfb'] for a in g]):7.1f} n={len(g)}")

# ---------- 4. diagnostic model check (cross-workload) ----------
print("\n== Path model (conditional diagnostic): cross-workload validation ==")
def costs(train):
    c = defaultdict(list)
    for a in train: c[(a["mode"], a["action"], a["rtt"], a["o"])].append(a["latencyMs"])
    return {k: mean(v) for k, v in c.items()}
def base_mean(train):
    c = defaultdict(list)
    for a in train: c[(a["mode"], a["action"], a["rtt"])].append(a["latencyMs"])
    return {k: mean(v) for k, v in c.items()}

wls = sorted({a["wl"] for a in acts})
errs = {"model": [], "B_nocache": [], "B_mean": []}
rel = {"model": [], "B_nocache": [], "B_mean": []}
missing = 0
for test_wl in wls:
    train = [a for a in acts if a["wl"] != test_wl]
    test = [a for a in acts if a["wl"] == test_wl]
    C, M = costs(train), base_mean(train)
    cells = defaultdict(list)
    for a in test: cells[(a["mode"], a["action"], a["rtt"], a["fe"], a["be"], a["seed"])].append(a)
    for (mode, action, rtt, fe, be, seed), g in cells.items():
        obs = mean([a["latencyMs"] for a in g])
        mix = Counter(a["o"] for a in g); n = len(g)
        try:
            pred = sum(cnt / n * C[(mode, action, rtt, o)] for o, cnt in mix.items())
        except KeyError:
            missing += 1; continue
        preds = {"model": pred,
                 "B_nocache": C.get((mode, action, rtt, "db"), float("nan")),
                 "B_mean": M[(mode, action, rtt)]}
        for k, p in preds.items():
            errs[k].append(abs(p - obs)); rel[k].append(abs(p - obs) / obs)
print(f"cells evaluated={len(errs['model'])} (skipped, outcome unseen in training: {missing})")
for k in errs:
    e = [x for x in errs[k] if x == x]; r = [x for x in rel[k] if x == x]
    print(f"  {k:10} MAE={mean(e):7.1f} ms  median abs={q(e, .5):6.1f} ms  mean rel={100 * mean(r):5.1f}%  P90 rel={100 * q(r, .9):5.1f}%")

# ---------- 5. CSR vs SSR (paired by seed/workload/caches/rtt) ----------
print("\n== SSR - CSR mean latency difference, per action (ms), paired runs ==")
for action in ("initial", "nav"):
    for rtt in sorted({a["rtt"] for a in acts}):
        for fe in (False, True):
            for be in (False, True):
                diffs = []
                for wl in wls:
                    for seed in sorted({a["seed"] for a in acts}):
                        sel = lambda m: [a["latencyMs"] for a in acts if a["action"] == action and a["mode"] == m and a["rtt"] == rtt
                                         and a["fe"] == fe and a["be"] == be and a["wl"] == wl and a["seed"] == seed]
                        c, s = sel("csr"), sel("ssr")
                        if c and s: diffs.append(mean(s) - mean(c))
                if diffs:
                    lo, hi = boot_ci(diffs) if len(diffs) > 1 else (float("nan"),) * 2
                    print(f"  {action:7} rtt={rtt:>4} fe={int(fe)} be={int(be)}: {mean(diffs):8.1f} [{lo:7.1f},{hi:7.1f}]  (n pairs={len(diffs)})")
