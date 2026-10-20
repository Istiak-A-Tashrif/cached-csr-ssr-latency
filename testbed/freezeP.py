#!/usr/bin/env python3
"""Freeze modelP from calibP (N = 1, server pinned cores): R1 per (mode, action), per-action
CPU demand per station (cgroup CPU minus idle rate; full sessions vs initial-only sessions)
and C1, the wall time per action of full sessions."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, jl, load, mean

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
acts, runs, err, unc = load("calibP.jsonl", "calibP-runs.jsonl")
assert not err and not unc, (len(err), len(unc))
GROUP = {"client": ["client"], "app": ["web", "api", "redis"], "db": ["db"]}

def busy(run):   # ms of CPU per station during the run, idle rate removed
    w = run["wallMs"] / 1000
    return {st: 1000 * sum(run["cpu"][c] - run["idleCpu"][c] * w for c in cs) for st, cs in GROUP.items()}

R1 = defaultdict(list); D = {}; C1 = {}
for a in acts: R1[f"{a['mode']}|{a['action']}"].append(a["latencyMs"])
for mode in ("csr", "ssr"):
    full = [r for r in runs.values() if r["mode"] == mode and not r.get("initOnly")]
    init = [r for r in runs.values() if r["mode"] == mode and r.get("initOnly")]
    d_init = {st: mean(busy(r)[st] / len(r["users"]) for r in init) for st in GROUP}
    n_nav = lambda r: sum(len(s) - 1 for s in r["users"])
    d_nav = {st: mean((busy(r)[st] - len(r["users"]) * d_init[st]) / n_nav(r) for r in full) for st in GROUP}
    D[f"{mode}|initial"], D[f"{mode}|nav"] = d_init, d_nav
    C1[mode] = mean(r["wallMs"] / sum(map(len, r["users"])) for r in full)
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "R1": {k: mean(v) for k, v in R1.items()}, "D": D, "C1": C1,
     "n": {k: len(v) for k, v in R1.items()}, "modelP_sha256": sha("modelP.py"), "model5_sha256": sha("model5.py")}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "modelP.frozen.json"), "w").write(blob)
print("frozen modelP; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
for k in sorted(F["R1"]):
    d = D[k]; print(f"  {k:12} R1={F['R1'][k]:7.1f}  D_client={d['client']:6.1f} D_app={d['app']:6.1f} D_db={d['db']:6.1f}  n={F['n'][k]}")
print("  C1 (ms/action):", {k: round(v, 1) for k, v in C1.items()})
