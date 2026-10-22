#!/usr/bin/env python3
"""A2 (TWEB revision): equal-information baselines, retrospective.

Each baseline is fitted only on the calibration data its model family was frozen from, and
gets the same inputs per action that the frozen model got before the run:
  rendering mode, action, predicted cache outcome (one-hot group g = mode|action|outcome),
  client and internal RTT (pre-run TCP probe minus the frozen RTT-0 value), bandwidth factor
  x = min(1, 10 Mbit/s / bw) where the model uses bandwidth, CPU level where the model uses
  it, and the race probability p (CSR initial: in training the observed big-chunk connection,
  in testing the expectation p f(new) + (1 - p) f(reused), as the model does).
Baselines
  ridge   g one-hot plus g x (crtt, crtt^2 optional, irtt, x, level, new); degree and alpha by CV
  rf      random forest on (g one-hot, numeric); depth / leaf size by CV
  gbt     gradient-boosted trees; depth / learning rate by CV
CV: leave-one-nominal-client-RTT-out within calibration (no test data is used).
Scores: evaluate_n.py cells; a cell is "in range" if its mean client RTT input lies within
the calibration client-RTT range. The home path (H3) is omitted: its inputs come from a
separate request-level RTT and bundle-equivalent bandwidth procedure.
usage: <venv>/bin/python baselines_eq.py [--json out.json]
"""
import json, os, sys, warnings
from collections import defaultdict

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge

from lib import jl, load, mean
from model7 import bundle_obs
from model8 import x_of

warnings.filterwarnings("ignore")
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
fj = lambda rel: json.load(open(os.path.join(R, rel)))

PF = "server-final/"
# family: frozen file, calibration tags, logs dir, uses race p, uses bandwidth, uses level
FAM = {
    "v5": ("model5.frozen.json", ["calib3", "diag", "prosp3", "prosp4"], "", False, False, False),
    "v7": (PF + "model7.frozen.json", [PF + "calib6", PF + "grid6"], "server-final", True, False, False),
    "v8b": (PF + "model8b.frozen.json", [PF + t for t in ("calib6", "grid6", "calib8", "grid8", "real6", "rep6", "real7", "rep7", "real8", "rep8")],
            "server-final", True, True, False),
    "v9": (PF + "model9.frozen.json", [PF + "calib9", PF + "grid9"], "server-final", False, False, False),
    "v9b": (PF + "model9b.frozen.json", [PF + "calib9b", PF + "grid9b"], "server-final", False, False, False),
    "S": ("modelS.frozen.json", ["calibS", "gridS"], "", True, False, False),
    "LQ": ("modelLQ.frozen.json", ["calibQ", "gridQ"], "", True, False, False),
    "LR2": ("server-R2/modelLR2.frozen.json", ["server-R2/calibR2", "server-R2/gridR2"], "server-R2", True, False, True),
}
TESTS = [("prosp5", "", "v5", "predictions5.jsonl"), ("rep5", "", "v5", "predictions5.jsonl"),
         ("real7", PF, "v7", PF + "predictions7.jsonl"), ("rep7", PF, "v7", PF + "predictions7.jsonl"),
         ("real8b", PF, "v8b", PF + "predictions8b.jsonl"), ("rep8b", PF, "v8b", PF + "predictions8b.jsonl"),
         ("real9", PF, "v9", PF + "predictions9.jsonl"), ("rep9", PF, "v9", PF + "predictions9.jsonl"),
         ("test9b", PF, "v9b", PF + "predictions9b.jsonl"), ("reptest9b", PF, "v9b", PF + "predictions9b.jsonl"),
         ("testS", "", "S", "predictionsS.jsonl"), ("repS", "", "S", "predictionsS.jsonl"),
         ("testQ", "", "LQ", "predictionsQ.jsonl"), ("repQ", "", "LQ", "predictionsQ.jsonl"),
         ("testR2", "server-R2/", "LR2", "server-R2/predictionsR2.jsonl"), ("repR2", "server-R2/", "LR2", "server-R2/predictionsR2.jsonl")]


def tcp0_for(F, fam, run):
    if "levels" in F:
        lv = F["levels"]
        if len(lv) == 1: return next(iter(lv.values()))["tcp0"]
        return lv[str(int(float(run.get(F["levelKey"], 1))))]["tcp0"] if str(int(float(run.get(F["levelKey"], 1)))) in lv else next(iter(lv.values()))["tcp0"]
    return F["tcp0"]


