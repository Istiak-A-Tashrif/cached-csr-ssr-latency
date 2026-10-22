#!/usr/bin/env python3
"""B1 offline (TWEB revision), retrospective: how well does the frozen timeline model (modelX,
frozen from calibW without writes) predict WHICH LAYER serves each view when caches expire (TTL)
and are purged by writes (push)? Scored on the accepted staleness tests (testW2, repW2: d = 0;
testX, repX: d = 25 / 100 ms), whose outcomes were never used to fit modelX.

Predicted per view: a distribution over {tq_hit, next_hit, redis_hit, db} from modelX.simulate:
  TanStack revisit -> tq_hit; Next TTL entry -> next_hit (SWR, refresh off-path);
  Next push entry -> next_hit with 1 - P_db, db with P_db; API read -> db with P_db, redis_hit
  with 1 - P_db (Redis enabled) else db.
Logged per view: CSR without a TanStack request -> tq_hit; otherwise the API log of the request
(Redis hit / DB); SSR: the web log's data-cache result, then the API log of the miss, where a
response the API produced before the view started counts as a data-cache hit (stale-while-
revalidate serves a background-refreshed entry that the web log's replay test calls a miss).
Metrics: multiclass Brier score (mean over views of sum_o (p_o - 1[y = o])^2), its skill against
calibration-frequency probabilities (per policy cell, action and step class, from calibW), the
share of views whose most likely predicted class is the logged one, and the confusion of
DB reads (the class that carries the server-work cost).
usage: python3 b1_offline.py
"""
import collections, json, os
from modelX import layer_cfg, simulate

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CLS = ("tq_hit", "next_hit", "redis_hit", "db")
M = json.load(open(os.path.join(R, "modelX.frozen.json")))

api_rid, api_resp, web_aid = {}, {}, {}
for l in open(os.path.join(R, "api.jsonl")):
    x = json.loads(l)
    if x.get("reqId"): api_rid[x["reqId"]] = x
    if x.get("respId"): api_resp[x["respId"]] = x
for l in open(os.path.join(R, "web.jsonl")):
    w = json.loads(l)
    if w.get("aid"): web_aid.setdefault(w["aid"], w)


def logged(v):
    if v["mode"] == "csr":
        if not v["tqRids"]: return "tq_hit"
        x = api_rid.get(v["tqRids"][-1])
    else:
        w = web_aid.get(v["aid"])
        if w is None: return None
        if w["nextCache"] in ("hit", "stale"): return "next_hit"
        x = api_resp.get(w["respId"])
        # A response first rendered here may still come from the data cache: stale-while-revalidate
        # refreshes the entry in the background, and the next render serves that new (never-rendered)
        # response. It was on the view's path only if the API produced it after the view started.
        if x is not None and x["ts"] < v["wall"] - v["domMs"]: return "next_hit"
    if x is None: return None
    return "redis_hit" if x["redis"] == "hit" else "db"


def predicted(run):
    users = run["users"] if isinstance(run["users"], list) else json.loads(run["users"])
    crtt = run["tcpPre"]["client_web"]
    fit = lambda tab: (lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt)
    cfg = layer_cfg(run)
    views = simulate(users, fit(M["gap"]), fit(M["lat"]), cfg, crtt / 1000, run.get("dbDelayMs", 0) / 1000, run["lam"] / run["pages"])
    from staleness import outcomes
    out = []
    for (action, o), (_, _, p_db) in zip(outcomes(users, cfg), views):
        p = dict.fromkeys(CLS, 0.0)
        if o == "tq_hit": p["tq_hit"] = 1.0
        elif o == "next_hit":
            pd = p_db or 0.0
            p["next_hit"] = 1 - pd; p["db"] += pd
        else:
            pd = 1.0 if p_db is None else p_db
            if cfg["redis"]: p["db"] = pd; p["redis_hit"] = 1 - pd
            else: p["db"] = 1.0
        out.append((action, p))
    return out


def brier(p, y): return sum((p[c] - (1.0 if c == y else 0.0)) ** 2 for c in CLS)


def cell(run): return f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}"


# Calibration-frequency reference (calibW, no writes): class frequencies per (cell, step class).
freq = collections.defaultdict(collections.Counter)
cruns = {r["runId"]: r for r in map(json.loads, open(os.path.join(R, "calibW-runs.jsonl")))}
for v in map(json.loads, open(os.path.join(R, "calibW.jsonl"))):
    if v.get("runId") not in cruns or "error" in v: continue
    y = logged(v)
    if y: freq[(cell(cruns[v["runId"]]), v["action"], v["revisit"])][y] += 1


def ref(run, v):
    c = freq.get((cell(run), v["action"], v["revisit"]))
    if not c: return {k: 0.25 for k in CLS}
    n = sum(c.values()); return {k: c[k] / n for k in CLS}


summary = {}
for tag in ("testW2", "repW2", "testX", "repX"):
    runs = {r["runId"]: r for r in map(json.loads, open(os.path.join(R, f"{tag}-runs.jsonl")))}
    byrun = collections.defaultdict(list)
    for v in map(json.loads, open(os.path.join(R, f"{tag}.jsonl"))):
        if v.get("runId") in runs and "error" not in v: byrun[v["runId"]].append(v)
    B = Bref = n = top = unl = 0
    conf = collections.Counter(); percell = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for rid, vs in byrun.items():
        run = runs[rid]
        P = predicted(run)
        pos = {(v["user"], v["step"]): v for v in vs}
        k = 0
        users = run["users"] if isinstance(run["users"], list) else json.loads(run["users"])
        for u, seq in enumerate(users):
            for s in range(len(seq)):
                action, p = P[k]; k += 1
                v = pos.get((u, s))
                if v is None: continue
                y = logged(v)
                if y is None: unl += 1; continue
                b, br = brier(p, y), brier(ref(run, v), y)
                B += b; Bref += br; n += 1
                top += max(CLS, key=lambda c: p[c]) == y
                conf[(max(CLS, key=lambda c: p[c]), y)] += 1
                pc = percell[cell(run)]; pc[0] += 1; pc[1] += b; pc[2] += br
    summary[tag] = {"views": n, "unclassified": unl, "brier": B / n, "brier_ref": Bref / n, "skill": 1 - B / Bref, "top1": top / n,
                    "db_recall": conf[("db", "db")] / max(1, sum(v for (p, y), v in conf.items() if y == "db")),
                    "db_precision": conf[("db", "db")] / max(1, sum(v for (p, y), v in conf.items() if p == "db")),
                    "per_cell": {c: {"views": a, "brier": b / a, "brier_ref": r / a} for c, (a, b, r) in sorted(percell.items())},
                    "confusion": {f"{p}->{y}": v for (p, y), v in sorted(conf.items())}}
    s = summary[tag]
    print(f"{tag:7s} views={s['views']} unclassified={s['unclassified']} Brier {s['brier']:.4f} (ref {s['brier_ref']:.4f}, skill {s['skill']:+.2f}) "
          f"top-1 {s['top1']:.3f} DB recall {s['db_recall']:.3f} precision {s['db_precision']:.3f}")
    for c, d in s["per_cell"].items():
        print(f"    {c:24s} views={d['views']:5d} Brier {d['brier']:.4f} ref {d['brier_ref']:.4f}")
    print("    confusion (predicted->logged):", s["confusion"])
os.makedirs(os.path.join(R, "revision"), exist_ok=True)
json.dump(summary, open(os.path.join(R, "revision", "B1-offline.json"), "w"), indent=1)
