#!/usr/bin/env python3
"""Freeze model v9 (HTTPS + HTTP/2) from netem data only: calib9 (RTT 0) + grid9 (120-550 ms)."""
import hashlib, json, os, time
TAG = os.environ.get("MODEL_TAG", "9")   # v9b: MODEL_TAG=9b
from collections import defaultdict
from lib import R, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import bundle_obs
from model9 import base

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
calib, cruns, e1, u1 = load(f"calib{TAG}.jsonl", f"calib{TAG}-runs.jsonl")
grid, gruns, e2, u2 = load(f"grid{TAG}.jsonl", f"grid{TAG}-runs.jsonl")
assert not (e1 or u1 or e2 or u2)
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
inp = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                   max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))
csr0 = [a for a in calib if a["mode"] == "csr" and a["action"] == "initial"]
lv = defaultdict(lambda: {"c": [], "b": []})
for a in grid:
    if a["mode"] == "csr" and a["action"] == "initial":
        c, _ = inp(gruns[a["runId"]]); lv[a["rtt"]]["c"].append(c); lv[a["rtt"]]["b"].append(bundle_obs(a)[0])
curve = [[0.0, mean(bundle_obs(a)[0] for a in csr0)]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(lv.items())]
newshare = mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")
cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
for a in grid:
    c, i = inp(gruns[a["runId"]])
    g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
    g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6, curve))
corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
F = {"frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": B, "T0": {"|".join(k): v for k, v in T0.items()}, "tcp0": tcp0,
     "curve": curve, "correction": corr, "bigChunkOnNewConnShare": newshare,
     **{f"{m}_sha256": sha(f"{m}.py") for m in ("model2", "model4", "model5", "model7", "model9")}}
blob = json.dumps(F, indent=1, sort_keys=True)
open(os.path.join(R, f"model{TAG}.frozen.json"), "w").write(blob)
print(f"frozen model{TAG}; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "| big chunk on new conn share (expect ~0 under h2):", round(newshare, 2))
print("bundle curve:", [[round(x), round(y)] for x, y in curve])
print("corrections:", {k: [round(y, 1) for _, y in v] for k, v in corr.items()})