def rtts(F, fam, run):
    t0, pre = tcp0_for(F, fam, run), run["tcpPre"]
    return (max(0.0, (pre["client_web"] - t0["client_web"] + pre["client_api"] - t0["client_api"]) / 2),
            max(0.0, pre["web_api"] - t0["web_api"]))


def bw_x(tag, run):
    if run.get("bwBps"): return x_of(run["bwBps"])
    return 0.0 if tag.rstrip("/").split("/")[-1].startswith(("calib8", "grid8")) else 1.0


def calib_rows(fam):
    ffile, tags, srv, use_p, use_bw, use_lv = FAM[fam]
    F = fj(ffile); os.environ["SERVER_LOGS"] = srv
    rows = []
    for t in tags:
        acts, runs, _, _ = load(f"{t}.jsonl", f"{t}-runs.jsonl")
        for a in acts:
            run = runs[a["runId"]]; c, i = rtts(F, fam, run)
            new = 0.0
            if use_p and a["mode"] == "csr" and a["action"] == "initial" and a.get("res"):
                try: new = float(bundle_obs(a)[1])
                except (ValueError, KeyError): new = 0.0
            rows.append({"g": f"{a['mode']}|{a['action']}|{a['o']}", "c": c, "i": i,
                         "x": bw_x(t, run) if use_bw else 1.0,
                         "lv": float(run.get(F.get("levelKey") or "", 1) or 1) if use_lv else 1.0,
                         "new": new, "y": a["latencyMs"], "grp": run["rtt"]})
    return F, rows


class Design:
    def __init__(self, groups): self.G = sorted(groups)

    def onehot(self, g):
        v = np.zeros(len(self.G)); v[self.G.index(g)] = 1.0; return v

    def lin(self, r, deg):
        oh = self.onehot(r["g"]); num = [r["c"], r["i"], r["x"], r["lv"], r["new"]] + ([r["c"] ** 2 / 1000] if deg == 2 else [])
        return np.concatenate([oh] + [oh * v for v in num])

    def tree(self, r):
        return np.concatenate([self.onehot(r["g"]), [r["c"], r["i"], r["x"], r["lv"], r["new"]]])


def candidates():
    for deg in (1, 2):
        for al in (0.01, 1.0, 100.0):
            yield "ridge", (deg, al)
    for d in (4, 8, None):
        for leaf in (1, 5):
            yield "rf", (d, leaf)
    for d in (2, 3, 5):
        for lr in (0.05, 0.1):
            yield "gbt", (d, lr)


def make(kind, hp, D, rows):
    X = np.array([D.lin(r, hp[0]) if kind == "ridge" else D.tree(r) for r in rows]); y = np.array([r["y"] for r in rows])
    if kind == "ridge": m = Ridge(alpha=hp[1])
    elif kind == "rf": m = RandomForestRegressor(n_estimators=200, max_depth=hp[0], min_samples_leaf=hp[1], random_state=0, n_jobs=-1)
    else: m = GradientBoostingRegressor(max_depth=hp[0], learning_rate=hp[1], n_estimators=300, random_state=0)
    m.fit(X, y)
    return lambda rs: m.predict(np.array([D.lin(r, hp[0]) if kind == "ridge" else D.tree(r) for r in rs]))


def cv_select(kind, D, rows):
    grps = sorted({r["grp"] for r in rows if r["grp"] > 0})
    best = None
    for k, hp in candidates():
        if k != kind: continue
        errs = []
        for gq in grps:   # leave one nominal client RTT out (RTT-0 runs always kept: they anchor T0)
            tr = [r for r in rows if r["grp"] != gq]; te = [r for r in rows if r["grp"] == gq]
            f = make(kind, hp, D, tr)
            by = defaultdict(lambda: [[], []])
            for r, yh in zip(te, f(te)): by[r["g"]][0].append(r["y"]); by[r["g"]][1].append(yh)
            errs += [abs(mean(p) - mean(o)) / mean(o) for o, p in by.values()]
        e = mean(errs)
        if best is None or e < best[0]: best = (e, hp)
    return best[1]


