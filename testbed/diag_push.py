#!/usr/bin/env python3
"""Post-hoc diagnosis (not a test): do SSR framework-push transitions follow the model's rule?
For every SSR view under Next push + Redis push, find the last fill of its page's framework entry
(latest web-caller API response for that page before the view started) and whether a write to the
page was committed after that fill and before the view started. Model rule: write since fill -> miss
(DB read); no write -> framework hit. usage: python3 diag_push.py <tag> ..."""
import bisect, collections, json, sys
R = "results"
TAB = {}
for tag in sys.argv[1:]:
    runs = {r["runId"]: r for r in map(json.loads, open(f"{R}/{tag}-runs.jsonl")) if r["mode"] == "ssr" and r["fe"] == "push"}
    fills = collections.defaultdict(lambda: collections.defaultdict(list))   # run -> page key -> [ts]
    resp = {}
    for x in map(json.loads, open(f"{R}/api.jsonl")):
        if x.get("runId") in runs and x.get("caller") == "web":
            fills[x["runId"]][x["key"]].append(x["ts"]); resp[x["respId"]] = x
    W = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in map(json.loads, open(f"{R}/writes.jsonl")):
        if w["runId"] in runs: W[w["runId"]][w["page"]].append((w["committed"], w["purgedAt"]))
    tab = collections.Counter(); lagc = []
    for v in map(json.loads, open(f"{R}/{tag}.jsonl")):
        if v.get("runId") not in runs or "error" in v: continue
        start = v["wall"] - v["domMs"]; page = v["page"]
        key = [k for k in fills[v["runId"]] if k.endswith(f"p{page}:l25")]
        if not key: continue
        fs = sorted(t for t in fills[v["runId"]][key[0]] if t < start)
        if not fs: continue
        last = fs[-1]
        ws = [(c, p) for c, p in W[v["runId"]][page] if last < c < start]
        x = resp.get(v.get("resp"))
        served_cache = x is not None and x["ts"] < start
        tab[(bool(ws), "cache" if served_cache else "fetched")] += 1
        if ws and served_cache: lagc.append(min(start - (p or c) for c, p in ws))
    n = sum(tab.values())
    TAB[tag] = {f"{k[0]}|{k[1]}": v for k, v in tab.items()}
    print(f"{tag}: {n} SSR push views with a previous fill")
    for k in sorted(tab): print(f"   write since fill={k[0]!s:5s} served={k[1]:8s} {tab[k]:5d} ({tab[k] / n:.3f})")
    if lagc:
        lagc.sort(); print(f"   write-but-cached: ms from purge to view start, median {lagc[len(lagc)//2]}, min {lagc[0]}, max {lagc[-1]}")


def timing(tag):
    """Predicted P(db) (frozen model, its own timeline) vs the same formula with the OBSERVED time since the
    entry's last fill, vs the observed share of views that were fetched."""
    import math
    runs = {r["runId"]: r for r in map(json.loads, open(f"{R}/{tag}-runs.jsonl")) if r["mode"] == "ssr" and r["fe"] == "push"}
    pred = {p["runId"]: {(x["user"], x["step"]): x["dist"]["db"] for x in p["views"]} for p in map(json.loads, open(f"{R}/predictionsR.jsonl")) if p["runId"] in runs}
    fills = collections.defaultdict(lambda: collections.defaultdict(list)); resp = {}
    for x in map(json.loads, open(f"{R}/api.jsonl")):
        if x.get("runId") in runs and x.get("caller") == "web":
            fills[x["runId"]][x["key"]].append(x["ts"]); resp[x["respId"]] = x
    acc = [0, 0.0, 0.0, 0, 0.0]
    for v in map(json.loads, open(f"{R}/{tag}.jsonl")):
        if v.get("runId") not in runs or "error" in v: continue
        start = v["wall"] - v["domMs"]; run = runs[v["runId"]]
        key = [k for k in fills[v["runId"]] if k.endswith(f"p{v['page']}:l25")]
        fs = sorted(t for t in fills[v["runId"]][key[0]] if t < start) if key else []
        p = pred[v["runId"]].get((v["user"], v["step"]))
        if not fs or p is None or not (0 < p < 1): continue
        dt = (start - fs[-1]) / 1000
        x = resp.get(v.get("resp")); fetched = not (x is not None and x["ts"] < start)
        acc[0] += 1; acc[1] += p; acc[2] += 1 - math.exp(-run["lam"] / run["pages"] * dt); acc[3] += fetched; acc[4] += dt
    n = acc[0]
    print(f"{tag}: {n} views  predicted P(db) {acc[1]/n:.3f}   formula with observed time since fill {acc[2]/n:.3f}   observed fetched {acc[3]/n:.3f}   mean time since fill {acc[4]/n:.1f} s")
    return {"tag": tag, "views": n, "pred": acc[1] / n, "observed_fetched": acc[3] / n}


