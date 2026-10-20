#!/usr/bin/env python3
"""Freeze the concurrency model from the N = 1 calibration (calibC): single-user latency
R1 and service demands D_web, D_api, D_db per (mode, action, outcome)."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, jl, load, mean

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
acts, runs, err, unc = load("calibC.jsonl", "calibC-runs.jsonl")
assert not err and not unc, (len(err), len(unc))
api = jl("api.jsonl")
by_rid = {x["reqId"]: x for x in api if x.get("reqId")}
by_resp = {x["respId"]: x for x in api if x.get("respId")}
web_by_aid = {}
for w in jl("web.jsonl"):
    if w.get("aid"): web_by_aid.setdefault(w["aid"], w)
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in jl("calibH-runs.jsonl")]) for l in ("client_web", "client_api")}

def api_rec(a):
    if a["mode"] == "csr": return by_rid.get(a["tqRids"][-1]) if a["tqRids"] else None
    w = web_by_aid.get(a["aid"]); return by_resp.get(w["respId"]) if w and w["nextCache"] != "hit" else None

R1, Dw, Da, Dd = (defaultdict(list) for _ in range(4))
for a in acts:
    run = runs[a["runId"]]; p = run["tcpPre"]
    crtt = (p["client_web"] - tcp0["client_web"] + p["client_api"] - tcp0["client_api"]) / 2
    k = f"{a['mode']}|{a['action']}|{a['o']}"
    R1[k].append(a["latencyMs"])
    x = api_rec(a)
    api_ms = x["totalMs"] if x else 0.0
    Da[k].append(max(0.0, api_ms - ((x or {}).get("dbMs") or 0.0)))
    Dd[k].append((x or {}).get("dbMs") or 0.0)
    res = a.get("res") or []
    ttfb = lambda r: r["responseStart"] - r["requestStart"]
    if a["mode"] == "ssr":
        doc = [r for r in res if (r["type"] == "navigation" if a["action"] == "initial" else (r["type"] == "fetch" and "_rsc=" in r["name"]))]
        web = (ttfb(doc[0]) - crtt - api_ms) if doc else 0.0
    else:
        doc = [r for r in res if r["type"] == "navigation"] if a["action"] == "initial" else []
        web = (ttfb(doc[0]) - crtt) if doc else 0.0
    Dw[k].append(max(0.0, web))
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "R1": {k: mean(v) for k, v in R1.items()},
     "D": {k: {"web": mean(Dw[k]), "api": mean(Da[k]), "db": mean(Dd[k])} for k in R1},
     "n": {k: len(v) for k, v in R1.items()}, "modelC_sha256": sha("modelC.py"), "model5_sha256": sha("model5.py")}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "modelC.frozen.json"), "w").write(blob)
print("frozen modelC; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
for k in sorted(F["R1"]):
    d = F["D"][k]; print(f"  {k:22} R1={F['R1'][k]:7.1f}  D_web={d['web']:5.1f} D_api={d['api']:5.1f} D_db={d['db']:5.1f}  n={F['n'][k]}")
