#!/usr/bin/env python3
"""Score a revision block (TWEB revision, protocol/PROTOCOL.md) against its frozen predictions.

Cells: mode-fe-rp-tau-alpha (+ write process). Oracle as experiment X: a view is stale iff a
displayed row's stock differs from stock0 + writes committed at or before the display instant.
Logged outcome per view: CSR without a TanStack request -> tq_hit, else the API log of that
request (Redis hit / DB); SSR: the API log of the DISPLAYED response (data-resp-id): produced
before the view started -> next_hit (framework cache), else Redis hit / DB on the view's path.

Criteria (frozen in protocol/PROTOCOL.md):
  W1 pooled MAE <= 0.03; W2 every cell within 0.05; W3 orderings of cells whose predictions differ
  by >= 0.05; W4 oracle integrity; W5 predictions before runs, by the frozen model
  L1 mean relative latency error over (cell, action) <= 3%; L2 every (cell, action) within max(5%, 10 ms)
  O1 calibration: in every predicted-P(db) decile bin with >= 100 views (0 < p < 1), |mean predicted - observed| <= 0.05
  O2 skill: multiclass Brier score below the calibration-frequency reference (skill > 0)
  O3 sharpness of fit: Brier - mean_views sum_o p_o (1 - p_o) <= 0.03
  B4 (selection blocks): see selection(); regret <= 5% mean over feasible decisions; no selected
     policy whose observed stale share exceeds eps with its run-bootstrap lower bound above eps
usage: python3 evaluateR.py <tag> [--pilot <pilot tag>]
"""
import bisect, collections, json, os, random, sys

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CLS = ("tq_hit", "next_hit", "redis_hit", "db")
EPS = (0.05, 0.10, 0.25, 0.50)
tag = sys.argv[1]
pilot_tag = sys.argv[sys.argv.index("--pilot") + 1] if "--pilot" in sys.argv else None
M = json.load(open(os.path.join(R, "modelR.frozen.json")))


def jl(name):
    p = os.path.join(R, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def cell(run):
    c = f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}"
    if run["fe"] == "ttl" or run["rp"] == "ttl": c += f"-tau{run['tau']}"
    c += f"-a{run['alpha']}"
    if run["proc"].get("kind", "poisson") != "poisson": c += f"-{run['proc']['kind']}"
    return c


def policy(c): return c.split("-a")[0]


def load_block(t, preds_needed=True):
    runs = {r["runId"]: r for r in jl(f"{t}-runs.jsonl")}
    api_rid, api_resp = {}, {}
    for x in jl("api.jsonl"):
        if x.get("runId") in runs:
            if x.get("reqId"): api_rid[x["reqId"]] = x
            if x.get("respId"): api_resp[x["respId"]] = x
    W = collections.defaultdict(lambda: collections.defaultdict(list)); lags = []
    for w in jl("writes.jsonl"):
        if w["runId"] in runs:
            W[w["runId"]][w["productId"]].append(w["committed"])
            if w["purgedAt"] is not None: lags.append(w["purgedAt"] - w["committed"])
    for d in W.values():
        for v in d.values(): v.sort()
    views = collections.defaultdict(list); errors = ahead = unl = 0
    for v in jl(f"{t}.jsonl"):
        if v.get("runId") not in runs: continue
        if "error" in v: errors += 1; continue
        run = runs[v["runId"]]; st = False
        for pid, shown in v["rows"]:
            truth = run["stock0"][str(pid)] + bisect.bisect_right(W[v["runId"]][pid], v["wall"])
            ahead += shown > truth; st |= shown != truth
        if v["mode"] == "csr":
            y = "tq_hit" if not v["tqRids"] else None
            x = None if y else api_rid.get(v["tqRids"][-1])
        else:
            y = None; x = api_resp.get(v.get("resp"))
            if x is not None and x["ts"] < v["wall"] - v["domMs"]: y = "next_hit"
        if y is None and x is not None: y = "redis_hit" if x["redis"] == "hit" else "db"
        if y is None: unl += 1
        views[v["runId"]].append({"u": v["user"], "s": v["step"], "action": v["action"], "revisit": v["revisit"],
                                  "lat": v["latencyMs"], "stale": st, "y": y})
    preds = {p["runId"]: p for p in jl("predictionsR.jsonl") if p["runId"] in runs}
    return runs, views, preds, W, lags, errors, ahead, unl


runs, views, preds, W, lags, errors, ahead, unl = load_block(tag)
print(f"{tag}: {len(runs)} runs, {sum(map(len, views.values()))} views, {errors} errors, {unl} views with unclassified outcome")

# ---- staleness (W) and latency (L) per cell ----
agg = collections.defaultdict(lambda: [0, 0, 0.0])
latc = collections.defaultdict(lambda: [[], []])
for rid, vs in views.items():
    c = cell(runs[rid]); p = preds.get(rid)
    pl = {(x["user"], x["step"]): x for x in p["views"]} if p else {}
    a = agg[c]; a[0] += len(vs); a[1] += sum(v["stale"] for v in vs); a[2] += (p["stale"] if p else float("nan")) * len(vs)
    for v in vs:
        if (v["u"], v["s"]) in pl:
            latc[(c, v["action"])][0].append(v["lat"]); latc[(c, v["action"])][1].append(pl[(v["u"], v["s"])]["ms"])