def last_access(tag):
    """Poisson no-write formula with the OBSERVED time since the page's last access (any render, from the web
    log), compared with the frozen prediction and with model R2's (exposure ending at request arrival)."""
    import math, types
    from writeproc import p0_factory
    runs = {r["runId"]: r for r in map(json.loads, open(f"{R}/{tag}-runs.jsonl")) if r["mode"] == "ssr" and r["fe"] == "push"}
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in map(json.loads, open(f"{R}/web.jsonl")):
        rid = (w.get("aid") or "").rsplit(".u", 1)[0]
        if rid in runs: acc[rid][int(w["key"][1:].split("-")[0])].append(w["ts"])
    resp = {x["respId"]: x for x in map(json.loads, open(f"{R}/api.jsonl")) if x.get("runId") in runs and x.get("caller") == "web"}
    W = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in map(json.loads, open(f"{R}/writes.jsonl")):
        if w["runId"] in runs: W[w["runId"]][w["page"]].append(w["committed"])
    import modelR2
    M = json.load(open(f"{R}/modelR.frozen.json"))
    p2 = {}
    for rid, run in runs.items():
        crtt = run["tcpPre"]["client_web"]
        fit = lambda tab: (lambda mm, a, o: tab[f"{mm}|{a}|{o}"]["a"] + tab[f"{mm}|{a}|{o}"]["b"] * crtt)
        v = modelR2.simulate(run["users"], fit(M["gap"]), fit(M["lat"]), modelR2.layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0_factory(run["proc"], run["pages"]))
        steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
        p2[rid] = {k: d["db"] for k, (_, _, d) in zip(steps, v)}
    pred = {p["runId"]: {(x["user"], x["step"]): x["dist"]["db"] for x in p["views"]} for p in map(json.loads, open(f"{R}/predictionsR.jsonl")) if p["runId"] in runs}
    n = sp = s2 = so = sw = sf = 0
    for v in map(json.loads, open(f"{R}/{tag}.jsonl")):
        if v.get("runId") not in runs: continue
        r = runs[v["runId"]]; start = v["wall"] - v["domMs"]
        prev = [t for t in acc[v["runId"]][v["page"]] if t < start - 1]
        p = pred[v["runId"]].get((v["user"], v["step"]))
        if not prev or p is None or not (0 < p < 1): continue
        last = max(prev); x = resp.get(v.get("resp"))
        n += 1; sp += p; s2 += p2[v["runId"]][(v["user"], v["step"])]
        so += 1 - math.exp(-r["lam"] / 8 * (start - last) / 1000); sf += not (x is not None and x["ts"] < start)
    return {"views": n, "pred_R": sp / n, "pred_R2": s2 / n, "formula_observed_gap": so / n, "observed_fetched": sf / n}


out = {t: {"transitions": TAB.get(t), **timing(t), "last_access": last_access(t)} for t in sys.argv[1:]}
json.dump(out, open(f"{R}/revision/diag-push.json", "w"), indent=1)
