#!/usr/bin/env python3
"""A3 (TWEB revision): calibration efficiency, retrospective. The v7-equation model (freezeL.py's
fit, in memory) and the cache-aware ridge baseline (A2's design, degree 1, alpha 1) are refitted
on subsets of each family's emulated calibration grid -- fewer client-RTT points, fewer seeds --
and scored on the family's fresh tests. The RTT-0 calibration runs are always kept (they give T0
and byte sizes). Cost = calibration runs and their summed wall time.
usage: <venv>/bin/python calib_efficiency.py [--json out.json]
"""
import itertools, json, os, sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import Ridge

from lib import jl, load, mean
from model4 import calibrate_bytes, calibrate_T0
from model7 import base, bundle_obs, predict

PF = "server-final/"
# family: calib tag, grid tag, logs dir, tests [(tag, sub, predictions)], svelte renaming
FAM = {
    "v7 (real path)": (PF + "calib6", PF + "grid6", "server-final",
                       [("real7", PF, PF + "predictions7.jsonl"), ("rep7", PF, PF + "predictions7.jsonl")], False),
    "S (SvelteKit)": ("calibS", "gridS", "", [("testS", "", "predictionsS.jsonl"), ("repS", "", "predictionsS.jsonl")], True),
    "LQ (heavy page)": ("calibQ", "gridQ", "", [("testQ", "", "predictionsQ.jsonl"), ("repQ", "", "predictionsQ.jsonl")], False),
}


def fit_model(calib, cruns, grid, gruns):
    links = ("client_web", "client_api", "web_api")
    tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in cruns.values()]) for l in links}
    B, T0 = calibrate_bytes(calib, grid), calibrate_T0(calib)
    inputs = lambda run: ((run["tcpPre"]["client_web"] - tcp0["client_web"] + run["tcpPre"]["client_api"] - tcp0["client_api"]) / 2,
                          max(0.0, run["tcpPre"]["web_api"] - tcp0["web_api"]))
    rtt0 = mean(bundle_obs(a)[0] for a in calib if a["mode"] == "csr" and a["action"] == "initial")
    lv = defaultdict(lambda: defaultdict(lambda: {"c": [], "b": []}))
    for a in grid:
        if a["mode"] == "csr" and a["action"] == "initial":
            b, new = bundle_obs(a); c, _ = inputs(gruns[a["runId"]])
            g = lv["new" if new else "reused"][a["rtt"]]; g["c"].append(c); g["b"].append(b)
    curves = {grp: [[0.0, rtt0]] + [[mean(v["c"]), mean(v["b"])] for _, v in sorted(l.items())] for grp, l in lv.items()}
    for grp in ("new", "reused"):
        curves.setdefault(grp, curves.get("reused" if grp == "new" else "new", [[0.0, rtt0]]))
    cells = defaultdict(lambda: defaultdict(lambda: {"c": [], "r": []}))
    for a in grid:
        c, i = inputs(gruns[a["runId"]])
        p = (1.0 if bundle_obs(a)[1] else 0.0) if (a["mode"] == "csr" and a["action"] == "initial") else 0.0
        g = cells[f"{a['mode']}|{a['action']}|{a['o']}"][a["rtt"]]
        g["c"].append(c); g["r"].append(a["latencyMs"] - base(a["mode"], a["action"], a["o"], c, i, T0, B, 10e6, curves, p))
    corr = {k: [[mean(v["c"]), mean(v["r"])] for _, v in sorted(l.items())] for k, l in cells.items()}
    p_netem = mean(bundle_obs(a)[1] for a in grid if a["mode"] == "csr" and a["action"] == "initial")
    return {"T0": T0, "B": B, "tcp0": tcp0, "curves": curves, "corr": corr, "p_netem": p_netem, "inputs": inputs}


GROUPS = [f"{m}|{a}|{o}" for m in ("csr", "ssr") for a in ("initial", "nav") for o in ("db", "redis_hit", "next_hit", "tq_hit")]


def feat(g, c, i, new):
    oh = np.array([1.0 if g == x else 0.0 for x in GROUPS])
    return np.concatenate([oh, oh * c, oh * i, oh * new])


def fit_ridge(M, calib, cruns, grid, gruns):
    X, y = [], []
    for acts, runs in ((calib, cruns), (grid, gruns)):
        for a in acts:
            c, i = M["inputs"](runs[a["runId"]])
            new = float(bundle_obs(a)[1]) if a["mode"] == "csr" and a["action"] == "initial" and a.get("res") else 0.0
            X.append(feat(f"{a['mode']}|{a['action']}|{a['o']}", c, i, new)); y.append(a["latencyMs"])
    return Ridge(alpha=1.0).fit(np.array(X), np.array(y))


