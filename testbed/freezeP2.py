#!/usr/bin/env python3
"""Freeze modelP2 from calibP2 (N = 1, server pinned cores, launch barrier).
TOTAL demand per (mode, action) and station: cgroup CPU minus the idle rate; client counted from
the barrier, servers over the whole run with each process's warm-up load counted as one extra
initial load; initial-only vs full sessions identify initial vs navigation demand.
ON-PATH demand from RTT-0 full sessions: DB = dbMs, API = totalMs - dbMs, Next.js = TTFB of the
document / RSC request - API time, client = latency - server on-path time.
R1 per (mode, action) and C1 (steady wall time per action) from RTT-100 full sessions."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, jl, load, mean

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
acts, runs, err, unc = load("calibP2.jsonl", "calibP2-runs.jsonl")
assert not err and not unc, (len(err), len(unc))
late = [r["runId"] for r in runs.values() if r["cpu"]["barrierLateMs"] > 0]
assert not late, f"barrier missed: {late}"
api = jl("api.jsonl")
by_rid = {x["reqId"]: x for x in api if x.get("reqId")}
by_resp = {x["respId"]: x for x in api if x.get("respId")}
web_by_aid = {}
for w in jl("web.jsonl"):
    if w.get("aid"): web_by_aid.setdefault(w["aid"], w)
GROUP = {"client": ["client"], "app": ["web", "api", "redis"], "db": ["db"]}

def busy(run):
    out = {}
    for st, cs in GROUP.items():
        dur = (run["steadyMs"] if st == "client" else run["wallMs"]) / 1000
        out[st] = 1000 * sum(run["cpu"][c] - run["idleCpu"][c] * dur for c in cs)
    return out

D, C1, R1 = {}, {}, defaultdict(list)
for a in acts:
    if runs[a["runId"]]["rtt"] == 100: R1[f"{a['mode']}|{a['action']}"].append(a["latencyMs"])
for mode in ("csr", "ssr"):
    full = [r for r in runs.values() if r["mode"] == mode and r["rtt"] == 100 and not r.get("initOnly")]
    init = [r for r in runs.values() if r["mode"] == mode and r["rtt"] == 100 and r.get("initOnly")]
    n_init = lambda r, st: len(r["users"]) + (0 if st == "client" else 1)       # + warm-up load on servers
    d_i = {st: mean(busy(r)[st] / n_init(r, st) for r in init) for st in GROUP}
    n_nav = lambda r: sum(len(s) - 1 for s in r["users"])
    d_n = {st: mean((busy(r)[st] - n_init(r, st) * d_i[st]) / n_nav(r) for r in full) for st in GROUP}
    D[f"{mode}|initial"], D[f"{mode}|nav"] = d_i, d_n
    C1[mode] = mean(r["steadyMs"] / sum(map(len, r["users"])) for r in full)

def api_rec(a):
    if a["mode"] == "csr": return by_rid.get(a["tqRids"][-1]) if a["tqRids"] else None
    w = web_by_aid.get(a["aid"]); return by_resp.get(w["respId"]) if w and w["nextCache"] != "hit" else None

path = defaultdict(lambda: defaultdict(list))
for a in acts:
    if runs[a["runId"]]["rtt"] != 0: continue
    k = f"{a['mode']}|{a['action']}"
    x = api_rec(a); api_ms = x["totalMs"] if x else 0.0; db_ms = (x or {}).get("dbMs") or 0.0
    ttfb = lambda r: r["responseStart"] - r["requestStart"]
    res = a.get("res") or []
    if a["mode"] == "ssr":
        doc = [r for r in res if (r["type"] == "navigation" if a["action"] == "initial" else (r["type"] == "fetch" and "_rsc=" in r["name"]))]
        web = max(0.0, ttfb(doc[0]) - api_ms) if doc else 0.0
    else:
        doc = [r for r in res if r["type"] == "navigation"] if a["action"] == "initial" else []
        web = ttfb(doc[0]) if doc else 0.0
    srv = web + api_ms
    path[k]["db"].append(db_ms); path[k]["app"].append(web + api_ms - db_ms)
    path[k]["client"].append(max(0.0, a["latencyMs"] - srv))
P = {k: {st: mean(v[st]) for st in GROUP} for k, v in path.items()}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "R1": {k: mean(v) for k, v in R1.items()}, "D": D, "P": P, "C1": C1,
     "modelP2_sha256": sha("modelP2.py"), "model5_sha256": sha("model5.py")}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "modelP2.frozen.json"), "w").write(blob)
print("frozen modelP2; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
for k in sorted(F["R1"]):
    print(f"  {k:12} R1={F['R1'][k]:7.1f}  total D: " + " ".join(f"{st}={D[k][st]:6.1f}" for st in GROUP)
          + "   on-path P: " + " ".join(f"{st}={P[k][st]:6.1f}" for st in GROUP))
print("  C1 (ms/action):", {k: round(v, 1) for k, v in C1.items()})
