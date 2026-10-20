#!/usr/bin/env python3
"""Freeze modelP3: modelP2's N = 1 calibration plus calibP3 (N = 2 and 6, server).
(1) alpha_k, beta_k: least squares of rho = observed per-action CPU / N=1 mix demand on
    (N - 1), with the N = 1 point rho = 1 (calibP2 runs) included.
(2) P_client per (mode, action): least squares through the origin of
    R(N) - R1 - sum_{app,db} P_k s_k Q_k  on  s_client Q_client, over the N = 2 and 6 runs."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from modelP3 import STATIONS, queues

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
F = json.load(open(os.path.join(R, "modelP2.frozen.json")))
acts, runs, err, unc = load("calibP3.jsonl", "calibP3-runs.jsonl")
assert not err and not unc, (len(err), len(unc))
assert not [r for r in runs.values() if r["cpu"]["barrierLateMs"] > 0], "barrier missed"
GROUP = {"client": ["client"], "app": ["web", "api", "redis"], "db": ["db"]}
_, p2runs, _, _ = load("calibP2.jsonl", "calibP2-runs.jsonl")
idle = {c: mean(r["idleCpu"][c] for r in p2runs.values() if r.get("idleCpu")) for c in ("client", "web", "api", "redis", "db")}

def keys_of(run):
    return [f"{run['mode']}|initial"] * len(run["users"]) + [f"{run['mode']}|nav"] * sum(len(s) - 1 for s in run["users"])

pts = defaultdict(list)                     # station -> [(N - 1, rho)]
for r in runs.values():
    ks = keys_of(r); n = r["n"]
    for st, cs in GROUP.items():
        dur = (r["steadyMs"] if st == "client" else r["wallMs"]) / 1000
        busy = 1000 * sum(r["cpu"][c] - idle[c] * dur for c in cs)
        if st != "client": busy -= n * F["D"][f"{r['mode']}|initial"][st]      # warm-up loads
        d1 = mean(F["D"][x][st] for x in ks)
        pts[st].append((n - 1, busy / len(ks) / d1))
alpha, beta = {}, {}
for st, xy in pts.items():
    xy = xy + [(0, 1.0)] * len(xy)          # N = 1 anchor, equal weight
    mx = mean(x for x, _ in xy); my = mean(y for _, y in xy)
    b = sum((x - mx) * (y - my) for x, y in xy) / sum((x - mx) ** 2 for x, _ in xy)
    beta[st] = b; alpha[st] = my - b * mx
F3 = {**F, "alpha": alpha, "beta": beta}
num, den = defaultdict(float), defaultdict(float)
for rid, r in runs.items():
    q = queues(keys_of(r), r["n"], F3)
    for cls in (f"{r['mode']}|initial", f"{r['mode']}|nav"):
        obs = [a["latencyMs"] for a in acts if a["runId"] == rid and f"{a['mode']}|{a['action']}" == cls]
        s = lambda k: F3["alpha"][k] + F3["beta"][k] * (r["n"] - 1)
        y = mean(obs) - F["R1"][cls] - sum(F["P"][cls][k] * s(k) * q[k] for k in ("app", "db"))
        x = s("client") * q["client"]
        num[cls] += x * y * len(obs); den[cls] += x * x * len(obs)
P = {cls: {**F["P"][cls], "client": num[cls] / den[cls]} for cls in F["P"]}
F3.update({"P": P, "P_client_logs": {c: F["P"][c]["client"] for c in F["P"]}, "frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "modelP3_sha256": sha("modelP3.py"), "modelP2_sha256": sha("modelP2.py")})
blob = json.dumps(F3, indent=1, sort_keys=True)
open(os.path.join(R, "modelP3.frozen.json"), "w").write(blob)
print("frozen modelP3; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
print("demand scale alpha + beta (N-1):", {k: (round(alpha[k], 3), round(beta[k], 4)) for k in alpha})
for c in sorted(P): print(f"  {c:12} P_client fitted {P[c]['client']:7.1f}  (RTT-0 estimate {F['P'][c]['client']:6.1f})")
