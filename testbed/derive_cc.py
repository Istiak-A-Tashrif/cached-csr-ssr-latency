#!/usr/bin/env python3
"""Protocol v4 development step (PROTOCOL_CC.md): derive sd_m for the chance-constrained selector from the
development blocks only (revT, revR, revHT, revHR: catalogue, Poisson writes, already scored), and report
what the frozen-a selector would have done on revHT/revHR (in-sample; for information, not a test).

Per cell: pred = model R2's distribution-only stale share from each run's pre-run inputs (8 sampled
session sets, seeds as predict_runR2.py), averaged over the cell's runs; obs = the oracle's stale share
averaged over runs; sd_s = selector_cc.block_sd at the cell's mean condition with the cell's run count.
sd_m^2 = max(0, mean(e^2 - sd_s^2)), e = obs - pred.
usage: python3 derive_cc.py   -> results/revision/cc-derivation.json"""
import collections, json, math, os
from decision_baselines import load_views, cell
from predict_runR2 import predict, sample_sessions, K
from selector_cc import block_sd, select, z_of

A = 0.05   # fixed in advance: the coverage of v3's margin (a 95th percentile), now per candidate
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
out = {"a": A, "z": z_of(A), "cells": []}
blocks = {}
for tag in ("revT", "revR", "revHT", "revHR"):
    runs, views = load_views("", "cat", tag)
    per = collections.defaultdict(list)
    for rid, vs in views.items():
        r = runs[rid]; n, L = len(r["users"]), len(r["users"][0])
        sl = [sample_sessions(n, L, r["pages"], r["alpha"], 9_000_011 * (k + 1) + r["seed"]) for k in range(K)]
        s, l, _ = predict(r, sl)
        per[cell(r)].append((sum(v["lat"] for v in vs) / len(vs), sum(v["stale"] for v in vs) / len(vs), l, s, r))
    cells = {}
    for c, xs in per.items():
        r0 = dict(xs[0][4]); r0["tcpPre"] = {"client_web": sum(x[4]["tcpPre"]["client_web"] for x in xs) / len(xs)}
        _, sd = block_sd(r0, len(xs), len(r0["users"]), len(r0["users"][0]), reps=200, seed=hash(c) & 0xffff)
        rec = {"block": tag, "cell": c, "obs_L": sum(x[0] for x in xs) / len(xs), "obs_S": sum(x[1] for x in xs) / len(xs),
               "pred_L": sum(x[2] for x in xs) / len(xs), "pred_S": sum(x[3] for x in xs) / len(xs), "sd_s": sd, "n": len(xs)}
        cells[c] = rec; out["cells"].append(rec)
    blocks[tag] = cells
    print(f"{tag}: {len(cells)} cells")
e2 = [(c["obs_S"] - c["pred_S"]) ** 2 for c in out["cells"]]; s2 = [c["sd_s"] ** 2 for c in out["cells"]]
out["sd_m"] = math.sqrt(max(0.0, sum(e2) / len(e2) - sum(s2) / len(s2)))
out["rmse"] = math.sqrt(sum(e2) / len(e2)); out["rms_sd_s"] = math.sqrt(sum(s2) / len(s2))
out["mean_error"] = sum(c["obs_S"] - c["pred_S"] for c in out["cells"]) / len(out["cells"])
out["frac_within"] = sum(abs(c["obs_S"] - c["pred_S"]) <= out["z"] * math.sqrt(c["sd_s"] ** 2 + out["sd_m"] ** 2) for c in out["cells"]) / len(out["cells"])
print(f"RMSE {out['rmse']:.4f}, rms sd_s {out['rms_sd_s']:.4f}, mean error {out['mean_error']:+.4f} -> sd_m {out['sd_m']:.4f}; "
      f"|e| within z*sd in {100 * out['frac_within']:.1f}% of cells")

# In-sample look at the near-threshold blocks with the frozen limits (information only).
out["insample"] = {}
for tag in ("revHT", "revHR"):
    MAN = json.load(open(os.path.join(os.path.dirname(RES), "protocol", f"{tag}.json"))); cs = blocks[tag]
    rows = []
    for setname, eps_list in MAN["eps"].items():
        sub = {c: v for c, v in cs.items() if setname == "all" or "push" not in c}
        for eps in eps_list:
            feas = [c for c in sub if sub[c]["obs_S"] <= eps]; best = min(feas, key=lambda c: sub[c]["obs_L"]) if feas else None
            pick = select({c: (v["pred_L"], v["pred_S"], v["sd_s"]) for c, v in sub.items()}, eps, A, out["sd_m"])
            if pick is None: rows.append({"eps": eps, "set": setname, "abstain": True}); continue
            v = sub[pick]
            rows.append({"eps": eps, "set": setname, "pick": pick, "viol": v["obs_S"] > eps,
                         "regret": None if v["obs_S"] > eps or best is None else (v["obs_L"] - sub[best]["obs_L"]) / sub[best]["obs_L"]})
    reg = [r["regret"] for r in rows if r.get("regret") is not None]
    out["insample"][tag] = {"decisions": len(rows), "abstain": sum(r.get("abstain", False) for r in rows), "viol": sum(r.get("viol", False) for r in rows),
                            "mean_regret": 100 * sum(reg) / len(reg) if reg else None, "worst": 100 * max(reg) if reg else None}
    print(tag, "in-sample:", out["insample"][tag])
json.dump(out, open(os.path.join(RES, "revision", "cc-derivation.json"), "w"), indent=1)