def run_family(fam, tests):
    F, rows = calib_rows(fam)
    use_p = FAM[fam][3]
    D = Design({r["g"] for r in rows} | {f"{m}|{a}|{o}" for m in ("csr", "ssr") for a in ("initial", "nav") for o in ("db", "redis_hit", "next_hit", "tq_hit")})
    models = {}
    for kind in ("ridge", "rf", "gbt"):
        hp = cv_select(kind, D, rows)
        models[kind] = (hp, make(kind, hp, D, rows))
    crange = (min(r["c"] for r in rows), max(r["c"] for r in rows))
    out = []
    for tag, sub, _, pfile in tests:
        os.environ["SERVER_LOGS"] = FAM[fam][2]
        acts, runs, _, _ = load(f"{sub}{tag}.jsonl", f"{sub}{tag}-runs.jsonl")
        recs = {p["runId"]: p for p in jl(pfile)}
        stored = {(rid, x["user"], x["step"]): x for rid, p in recs.items() for x in p["preds"]}
        cells = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        items = []
        for a in acts:
            run, rec = runs[a["runId"]], recs[a["runId"]]
            s = stored[(a["runId"], a["user"], a["step"])]
            c, i = rtts(F, fam, run)
            r = {"g": f"{a['mode']}|{a['action']}|{s['o']}", "c": c, "i": i,
                 "x": x_of(rec.get("bwBps")) if FAM[fam][4] else 1.0,
                 "lv": float(rec.get("level", 1) or 1) if FAM[fam][5] else 1.0, "new": 0.0}
            p = rec.get("raceP")
            if p is None and "levels" in F: p = next(iter(F["levels"].values())).get("p_netem")
            if p is None: p = F.get("p_netem", 0.0) if "p_netem" in F else F.get("cap", {}).get("p_netem", 0.0)
            mix = use_p and a["mode"] == "csr" and a["action"] == "initial"
            items.append((a, s, c, r, p if mix else 0.0))
        preds = {}
        for kind, (_, f) in models.items():
            y1 = f([dict(r, new=1.0) for _, _, _, r, _ in items]); y0 = f([dict(r, new=0.0) for _, _, _, r, _ in items])
            preds[kind] = [p * u + (1 - p) * v for (_, _, _, _, p), u, v in zip(items, y1, y0)]
        for n, (a, s, c, r, p) in enumerate(items):
            k = (a["mode"], a["fe"], a["rtt"], a["irtt"], a["action"])
            cc = cells[k][a["seed"]]
            cc["obs"].append(a["latencyMs"]); cc["model"].append(s["pred"]); cc["crtt"].append(c)
            for kind in models: cc[kind].append(preds[kind][n])
        res = {"tag": tag, "family": fam, "hp": {k: v[0] for k, v in models.items()}, "crange": crange,
               "cellseed": {"|".join(map(str, k)): {str(sd): {m: mean(v[m]) for m in ("obs", "model", "ridge", "rf", "gbt")}
                                                    for sd, v in s.items()} for k, s in cells.items()}}
        for slice_ in ("all", "in", "out"):
            for m in ("model", "ridge", "rf", "gbt"):
                errs = []
                for k, s in cells.items():
                    cm = mean(mean(x["crtt"]) for x in s.values())
                    inr = crange[0] <= cm <= crange[1]
                    if slice_ == "in" and not inr or slice_ == "out" and inr: continue
                    obs = mean(mean(x["obs"]) for x in s.values()); pr = mean(mean(x[m]) for x in s.values())
                    errs.append(abs(pr - obs) / obs)
                res[f"{slice_}:{m}"] = (100 * mean(errs), 100 * max(errs), len(errs)) if errs else None
        out.append(res)
    return out


if __name__ == "__main__":
    by = defaultdict(list)
    for t in TESTS: by[t[2]].append(t)
    res = []
    for fam, ts in by.items():
        res += run_family(fam, ts)
    print("A2 equal-information baselines (retrospective): mean / max relative error over cells, % [cells]")
    for sl in ("all", "in", "out"):
        print(f"-- {sl} cells")
        for r in res:
            row = []
            for m in ("model", "ridge", "rf", "gbt"):
                v = r[f"{sl}:{m}"]
                row.append(f"{m} {v[0]:6.2f}/{v[1]:6.2f}[{v[2]}]" if v else f"{m} {'-':>14s}")
            print(f"{r['tag']:10s} {r['family']:4s} " + "  ".join(row))
    print("hyperparameters:", {r["family"]: r["hp"] for r in res})
    if "--json" in sys.argv:
        json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1, default=str)