res = {c: (s / n, pv / n) for c, (n, s, pv) in agg.items()}
for c in sorted(res): print(f"  {c:40s} stale obs {res[c][0]:.3f} pred {res[c][1]:.3f}")
errs = [abs(o - p) for o, p in res.values()]
pairs = [(a, b) for a in res for b in res if a < b and abs(res[a][1] - res[b][1]) >= 0.05]
bad = [(a, b) for a, b in pairs if (res[a][0] - res[b][0]) * (res[a][1] - res[b][1]) <= 0]
lags.sort(); p99 = lags[int(0.99 * (len(lags) - 1))] if lags else None
missing_w = [rid for rid in runs if not any(W[rid].values())]
late = [rid for rid in runs if rid not in preds or preds[rid]["ts"] >= runs[rid]["t0"] or preds[rid]["sha"] != M["sha"]]
lerr = {k: (sum(o) / len(o), sum(p) / len(p)) for k, (o, p) in latc.items()}
rel = {k: abs(p - o) / o for k, (o, p) in lerr.items()}
l2bad = [k for k, (o, p) in lerr.items() if abs(p - o) > max(0.05 * o, 10.0)]

# ---- outcomes (O) ----
REF = M["outcome_reference"]   # calibration-frequency probabilities from calibW (freezeR.py)
B = Bref = expB = n = top = 0; bins = collections.defaultdict(lambda: [0, 0, 0.0])
for rid, vs in views.items():
    p = preds.get(rid)
    if not p: continue
    run = runs[rid]; pl = {(x["user"], x["step"]): x["dist"] for x in p["views"]}
    key = lambda v: f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}|{v['action']}|{v['revisit']}"
    for v in vs:
        d = pl.get((v["u"], v["s"])); y = v["y"]
        if d is None or y is None: continue
        # No calibW reference exists for the cache-less CSR policy; with no cache every view is a
        # DB read, which the reference then knows exactly (it gives the predictor no advantage).
        rf = REF.get(key(v)) or ({"db": 1.0} if not run["fe"] and not run["rp"] else {c: 0.25 for c in CLS})
        B += sum((d[c] - (c == y)) ** 2 for c in CLS); Bref += sum((rf.get(c, 0.0) - (c == y)) ** 2 for c in CLS)
        expB += sum(d[c] * (1 - d[c]) for c in CLS); n += 1; top += max(CLS, key=lambda c: d[c]) == y
        if 0 < d["db"] < 1:
            b = bins[min(9, int(d["db"] * 10))]; b[0] += 1; b[1] += y == "db"; b[2] += d["db"]
calib = {k: (b[0], b[2] / b[0], b[1] / b[0]) for k, b in sorted(bins.items())}
o1bad = [k for k, (m, pm, ob) in calib.items() if m >= 100 and abs(pm - ob) > 0.05]

crit = {
    "W1 pooled MAE <= 0.03": (sum(errs) / len(errs) <= 0.03, f"{sum(errs) / len(errs):.4f}"),
    "W2 every cell within 0.05": (max(errs) <= 0.05, f"max {max(errs):.4f}"),
    "W3 orderings": (not bad, f"{len(pairs) - len(bad)}/{len(pairs)}" + (f" wrong: {bad[:5]}" if bad else "")),
    "W4 oracle integrity": (ahead == 0 and not missing_w and errors == 0 and (p99 is None or p99 <= 20),
                            f"ahead {ahead}, runs without writes {len(missing_w)}, errors {errors}, purge lag p99 {p99} ms"),
    "W5 predictions before runs": (not late, f"{len(runs) - len(late)}/{len(runs)}"),
    "L1 mean latency error <= 3%": (sum(rel.values()) / len(rel) <= 0.03, f"{100 * sum(rel.values()) / len(rel):.2f}% over {len(rel)} (cell, action)"),
    "L2 every (cell, action) within max(5%, 10 ms)": (not l2bad, f"max {100 * max(rel.values()):.2f}%" + (f"; failing {sorted(l2bad)[:6]}" if l2bad else "")),
    "O1 outcome calibration (deciles, n >= 100) within 0.05": (not o1bad, "; ".join(f"{k}: n={m} pred {pm:.3f} obs {ob:.3f}" for k, (m, pm, ob) in calib.items())),
    "O2 Brier skill > 0": (B < Bref, f"Brier {B / n:.4f} ref {Bref / n:.4f} skill {1 - B / Bref:+.3f}; top-1 {top / n:.3f} over {n} views"),
    "O3 Brier - expected Brier <= 0.03": ((B - expB) / n <= 0.03, f"{(B - expB) / n:+.4f}"),
}
out = {"tag": tag, "stale": res, "latency": {f"{c}|{a}": v for (c, a), v in lerr.items()}, "outcome_calibration": calib}


