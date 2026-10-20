#!/usr/bin/env python3
"""Freeze the home-path model (item 5): model v7 equations with a HARDWARE-SPLIT calibration.
Client side: this Mac's local stack (calibH at RTT 0, gridH netem 30-150 ms, 10 Mbit/s).
Server side: server (calib6, RTT 0) minus the Mac, measured as time-to-first-byte of the
requests on each action's critical path. No home-path data is used."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load("calibH.jsonl", "calibH-runs.jsonl")
grid, gruns, e2, u2 = load("gridH.jsonl", "gridH-runs.jsonl")
os.environ["SERVER_LOGS"] = "server-raw"      # server actions are classified with server's server logs
pos, pruns, e3, u3 = load("server-raw/calib6.jsonl", "server-raw/calib6-runs.jsonl")
del os.environ["SERVER_LOGS"]
assert not (e1 or u1 or e2 or u2 or e3 or u3), (len(e1), len(u1), len(e2), len(u2), len(e3), len(u3))

def critical_ttfb(a):
    """Server time on the action's critical path: sum of TTFBs of its requests (RTT 0)."""
    t = lambda r: r["responseStart"] - r["requestStart"]
    res = a.get("res") or []
    if a["o"] == "tq_hit": return 0.0
    if a["action"] == "initial":
        doc = [t(r) for r in res if r["type"] == "navigation"]
        api = [t(r) for r in res if r["type"] == "fetch" and "/api/products" in r["name"]] if a["mode"] == "csr" else []
        return sum(doc[:1]) + sum(api[:1])
    key = "/api/products" if a["mode"] == "csr" else "_rsc="
    return sum(t(r) for r in res if r["type"] == "fetch" and key in r["name"])

def by_outcome(acts):
    d = defaultdict(list)
    for a in acts: d[(a["mode"], a["action"], a["o"])].append(critical_ttfb(a))
    return {k: mean(v) for k, v in d.items()}

mac_srv, pos_srv = by_outcome(calib), by_outcome(pos)
T0_mac = calibrate_T0(calib)
delta = {k: pos_srv.get(k, mac_srv[k]) - mac_srv[k] for k in mac_srv}
T0 = {k: T0_mac[k] + delta.get(k, 0.0) for k in T0_mac}
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
tcp0["web_api"] = mean([(r["tcpPre"]["web_api"] + r["tcpPost"]["web_api"]) / 2 for r in pruns.values()])  # measured on server
B = calibrate_bytes(calib, grid)
inp = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2, 0.0)
rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
for a in grid:
    if a["mode"] == "csr" and a["action"] == "initial":
        b, new = bundle_obs(a); c, _ = inp(gruns[a["runId"]])
        g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(l.items())] for grp, l in lv.items()}
for grp in ("new", "reused"):   # a group unseen at some RTTs falls back to the other's curve
    curves.setdefault(grp, curves["reused" if grp == "new" else "new"])
cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
for a in grid:
    c, i = inp(gruns[a["runId"]])
    p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
    g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
    g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0_mac, B, 10e6, curves, p))
corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": B, "T0": {"|".join(k): v for k, v in T0.items()},
     "T0_mac": {"|".join(k): v for k, v in T0_mac.items()}, "serverDelta": {"|".join(k): v for k, v in delta.items()},
     "tcp0": tcp0, "curves": curves, "correction": corr,
     "p_netem": mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial"),
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "modelH.frozen.json"), "w").write(blob)
print("frozen modelH; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
print("server delta (server - Mac, ms):", {"|".join(k): round(v, 1) for k, v in delta.items()})
