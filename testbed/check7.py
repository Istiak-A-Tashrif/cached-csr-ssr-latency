#!/usr/bin/env python3
"""Mechanism check (diagnostic, NOT a test): v7 on already-used real-path data with p from diag6."""
import json
from collections import defaultdict
from lib import R, load, mean
from model7 import bundle_obs, predict
F = json.load(open(f"{R}/model7.frozen.json")); t0 = F["tcp0"]
T0 = {tuple(k.split("|")): v for k, v in F["T0"].items()}
diag, _, _, _ = load("diag6.jsonl", "diag6-runs.jsonl")
p = mean(bundle_obs(a)[1] for a in diag if a["mode"] == "csr" and a["action"] == "initial")
print(f"p (real path, diag6) = {p:.2f}; p (netem) = {F['p_netem']:.2f}")
for tag in ("real6", "rep6"):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
    cells = defaultdict(lambda: {"o": [], "p": []})
    for a in acts:
        q = runs[a["runId"]]["tcpPre"]; c = (q["client_web"] - t0["client_web"] + q["client_api"] - t0["client_api"]) / 2
        g = cells[(a["mode"], a["action"], a["fe"])]
        g["o"].append(a["latencyMs"]); g["p"].append(predict(a["mode"], a["action"], a["o"], c, 0, T0, F["bytes"], 10e6, F["curves"], F["correction"], p))
    errs = []
    for k, g in sorted(cells.items()):
        o, pr = mean(g["o"]), mean(g["p"]); errs.append(abs(pr - o) / o)
        print(f"  {tag} {k[1]:7} {k[0]} caches={'on ' if k[2] else 'off'}: obs {o:7.1f} v7 {pr:7.1f} ({100 * (pr - o) / o:+5.1f}%)")
    print(f"  {tag}: mean rel {100 * mean(errs):.2f}%  max {100 * max(errs):.2f}%")
