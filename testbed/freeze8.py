#!/usr/bin/env python3
"""Freeze model v8 from netem data only: 10 Mbit/s level (calib6 + grid6) and uncapped level (calib8 + grid8)."""
import hashlib, json, os, time
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()


def level(calib_tag, grid_tag, bw):
    calib, cruns, e1, u1 = load(f"{calib_tag}.jsonl", f"{calib_tag}-runs.jsonl")
    grid, gruns, e2, u2 = load(f"{grid_tag}.jsonl", f"{grid_tag}-runs.jsonl")
    assert not (e1 or u1 or e2 or u2), (calib_tag, grid_tag)
    links = ("client_web", "client_api", "web_api")
    tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
    B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
    inp = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                       max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))
    rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
    lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
    for a in grid:
        if a["mode"] == "csr" and a["action"] == "initial":
            b, new = bundle_obs(a); c, _ = inp(gruns[a["runId"]])
            g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
    curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(l.items())] for grp, l in lv.items()}
    cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
    for a in grid:
        c, i = inp(gruns[a["runId"]])
        p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
        g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
        g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0, B, bw, curves, p))
    corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
    return {"bytes": B, "T0": {"|".join(k): v for k, v in T0.items()}, "tcp0": tcp0, "curves": curves, "correction": corr,
            "p_netem": mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")}


cap, inf = level("calib6", "grid6", 10e6), level("calib8", "grid8", 1e12)
tcp0 = {l: (cap["tcp0"][l] + inf["tcp0"][l]) / 2 for l in cap["tcp0"]}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "cap": cap, "inf": inf, "tcp0": tcp0,
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7", "model8")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, "model8.frozen.json"), "w").write(blob)
print("frozen model8; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16])
for name, L in (("cap 10Mbit", cap), ("uncapped", inf)):
    print(f"  {name}: T0 csr initial db {L['T0']['csr|initial|db']:.1f} ms, ssr initial db {L['T0']['ssr|initial|db']:.1f} ms, p_netem {L['p_netem']:.2f}")