# ---- selection (B4) ----
def selection(runs, views, preds, pilot):
    rng = random.Random(7)
    per = collections.defaultdict(list)
    for rid, vs in views.items():
        r = runs[rid]
        per[cell(r)].append((sum(v["lat"] for v in vs) / len(vs), sum(v["stale"] for v in vs) / len(vs),
                             sum(x["ms"] for x in preds[rid]["views"]) / len(preds[rid]["views"]), preds[rid]["stale"]))
    rep = {}
    for alpha in sorted({c.split("-a")[1] for c in per}):
        cs = [c for c in per if c.split("-a")[1] == alpha]
        obs = {c: (sum(x[0] for x in per[c]) / len(per[c]), sum(x[1] for x in per[c]) / len(per[c])) for c in cs}
        prd = {c: (sum(x[2] for x in per[c]) / len(per[c]), sum(x[3] for x in per[c]) / len(per[c])) for c in cs}
        lo = {}
        for c in cs:
            bs = sorted(sum(rng.choice(per[c])[1] for _ in per[c]) / len(per[c]) for _ in range(4000))
            lo[c] = bs[int(0.025 * len(bs))]
        tune = {}
        if pilot:
            for c in cs:
                pc = [x for x in pilot.get(c, [])]
                if pc: tune[c] = (sum(x[0] for x in pc) / len(pc), sum(x[1] for x in pc) / len(pc))
        for eps in EPS:
            feas = [c for c in cs if obs[c][1] <= eps]
            best = min(feas, key=lambda c: obs[c][0]) if feas else None
            pick = lambda vals: min([c for c in vals if vals[c][1] <= eps], key=lambda c: vals[c][0], default=None)
            picks = {"selector": pick(prd), "tuning": pick(tune) if tune else None,
                     "fixed": f"ssr-fepush-rdpush-a{alpha}", "default": f"ssr-fettl-rdttl-tau60-a{alpha}", "nocache": f"ssr-feoff-rdoff-a{alpha}"}
            row = {"oracle": best}
            for m, c in picks.items():
                if c is None or c not in obs: row[m] = {"pick": c, "abstain": True}; continue
                l, s = obs[c]
                row[m] = {"pick": c, "violation": s > eps, "confirmed_violation": lo[c] > eps, "excess": max(0.0, s - eps),
                          "regret": None if s > eps or best is None else (l - obs[best][0]) / obs[best][0]}
            rep[f"a{alpha}|{eps}"] = row
    return rep


if any(r["proc"].get("kind", "poisson") == "poisson" for r in runs.values()) and len({cell(r) for r in runs.values()}) >= 27:
    pilot = None
    if pilot_tag:
        pr, pv, _, _, _, _, _, _ = load_block(pilot_tag, preds_needed=False)
        pilot = collections.defaultdict(list)
        for rid, vs in pv.items():
            pilot[cell(pr[rid])].append((sum(v["lat"] for v in vs) / len(vs), sum(v["stale"] for v in vs) / len(vs)))
    sel = selection(runs, views, preds, pilot)
    regs = [r["selector"]["regret"] for r in sel.values() if not r["selector"].get("abstain") and r["selector"]["regret"] is not None]
    viol = [k for k, r in sel.items() if not r["selector"].get("abstain") and r["selector"]["confirmed_violation"]]
    crit["B4a mean selector regret <= 5%"] = (bool(regs) and sum(regs) / len(regs) <= 0.05,
                                              f"mean {100 * sum(regs) / len(regs):.2f}% over {len(regs)} feasible decisions, worst {100 * max(regs):.2f}%" if regs else "no feasible decisions")
    crit["B4b no confirmed constraint violation"] = (not viol, f"{len(viol)} confirmed" + (f": {viol}" if viol else ""))
    for k, row in sel.items():
        print(f"  {k}: oracle {row['oracle']}")
        for m in ("selector", "tuning", "fixed", "default", "nocache"):
            r = row[m]
            if r.get("abstain"): print(f"     {m:9s} abstains ({r['pick']})"); continue
            s = (f"VIOLATES +{r['excess']:.3f}" + (" (confirmed)" if r["confirmed_violation"] else "")) if r["violation"] else f"regret {100 * r['regret']:+.1f}%"
            print(f"     {m:9s} {r['pick']:34s} {s}")
    out["selection"] = sel
for k, (ok, d) in crit.items(): print(f"{'PASS' if ok else 'FAIL'}  {k}: {d}")
print("ACCEPTED" if all(ok for ok, _ in crit.values()) else "NOT ACCEPTED")
out["criteria"] = {k: [ok, d] for k, (ok, d) in crit.items()}
os.makedirs(os.path.join(R, "revision"), exist_ok=True)
json.dump(out, open(os.path.join(R, "revision", f"{tag}-evaluation.json"), "w"), indent=1)
