#!/usr/bin/env python3
"""B4 offline (TWEB revision), retrospective: constrained policy selection on experiment X.

Candidates: the 9 caching policies of experiment X (rendering mode x browser/framework layer x
Redis layer). For each test (testX: d = 25 ms, RTT 100; repX: d = 100 ms, RTT 200) and staleness
limit eps in {1, 5, 10, 50}%:
  selector  argmin predicted mean latency subject to predicted stale share <= eps (modelX,
            frozen from calibW, which has no writes and no added server work)
  oracle    argmin observed mean latency subject to observed stale share <= eps
Regret = (L_selected - L_oracle) / L_oracle on the observed values; a selection whose observed
stale share exceeds eps is a violation (reported with its magnitude, never as regret).
Observed values are evaluated on runs NOT used by the tuning baseline (seeds 3..8 of each cell),
so every method is scored on the same held-out runs.
Comparison policies:
  default    SSR, Next data cache TTL + Redis TTL (framework defaults with an application cache)
  nocache    SSR without caches
  fixed      the single policy best on the OTHER test (chosen on training data)
  tuning     2 pilot runs per policy (seeds 1-2 of each cell: 18 runs), pick by pilot means
Cost: modelX's calibration (calibW runs) vs tuning's 18 pilot runs, per new deployment condition.
usage: python3 b4_offline.py
"""
import bisect, collections, json, os

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
EPS = (0.01, 0.05, 0.10, 0.50)


def load(tag):
    runs = {r["runId"]: r for r in map(json.loads, open(os.path.join(R, f"{tag}-runs.jsonl")))}
    preds = {p["runId"]: p for p in map(json.loads, open(os.path.join(R, "predictionsX.jsonl"))) if p["runId"] in runs}
    W = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in map(json.loads, open(os.path.join(R, "writes.jsonl"))):
        if w["runId"] in runs: W[w["runId"]][w["productId"]].append(w["committed"])
    for d in W.values():
        for v in d.values(): v.sort()
    per = collections.defaultdict(lambda: {"lat": [], "stale": []})
    for v in map(json.loads, open(os.path.join(R, f"{tag}.jsonl"))):
        if v.get("runId") not in runs or "error" in v: continue
        run = runs[v["runId"]]
        st = any(shown != run["stock0"][str(pid)] + bisect.bisect_right(W[v["runId"]][pid], v["wall"]) for pid, shown in v["rows"])
        per[v["runId"]]["lat"].append(v["latencyMs"]); per[v["runId"]]["stale"].append(st)
    cells = collections.defaultdict(list)
    for rid, d in per.items():
        r = runs[rid]
        pl = [x["ms"] for x in preds[rid]["lat"]]
        cells[f"{r['mode']}-fe{r['fe'] or 'off'}-rd{r['rp'] or 'off'}"].append(
            {"seed": r["seed"], "lat": sum(d["lat"]) / len(d["lat"]), "stale": sum(d["stale"]) / len(d["stale"]),
             "plat": sum(pl) / len(pl), "pstale": preds[rid]["stale"]})
    return cells


def agg(rs, key): return sum(r[key] for r in rs) / len(rs)


def choose(vals, eps):
    feas = [c for c, (l, s) in vals.items() if s <= eps]
    return min(feas, key=lambda c: vals[c][0]) if feas else None


tests = {t: load(t) for t in ("testX", "repX")}
out = {}
for tag, cells in tests.items():
    seeds = sorted({r["seed"] for rs in cells.values() for r in rs})
    pilot, held = set(seeds[:2]), set(seeds[2:])
    obs = {c: (agg([r for r in rs if r["seed"] in held], "lat"), agg([r for r in rs if r["seed"] in held], "stale")) for c, rs in cells.items()}
    pred = {c: (agg(rs, "plat"), agg(rs, "pstale")) for c, rs in cells.items()}
    tune = {c: (agg([r for r in rs if r["seed"] in pilot], "lat"), agg([r for r in rs if r["seed"] in pilot], "stale")) for c, rs in cells.items()}
    other = tests["repX" if tag == "testX" else "testX"]
    oth = {c: (agg(rs, "lat"), agg(rs, "stale")) for c, rs in other.items()}
    res = {}
    for eps in EPS:
        best = choose(obs, eps)
        picks = {"selector": choose(pred, eps), "tuning": choose(tune, eps), "fixed": choose(oth, eps),
                 "default": "ssr-fettl-rdttl", "nocache": "ssr-feoff-rdoff"}
        row = {"oracle": best}
        for m, c in picks.items():
            if c is None: row[m] = {"pick": None, "abstain": True}; continue
            l, s = obs[c]
            row[m] = {"pick": c, "violation": s > eps, "excess_stale": max(0.0, s - eps),
                      "regret": None if s > eps or best is None else (l - obs[best][0]) / obs[best][0]}
        res[f"{eps:.2f}"] = row
    out[tag] = {"observed": obs, "predicted": pred, "selection": res}
    print(f"\n{tag}: observed (held-out seeds) vs predicted  [mean latency ms, stale share]")
    for c in sorted(obs):
        print(f"  {c:22s} obs {obs[c][0]:7.1f} {obs[c][1]:.3f}   pred {pred[c][0]:7.1f} {pred[c][1]:.3f}")
    for eps, row in res.items():
        print(f"  eps {eps}: oracle {row['oracle']}")
        for m in ("selector", "tuning", "fixed", "default", "nocache"):
            r = row[m]
            if r.get("abstain"): print(f"     {m:9s} abstains"); continue
            tag_ = "VIOLATES (+%.3f)" % r["excess_stale"] if r["violation"] else "regret %+.1f%%" % (100 * r["regret"])
            print(f"     {m:9s} {r['pick']:22s} {tag_}")
calib_runs = sum(1 for _ in open(os.path.join(R, "calibW-runs.jsonl")))
out["cost"] = {"model_calibration_runs": calib_runs, "tuning_runs_per_condition": 18}
print(f"\ncost: modelX calibration {calib_runs} runs once (no writes, no server work); tuning 18 pilot runs per new condition")
os.makedirs(os.path.join(R, "revision"), exist_ok=True)
json.dump(out, open(os.path.join(R, "revision", "B4-offline.json"), "w"), indent=1)
