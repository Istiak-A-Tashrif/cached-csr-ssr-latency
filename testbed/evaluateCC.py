#!/usr/bin/env python3
"""Score a protocol-v4 block (chance-constrained selection, protocol/PROTOCOL_CC.md). evaluateR2.py unchanged except
the selection section: three selectors (point, v3 margin 0.05, chance-constrained from selector_cc.py with the
manifest's frozen a, sd_m and per-candidate sd_s); the gates B4cc-a/b apply to the chance-constrained one.
evaluateR2.py's description:

Score a protocol-v3 block (near-threshold selection, protocol/PROTOCOL_HARD.md): evaluateR.py with model R2,
staleness predictions from the access distribution only, a noise-aware O1 variant, and the two selectors.
Original description:

Score a revision block (TWEB revision, protocol/PROTOCOL.md) against its frozen predictions.

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
M = json.load(open(os.path.join(R, "modelR2.frozen.json")))
MAN = json.load(open(os.path.join(os.path.dirname(R), "protocol", f"{tag}.json")))


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
    preds = {p["runId"]: p for p in jl("predictionsR2.jsonl") if p["runId"] in runs}
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


# ---- O1' (noise-aware, pre-registered in v3): per decile |dev| <= max(0.05, run-bootstrap 95% half-width) ----
rng = random.Random(11); perrun = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0]))
for rid, vs in views.items():
    pl = {(x["user"], x["step"]): x["dist"] for x in preds[rid]["views"]}
    for v in vs:
        d = pl.get((v["u"], v["s"]))
        if d and v["y"] and 0 < d["db"] < 1:
            b = perrun[rid][min(9, int(d["db"] * 10))]; b[0] += 1; b[1] += d["db"]; b[2] += v["y"] == "db"
o1p = []
rids = sorted(perrun)
for k in range(10):
    tot = [sum(perrun[r][k][i] for r in rids) for i in range(3)]
    if tot[0] < 100: continue
    dev = (tot[2] - tot[1]) / tot[0]; bs = []
    for _ in range(2000):
        smp = [rng.choice(rids) for _ in rids]; n_ = sum(perrun[r][k][0] for r in smp)
        if n_: bs.append((sum(perrun[r][k][2] for r in smp) - sum(perrun[r][k][1] for r in smp)) / n_)
    bs.sort(); half = (bs[1949] - bs[50]) / 2
    o1p.append((k, dev, max(0.05, half)))
crit["O1' noise-aware calibration"] = (all(abs(dv) <= tol for _, dv, tol in o1p), "; ".join(f"{k}: {dv:+.3f} (tol {tol:.3f})" for k, dv, tol in o1p))

# ---- selection near the threshold (B4h) ----
per = collections.defaultdict(list)
for rid, vs in views.items():
    r = runs[rid]; p = preds[rid]
    per[cell(r)].append((sum(v["lat"] for v in vs) / len(vs), sum(v["stale"] for v in vs) / len(vs), p["lat"], p["stale"]))
mean = lambda x: sum(x) / len(x)
obs = {c: (mean([x[0] for x in xs]), mean([x[1] for x in xs])) for c, xs in per.items()}
prd = {c: (mean([x[2] for x in xs]), mean([x[3] for x in xs])) for c, xs in per.items()}
lo = {}
for c, xs in per.items():
    bs = sorted(mean([rng.choice(xs)[1] for _ in xs]) for _ in range(4000)); lo[c] = bs[int(0.025 * len(bs))]
import math
CC = MAN["cc"]; ccmargin = {c: CC["z"] * math.sqrt(CC["sd_s"][c] ** 2 + CC["sd_m"] ** 2) for c in obs}
selrep, picks_by = {}, {"point": [], "margin": [], "cc": []}
for setname, eps_list in MAN["eps"].items():
    cs = [c for c in obs if setname == "all" or "push" not in c]
    for eps in eps_list:
        feas = [c for c in cs if obs[c][1] <= eps]
        best = min(feas, key=lambda c: obs[c][0]) if feas else None
        row = {"oracle": best}
        for name, margin in (("point", lambda c: 0.0), ("margin", lambda c: MAN["margin"]), ("cc", lambda c: ccmargin[c])):
            ok = [c for c in cs if prd[c][1] + margin(c) <= eps]
            pick = min(ok, key=lambda c: prd[c][0]) if ok else None
            if pick is None: row[name] = {"abstain": True}; picks_by[name].append(row[name]); continue
            l, st = obs[pick]
            row[name] = {"pick": pick, "violation": st > eps, "confirmed": lo[pick] > eps, "excess": max(0.0, st - eps),
                         "regret": None if best is None or st > eps else (l - obs[best][0]) / obs[best][0], "right": pick == best}
            picks_by[name].append(row[name])
        selrep[f"{setname}|{eps}"] = row
        print(f"  {setname} eps {eps}: oracle {best}")
        for name in ("point", "margin", "cc"):
            r = row[name]
            print(f"     {name:6s} " + ("abstains" if r.get("abstain") else f"{r['pick']:34s} " + (f"VIOLATES +{r['excess']:.3f}" + (" (confirmed)" if r["confirmed"] else "") if r["violation"] else f"regret {100 * r['regret']:+.1f}%")))
def summ(rs):
    sel = [r for r in rs if not r.get("abstain")]; fe = [r["regret"] for r in sel if r["regret"] is not None]
    return (len(rs), len(rs) - len(sel), sum(r["violation"] for r in sel), sum(r["confirmed"] for r in sel), sum(r["right"] for r in sel),
            100 * mean(fe) if fe else float("nan"), 100 * max(fe) if fe else float("nan"))
for name, rs in picks_by.items():
    n, ab, v, cv, right, mr, wr = summ(rs)
    print(f"  {name}: {n} decisions, {ab} abstentions, {v} violations ({cv} confirmed), {right} oracle choices, mean regret {mr:.2f}%, worst {wr:.2f}%")
n, ab, v, cv, right, mr, wr = summ(picks_by["cc"])
crit["B4cc-a chance-constrained selector mean regret <= 5%"] = (mr <= 5.0, f"mean {mr:.2f}% over {n - ab - v} feasible decisions, worst {wr:.2f}%")
crit["B4cc-b chance-constrained selector: no confirmed violation"] = (cv == 0, f"{v} violations, {cv} confirmed, {ab} abstentions")
out["selection"] = selrep
out["selectors"] = {k: dict(zip(("decisions", "abstentions", "violations", "confirmed", "oracle_choices", "mean_regret", "worst_regret"), summ(v))) for k, v in picks_by.items()}
out["cc_margin"] = ccmargin
for k, (ok, d) in crit.items(): print(f"{'PASS' if ok else 'FAIL'}  {k}: {d}")
print("ACCEPTED" if all(ok for ok, _ in crit.values()) else "NOT ACCEPTED")
out["criteria"] = {k: [ok, d] for k, (ok, d) in crit.items()}
os.makedirs(os.path.join(R, "revision"), exist_ok=True)
json.dump(out, open(os.path.join(R, "revision", f"{tag}-evaluation.json"), "w"), indent=1)