def svelte_fix(acts):
    for a in acts:
        for r in a.get("res") or []:
            if r["type"] == "fetch" and "__data.json" in r["name"] and "#_rsc=" not in r["name"]: r["name"] += "#_rsc="


def evaluate(M, rg, tests):
    out = {}
    for tag, sub, pfile in tests:
        acts, runs, _, _ = load(f"{sub}{tag}.jsonl", f"{sub}{tag}-runs.jsonl")
        recs = {p["runId"]: p for p in jl(pfile)}
        o_pred = {(r, x["user"], x["step"]): x["o"] for r, p in recs.items() for x in p["preds"]}
        rows, Xn, Xr = [], [], []
        for a in acts:
            run, rec = runs[a["runId"]], recs[a["runId"]]
            c, i = M["inputs"](run)
            o = o_pred[(a["runId"], a["user"], a["step"])]
            p = rec.get("raceP") if rec.get("raceP") is not None else M["p_netem"]
            act = a["action"]
            yM = predict(a["mode"], act, o, c, i, M["T0"], M["B"], 10e6, M["curves"], M["corr"], p)
            g = f"{a['mode']}|{act}|{o}"
            mix = a["mode"] == "csr" and act == "initial"
            rows.append((a, yM, p if mix else 0.0)); Xn.append(feat(g, c, i, 1.0)); Xr.append(feat(g, c, i, 0.0))
        y1, y0 = rg.predict(np.array(Xn)), rg.predict(np.array(Xr))
        cells = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for (a, yM, p), u, v in zip(rows, y1, y0):
            s = cells[(a["mode"], a["fe"], a["rtt"], a["irtt"], a["action"])][a["seed"]]
            s["obs"].append(a["latencyMs"]); s["model"].append(yM); s["ridge"].append(p * u + (1 - p) * v)
        for m in ("model", "ridge"):
            errs = [abs(mean(mean(x[m]) for x in s.values()) - mean(mean(x["obs"]) for x in s.values())) /
                    mean(mean(x["obs"]) for x in s.values()) for s in cells.values()]
            out[f"{tag}:{m}"] = 100 * mean(errs)
    return out


def main():
    results = []
    for fam, (ct, gt, srv, tests, sv) in FAM.items():
        os.environ["SERVER_LOGS"] = srv
        calib, cruns, _, _ = load(f"{ct}.jsonl", f"{ct}-runs.jsonl")
        grid, gruns, _, _ = load(f"{gt}.jsonl", f"{gt}-runs.jsonl")
        if sv: svelte_fix(calib + grid)
        rtts = sorted({r["rtt"] for r in gruns.values()}); seeds = sorted({r["seed"] for r in gruns.values()})
        subsets = []
        for k in range(len(rtts), 0, -1):
            for sub_r in itertools.combinations(rtts, k):
                for sub_s in ([tuple(seeds)] + ([(s,) for s in seeds] if len(seeds) > 1 else [])):
                    subsets.append((sub_r, sub_s))
        for sub_r, sub_s in subsets:
            keep = {rid for rid, r in gruns.items() if r["rtt"] in sub_r and r["seed"] in sub_s}
            g = [a for a in grid if a["runId"] in keep]; gr = {k: v for k, v in gruns.items() if k in keep}
            if not any(a["mode"] == "csr" and a["action"] == "initial" for a in g): continue
            try:
                M = fit_model(calib, cruns, g, gr)
            except (KeyError, ValueError, ZeroDivisionError, IndexError) as e:
                print("skip", fam, sub_r, sub_s, type(e).__name__); continue
            rg = fit_ridge(M, calib, cruns, g, gr)
            ev = evaluate(M, rg, tests)
            runs_n = len(cruns) + len(gr)
            wall = (sum(r.get("wallMs", 0) for r in cruns.values()) + sum(r.get("wallMs", 0) for r in gr.values())) / 60000
            results.append({"family": fam, "rtts": list(sub_r), "seeds": list(sub_s), "runs": runs_n, "wall_min": wall, **ev})
            print(f"{fam:16s} rtts={list(sub_r)!s:22s} seeds={len(sub_s)} runs={runs_n:3d} wall={wall:5.0f} min  " +
                  "  ".join(f"{k} {v:5.2f}" for k, v in ev.items()), flush=True)
    if "--json" in sys.argv:
        json.dump(results, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)


if __name__ == "__main__":
    main()
