#!/usr/bin/env python3
"""Freeze modelH2 (home path): per bandwidth level, the modelH hardware-split calibration.
Client side per level from this Mac's local stack under netem: 10 Mbit/s = calibH + gridH,
uncapped / 5 / 3 Mbit/s = calibH2 + gridH2 (split by rate). Server side: server (calib6) minus
the Mac at RTT 0 (same delta at every level). RTT input: request-level RTT minus its RTT-0
value (http0); under netem it equals the TCP-connect input (checked below). No home data used."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
cH, cHr, e1, u1 = load("calibH.jsonl", "calibH-runs.jsonl")
gH, gHr, e2, u2 = load("gridH.jsonl", "gridH-runs.jsonl")
c2, c2r, e3, u3 = load("calibH2.jsonl", "calibH2-runs.jsonl")
g2, g2r, e4, u4 = load("gridH2.jsonl", "gridH2-runs.jsonl")
os.environ["SERVER_LOGS"] = "server-raw"
pos, pruns, e5, u5 = load("server-raw/calib6.jsonl", "server-raw/calib6-runs.jsonl")
del os.environ["SERVER_LOGS"]
assert not any((e1, u1, e2, u2, e3, u3, e4, u4, e5, u5))

def critical_ttfb(a):
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

mac_srv, pos_srv = by_outcome(cH), by_outcome(pos)
delta = {k: pos_srv.get(k, mac_srv[k]) - mac_srv[k] for k in mac_srv}
web_api0 = mean([(r["tcpPre"]["web_api"] + r["tcpPost"]["web_api"]) / 2 for r in pruns.values()])

def level(calib, cruns, grid, gruns, bw):
    T0_mac = calibrate_T0(calib)
    tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in ("client_web", "client_api")}
    B = calibrate_bytes(calib, grid)
    inp = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2, 0.0)
    rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
    lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
    for a in grid:
        if a["mode"] == "csr" and a["action"] == "initial":
            b, new = bundle_obs(a); c, _ = inp(gruns[a["runId"]])
            g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
    curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(l.items())] for grp, l in lv.items()}
    for grp in ("new", "reused"):
        curves.setdefault(grp, curves["reused" if grp == "new" else "new"])
    cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
    for a in grid:
        c, i = inp(gruns[a["runId"]])
        p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
        g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
        g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0_mac, B, bw, curves, p))
    corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
    T0 = {k: T0_mac[k] + delta.get(k, 0.0) for k in T0_mac}
    return {"bytes": B, "T0": {"|".join(k): v for k, v in T0.items()}, "curves": curves, "correction": corr,
            "p_netem": mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")}

split = lambda acts, runs, rate: ([a for a in acts if runs[a["runId"]]["rate"] == rate], {k: r for k, r in runs.items() if r["rate"] == rate})
P = {"10mbit": level(cH, cHr, gH, gHr, 10e6)}
for name, rate, bw in (("inf", "", 1e12), ("5mbit", "5mbit", 5e6), ("3mbit", "3mbit", 3e6)):
    P[name] = level(*split(c2, c2r, rate), *split(g2, g2r, rate), bw)
http0 = mean(r["httpPre"]["mean"] for r in c2r.values())
# Check: under netem, request-level RTT input = TCP-connect input.
chk = defaultdict(list)
for r in g2r.values():
    tcp_in = (r["tcpPre"]["client_web"] + r["tcpPre"]["client_api"]) / 2
    chk[r["rtt"]].append(r["httpPre"]["mean"] - http0 - (tcp_in - mean((x["tcpPre"]["client_web"] + x["tcpPre"]["client_api"]) / 2 for x in c2r.values())))
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "levels": P, "http0": http0, "web_api0": web_api0,
     "serverDelta": {"|".join(k): v for k, v in delta.items()},
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7", "modelH2")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "modelH2.frozen.json"), "w").write(blob)
print("frozen modelH2; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "| http0", round(http0, 2))
print("http-minus-tcp input difference under netem, by RTT:", {k: round(mean(v), 2) for k, v in sorted(chk.items())})
for name in P: print(f"  {name:7s} bytes {P[name]['bytes']}  p_netem {P[name]['p_netem']:.2f}")
