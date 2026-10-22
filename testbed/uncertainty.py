#!/usr/bin/env python3
"""A4 (TWEB revision): uncertainty with the run as the unit, retrospective.

Latency (from A2's per-seed cell means, results/revision/A2-baselines.json)
  Estimand: a test's mean relative error = equal-weight mean over cells of |pred - obs| / obs,
  where obs and pred are equal-weight means over the cell's runs (one run per seed and cell).
  Block bootstrap over seeds: when every cell has the same seed set, one resample of seeds is
  applied to all cells (runs of a seed share the workload sessions and time window); otherwise
  seeds are resampled within each cell. 10,000 resamples; 95% percentile intervals for the
  model's error, the ridge baseline's error and their paired difference.
Tails (descriptive): observed p50/p90/p95/p99 per action type vs the predicted mean.
Staleness (W2, X tests): per-cell stale-view share with a run-level bootstrap interval, the
  oracle replicated from evaluateW.py.
usage: python3 uncertainty.py
"""
import bisect, collections, json, os, random, sys
from lib import jl, load, mean

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
B = 10000


def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))]


def latency():
    res = json.load(open(os.path.join(R, "revision", "A2-baselines.json")))
    out = []
    for r in res:
        cs = r["cellseed"]
        seedsets = {tuple(sorted(v)) for v in cs.values()}
        common = len(seedsets) == 1
        rng = random.Random(1)

        def err(sample, m):
            e = []
            for k, v in cs.items():
                ss = sample(k)
                o = mean(v[s]["obs"] for s in ss); p = mean(v[s][m] for s in ss)
                e.append(abs(p - o) / o)
            return 100 * mean(e)

        point = {m: err(lambda k: list(cs[k]), m) for m in ("model", "ridge")}
        boots = {"model": [], "ridge": [], "diff": []}
        for _ in range(B):
            if common:
                seeds = list(next(iter(seedsets))); draw = [rng.choice(seeds) for _ in seeds]
                sample = lambda k: draw
            else:
                draws = {k: [rng.choice(list(cs[k])) for _ in cs[k]] for k in cs}
                sample = lambda k: draws[k]
            em, er = err(sample, "model"), err(sample, "ridge")
            boots["model"].append(em); boots["ridge"].append(er); boots["diff"].append(em - er)
        nseeds = min(len(v) for v in cs.values())
        out.append({"tag": r["tag"], "seeds_per_cell": nseeds, "cells": len(cs), "common_seeds": common, **{
            f"{m}": [point[m] if m != "diff" else point["model"] - point["ridge"], pct(boots[m], .025), pct(boots[m], .975)]
            for m in ("model", "ridge", "diff")}})
    return out


def tails():
    tests = [("prosp5", "", ""), ("rep5", "", ""), ("real7", "server-final/", "server-final"), ("rep7", "server-final/", "server-final"),
             ("real8b", "server-final/", "server-final"), ("rep8b", "server-final/", "server-final"),
             ("real9", "server-final/", "server-final"), ("rep9", "server-final/", "server-final"),
             ("testS", "", ""), ("repS", "", ""), ("testQ", "", ""), ("repQ", "", ""),
             ("realH3", "", "server-final"), ("repH3", "", "server-final")]
    pf = {"prosp5": "predictions5.jsonl", "rep5": "predictions5.jsonl", "real7": "server-final/predictions7.jsonl",
          "rep7": "server-final/predictions7.jsonl", "real8b": "server-final/predictions8b.jsonl", "rep8b": "server-final/predictions8b.jsonl",
          "real9": "server-final/predictions9.jsonl", "rep9": "server-final/predictions9.jsonl", "testS": "predictionsS.jsonl",
          "repS": "predictionsS.jsonl", "testQ": "predictionsQ.jsonl", "repQ": "predictionsQ.jsonl",
          "realH3": "predictionsH3.jsonl", "repH3": "predictionsH3.jsonl"}
    out = []
    for tag, sub, srv in tests:
        os.environ["SERVER_LOGS"] = srv
        acts, runs, _, _ = load(f"{sub}{tag}.jsonl", f"{sub}{tag}-runs.jsonl")
        pm = {(r, x["user"], x["step"]): x["pred"] for r, p in ((p["runId"], p) for p in jl(pf[tag])) for x in p["preds"]}
        by = collections.defaultdict(lambda: ([], []))
        for a in acts:
            # ratio of each observed action to its own predicted mean pools cells with different RTTs
            by[(a["mode"], a["action"])][0].append(a["latencyMs"] / pm[(a["runId"], a["user"], a["step"])])
        for k, (rs, _) in sorted(by.items()):
            out.append({"tag": tag, "path": "|".join(k), "n": len(rs), "mean": mean(rs),
                        **{f"p{int(q * 100)}": pct(rs, q) for q in (.5, .9, .95, .99)}})
    return out


