#!/usr/bin/env python3
"""Retrospective test of point 4 (workload knowledge): predictions that use only the access DISTRIBUTION
(Zipf alpha over the pages, or Conduit's popularity weights; users and session length), not the declared
sessions. For each run, K session sets are sampled from the distribution (seeds unrelated to the run's),
the frozen model predicts stale share, mean latency and mean P(db) for each, and the K predictions are
averaged. Scored per cell (equal-weight mean over runs) against the observed values, beside the frozen
predictions that used the declared sessions.
usage: python3 diag_distonly.py <tag> [R|RC]"""
import bisect, collections, json, random, sys
tag = sys.argv[1]; kind = sys.argv[2] if len(sys.argv) > 2 else "R"
if kind == "R":
    from modelR import layer_cfg, simulate, stale_fraction
    from writeproc import p0_factory
    M = json.load(open("results/modelR.frozen.json")); PF = "predictionsR.jsonl"
    p0f = lambda run: p0_factory(run["proc"], run["pages"])
else:
    from modelRC import layer_cfg, simulate, stale_fraction, page_p0
    M = json.load(open("results/modelRC.frozen.json")); PF = "predictionsRC.jsonl"
    probs = {int(k): v for k, v in M["page_probs"].items()}
    p0f = lambda run: page_p0(run["proc"], probs)
K = 8


def sessions(run, seed):
    rng = random.Random(seed)
    pages = run["pages"]
    w = [1 / (i + 1) ** run["alpha"] for i in range(pages)] if kind == "R" else [probs[i + 1] for i in range(pages)]
    out = []
    for _ in range(len(run["users"])):
        seq = []
        while len(seq) < len(run["users"][0]):
            p = rng.choices(range(1, pages + 1), weights=w)[0]
            if not seq or p != seq[-1]: seq.append(p)
        out.append(seq)
    return out


runs = {r["runId"]: r for r in map(json.loads, open(f"results/{tag}-runs.jsonl"))}
W = collections.defaultdict(lambda: collections.defaultdict(list))
for x in map(json.loads, open("results/writes.jsonl")):
    if x["runId"] in runs: W[x["runId"]][x["productId"]].append(x["committed"])
for d in W.values():
    for v in d.values(): v.sort()
pr = {p["runId"]: p for p in map(json.loads, open(f"results/{PF}")) if p["runId"] in runs}
obs = collections.defaultdict(lambda: [[], []])
for v in map(json.loads, open(f"results/{tag}.jsonl")):
    if v.get("runId") not in runs or "error" in v: continue
    r = runs[v["runId"]]
    obs[v["runId"]][0].append(any(s != r["stock0"][str(p)] + bisect.bisect_right(W[v["runId"]][p], v["wall"]) for p, s in v["rows"]))
    obs[v["runId"]][1].append(v["latencyMs"])
cells = collections.defaultdict(lambda: collections.defaultdict(list))
for i, (rid, run) in enumerate(sorted(runs.items())):
    crtt = run["tcpPre"]["client_web"]
    fit = lambda tab: (lambda mm, a, o: tab[f"{mm}|{a}|{o}"]["a"] + tab[f"{mm}|{a}|{o}"]["b"] * crtt)
    p0 = p0f(run); st = lt = 0.0
    for k in range(K):
        sess = sessions(run, 7_000_003 * (k + 1) + i)
        v = simulate(sess, fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0)
        st += stale_fraction(v, p0) / K; lt += 1000 * sum(x[1] for x in v) / len(v) / K
    c = cells[run["cellName"]]
    c["obs_s"].append(sum(obs[rid][0]) / len(obs[rid][0])); c["obs_l"].append(sum(obs[rid][1]) / len(obs[rid][1]))
    c["dec_s"].append(pr[rid]["stale"]); c["dec_l"].append(sum(x["ms"] for x in pr[rid]["views"]) / len(pr[rid]["views"]))
    c["dist_s"].append(st); c["dist_l"].append(lt)
m = lambda x: sum(x) / len(x)
res = {}
for src in ("dec", "dist"):
    es = [abs(m(c["obs_s"]) - m(c[f"{src}_s"])) for c in cells.values()]
    el = [abs(m(c["obs_l"]) - m(c[f"{src}_l"])) / m(c["obs_l"]) for c in cells.values()]
    res[src] = {"W1": m(es), "Wmax": max(es), "L1": 100 * m(el), "Lmax": 100 * max(el)}
    print(f"{tag} {'declared sessions' if src == 'dec' else 'distribution only'}: staleness MAE {m(es):.4f} (worst {max(es):.3f}); latency (run mean) {100 * m(el):.2f}% (worst {100 * max(el):.2f}%)")
json.dump({"cells": len(cells), **res}, open(f"results/revision/distonly-{tag}.json", "w"), indent=1)