def staleness():
    out = []
    writes_all = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in map(json.loads, open(os.path.join(R, "writes.jsonl"))):
        writes_all[w["runId"]][w["productId"]].append(w["committed"])
    for tag, mfile, pfile in (("testW2", "modelW", "predictionsW.jsonl"), ("repW2", "modelW", "predictionsW.jsonl"),
                              ("testX", "modelX", "predictionsX.jsonl"), ("repX", "modelX", "predictionsX.jsonl")):
        runs = {r["runId"]: r for r in map(json.loads, open(os.path.join(R, f"{tag}-runs.jsonl")))}
        preds = {p["runId"]: p for p in map(json.loads, open(os.path.join(R, pfile))) if p["runId"] in runs}
        per_run = collections.defaultdict(list)
        for r in map(json.loads, open(os.path.join(R, f"{tag}.jsonl"))):
            if r.get("runId") not in runs or "error" in r: continue
            run = runs[r["runId"]]; st = False
            for pid, shown in r["rows"]:
                ts = sorted(writes_all[r["runId"]][pid])
                st |= shown != run["stock0"][str(pid)] + bisect.bisect_right(ts, r["wall"])
            per_run[r["runId"]].append(st)
        cells = collections.defaultdict(list)
        for rid, v in per_run.items():
            run = runs[rid]
            pr = preds[rid]["pred"] if "pred" in preds[rid] else preds[rid]["stale"]
            cells[f"{run['mode']}-fe{run['fe'] or 'off'}-redis{run['rp'] or 'off'}"].append((sum(v), len(v), pr))
        rng = random.Random(2)
        for c, rr in sorted(cells.items()):
            obs = sum(s for s, _, _ in rr) / sum(n for _, n, _ in rr)
            pred = sum(p * n for _, n, p in rr) / sum(n for _, n, _ in rr)
            bs = []
            for _ in range(B):
                d = [rng.choice(rr) for _ in rr]; bs.append(sum(s for s, _, _ in d) / sum(n for _, n, _ in d))
            out.append({"tag": tag, "cell": c, "runs": len(rr), "views": sum(n for _, n, _ in rr), "obs": obs,
                        "ci": [pct(bs, .025), pct(bs, .975)], "pred": pred, "pred_in_ci": pct(bs, .025) <= pred <= pct(bs, .975)})
    return out


if __name__ == "__main__":
    L = latency(); T = tails(); S = staleness()
    print("Latency mean relative error, 95% block-bootstrap intervals (unit: run; seeds as blocks)")
    print(f"{'test':10s} {'seeds':>5s} {'cells':>5s}  {'model':>22s}  {'ridge':>22s}  {'model - ridge':>24s}")
    for r in L:
        f = lambda v: f"{v[0]:5.2f} [{v[1]:5.2f},{v[2]:5.2f}]"
        print(f"{r['tag']:10s} {r['seeds_per_cell']:5d} {r['cells']:5d}  {f(r['model']):>22s}  {f(r['ridge']):>22s}  {f(r['diff']):>24s}"
              + ("" if r["common_seeds"] else "  (per-cell resampling)"))
    print("\nTails: observed latency / predicted mean, per action type (descriptive)")
    for t in T:
        print(f"{t['tag']:8s} {t['path']:12s} n={t['n']:5d} mean {t['mean']:.3f} p50 {t['p50']:.3f} p90 {t['p90']:.3f} p95 {t['p95']:.3f} p99 {t['p99']:.3f}")
    print("\nStaleness: observed stale share [95% run-bootstrap interval] vs predicted")
    for s in S:
        print(f"{s['tag']:7s} {s['cell']:26s} runs={s['runs']} views={s['views']:5d} obs {s['obs']:.3f} [{s['ci'][0]:.3f},{s['ci'][1]:.3f}] pred {s['pred']:.3f} {'in' if s['pred_in_ci'] else 'OUT'}")
    print(f"\npredicted stale share inside the run-bootstrap interval: {sum(s['pred_in_ci'] for s in S)}/{len(S)} cells")
    json.dump({"latency": L, "tails": T, "staleness": S}, open(os.path.join(R, "revision", "A4-uncertainty.json"), "w"), indent=1)
