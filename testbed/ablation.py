#!/usr/bin/env python3
"""A1 (TWEB revision): retrospective ablation of the frozen latency models on their own
fresh tests. Every variant recomputes each action's prediction from the frozen parameters
and the inputs recorded before the run; the full variant must reproduce the stored
prediction exactly (asserted), so the other variants differ only in the term removed.

Variants
  full         the frozen model as used in the test
  no_rho       the interpolated residual correction removed (and v8b's SSR-nav transfer offset)
  no_rho_abun  no_rho, and the empirical race-split bundle curves (v7 family) replaced by the
               analytic slow-start simulation of the calibration loads' chunk dispatch (model4)
  pooled_T0    no_rho, and T0 pooled over cache outcomes per (mode, action): the network
               term still follows the outcome's path, the service time does not
  service      T0 of the action's outcome only (no network term, no correction)

Scores use evaluate_n.py's cells: (mode, cache setting, client RTT, internal RTT, action),
observed and predicted means over seeds. Retrospective: these tests were already scored.
usage: python3 ablation.py [--json out.json]
"""
import copy, json, os, sys
from collections import defaultdict

import model4, model7, model9
from lib import jl, load, mean

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def fj(rel):
    return json.load(open(os.path.join(R, rel)))


# test tag, results subdir, family, frozen file, predictions file, SERVER_LOGS
TESTS = [
    ("prosp5", "", "v5", "model5.frozen.json", "predictions5.jsonl", ""),
    ("rep5", "", "v5", "model5.frozen.json", "predictions5.jsonl", ""),
    ("real7", "server-final", "v7", "server-final/model7.frozen.json", "server-final/predictions7.jsonl", "server-final"),
    ("rep7", "server-final", "v7", "server-final/model7.frozen.json", "server-final/predictions7.jsonl", "server-final"),
    ("real8b", "server-final", "v8b", "server-final/model8b.frozen.json", "server-final/predictions8b.jsonl", "server-final"),
    ("rep8b", "server-final", "v8b", "server-final/model8b.frozen.json", "server-final/predictions8b.jsonl", "server-final"),
    ("real9", "server-final", "v9", "server-final/model9.frozen.json", "server-final/predictions9.jsonl", "server-final"),
    ("rep9", "server-final", "v9", "server-final/model9.frozen.json", "server-final/predictions9.jsonl", "server-final"),
    ("test9b", "server-final", "v9", "server-final/model9b.frozen.json", "server-final/predictions9b.jsonl", "server-final"),
    ("reptest9b", "server-final", "v9", "server-final/model9b.frozen.json", "server-final/predictions9b.jsonl", "server-final"),
    ("testS", "", "v7", "modelS.frozen.json", "predictionsS.jsonl", ""),
    ("repS", "", "v7", "modelS.frozen.json", "predictionsS.jsonl", ""),
    ("testQ", "", "L", "modelLQ.frozen.json", "predictionsQ.jsonl", ""),
    ("repQ", "", "L", "modelLQ.frozen.json", "predictionsQ.jsonl", ""),
    ("testR2", "server-R2", "L", "server-R2/modelLR2.frozen.json", "server-R2/predictionsR2.jsonl", "server-R2"),
    ("repR2", "server-R2", "L", "server-R2/modelLR2.frozen.json", "server-R2/predictionsR2.jsonl", "server-R2"),
    ("realH3", "", "H3", "modelH3.frozen.json", "predictionsH3.jsonl", "server-final"),
    ("repH3", "", "H3", "modelH3.frozen.json", "predictionsH3.jsonl", "server-final"),
]
VARIANTS = ("full", "no_rho", "no_rho_abun", "pooled_T0", "service")


def strip(F, variant):
    """Copy of the frozen parameters with the variant's terms removed."""
    F = copy.deepcopy(F)

    def walk(d):
        if isinstance(d, dict):
            for k in list(d):
                if k in ("correction", "transfer") and variant != "full":
                    d[k] = {}
                elif k == "T0" and variant == "pooled_T0":
                    by = defaultdict(list)
                    for key, v in d[k].items():
                        m, a, _ = key.split("|"); by[(m, a)].append(v)
                    d[k] = {key: mean(by[tuple(key.split("|")[:2])]) for key in d[k]}
                else:
                    walk(d[k])
    walk(F)
    return F


def analytic_bundle_net(orig):
    """model7.net with the CSR-initial bundle term from model4's chunk-dispatch simulation."""
    def net(mode, action, o, crtt, irtt, B, bw_bps, curves, p):
        if mode == "csr" and action == "initial":
            return model4.net(mode, action, o, crtt, irtt, B, bw_bps or float("inf"))
        return orig(mode, action, o, crtt, irtt, B, bw_bps, curves, p)
    return net


def T0d(L):
    return {tuple(k.split("|")): v for k, v in L["T0"].items()}


def predictor(family, F, run, rec):
    """f(mode, action, o) -> ms, replicating the family's predict_run script with the
    inputs recorded before the run."""
    if family == "v5":
        import model5
        return lambda m, a, o: model5.predict(m, a, o, rec["crttIn"], rec["irttIn"], T0d(F), F["bytes"], 10e6, F["correction"])
    if family == "v7":
        return lambda m, a, o: model7.predict(m, a, o, rec["crttIn"], rec["irttIn"], T0d(F), F["bytes"], 10e6, F["curves"], F["correction"], rec["raceP"])
    if family == "v8b":
        import model8b
        return lambda m, a, o: model8b.predict(m, a, o, rec["crttIn"], rec["irttIn"], F, rec["bwBps"], rec["raceP"], F["transfer"])
    if family == "v9":
        return lambda m, a, o: model9.predict(m, a, o, rec["crttIn"], rec["irttIn"], T0d(F), F["bytes"], 10e6, F["curve"], F["correction"])
    if family == "H3":
        import modelH2
        return lambda m, a, o: modelH2.predict(m, a, o, rec["crttIn"], rec["irttIn"], F["levels"], rec["bwEq"], rec["raceP"])
    if family == "L":   # predict_runL.py: per-level v7, linear in the run's level value
        pre = run["tcpPre"]
        lv = sorted(F["levels"].items(), key=lambda kv: float(kv[0]))
        x = rec["level"]

        def one(L, m, a, o):
            tcp0 = L["tcp0"]
            crtt = max(0.0, (pre["client_web"] - tcp0["client_web"] + pre["client_api"] - tcp0["client_api"]) / 2)
            irtt = max(0.0, pre["web_api"] - tcp0["web_api"])
            p = rec["raceP"] if rec.get("raceP") is not None else L["p_netem"]
            return model7.predict(m, a, o, crtt, irtt, T0d(L), L["bytes"], 10e6, L["curves"], L["correction"], p)

        def f(m, a, o):
            if len(lv) == 1: return one(lv[0][1], m, a, o)
            i = next((k for k in range(1, len(lv)) if x <= float(lv[k][0])), len(lv) - 1)
            (x0, L0), (x1, L1) = (float(lv[i - 1][0]), lv[i - 1][1]), (float(lv[i][0]), lv[i][1])
            y0, y1 = one(L0, m, a, o), one(L1, m, a, o)
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return f
    raise ValueError(family)


def service_only(family, F, run, rec):
    """T0 of the action's path, at the run's bandwidth/level where the model has levels."""
    G = strip(F, "service")
    z = dict(rec, crttIn=0.0, irttIn=0.0)
    if family == "L":
        run = dict(run, tcpPre={k: G["levels"][next(iter(G["levels"]))]["tcp0"][k] for k in ("client_web", "client_api", "web_api")})
        # each level's own tcp0 gives crtt = irtt = 0 only if the levels share tcp0; force zero instead:
        f = predictor("L", G, run, z)
        orig = model7.predict
        return lambda m, a, o: _zero_rtt(orig, f, m, a, o)
    return predictor(family, G, run, z)


def _zero_rtt(orig, f, m, a, o):
    def p0(mode, action, oo, crtt, irtt, *rest):
        return orig(mode, action, oo, 0.0, 0.0, *rest)
    model7.predict = p0
    try:
        return f(m, a, o)
    finally:
        model7.predict = orig


def score(tag, sub, family, ffile, pfile, srv):
    os.environ["SERVER_LOGS"] = srv
    pre = f"{sub}/" if sub else ""
    acts, runs, _, _ = load(f"{pre}{tag}.jsonl", f"{pre}{tag}-runs.jsonl")
    recs = {p["runId"]: p for p in jl(pfile)}
    F = fj(ffile)
    stored = {(r, x["user"], x["step"]): x["pred"] for r, p in recs.items() for x in p["preds"]}
    o_pred = {(r, x["user"], x["step"]): x["o"] for r, p in recs.items() for x in p["preds"]}
    fns = {}
    for rid in runs:
        rec, run = recs[rid], runs[rid]
        fns[rid] = {
            "full": predictor(family, F, run, rec),
            "no_rho": predictor(family, strip(F, "no_rho"), run, rec),
            "pooled_T0": predictor(family, strip(F, "pooled_T0"), run, rec),
            "service": service_only(family, F, run, rec),
        }
        if family in ("v7", "v8b", "L", "H3"):
            fns[rid]["no_rho_abun"] = predictor(family, strip(F, "no_rho"), run, rec)
    cells = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    rho_share = defaultdict(list)
    orig_net = model7.net
    for a in acts:
        rid, act = a["runId"], a["action"]
        o = o_pred[(rid, a["user"], a["step"])]   # the outcome the model used (C4 checked it)
        k = (a["mode"], a["fe"], a["rtt"], a["irtt"], act)
        c = cells[k][a["seed"]]
        c["obs"].append(a["latencyMs"])
        for v, f in fns[rid].items():
            if v == "no_rho_abun":
                model7.net = analytic_bundle_net(orig_net)
                try: y = f(a["mode"], act, o)
                finally: model7.net = orig_net
            else:
                y = f(a["mode"], act, o)
            c[v].append(y)
        full = c["full"][-1]
        assert abs(full - stored[(rid, a["user"], a["step"])]) < 1e-6, (tag, rid, full, stored[(rid, a["user"], a["step"])])
        rho_share[(a["mode"], act)].append(abs(full - c["no_rho"][-1]) / full)
    out = {"tag": tag, "family": family, "cells": len(cells), "actions": len(acts), "runs": len(runs)}
    for v in VARIANTS:
        errs = []
        for k, s in cells.items():
            if v not in next(iter(s.values())): break
            obs = mean(mean(x["obs"]) for x in s.values()); pr = mean(mean(x[v]) for x in s.values())
            errs.append(abs(pr - obs) / obs)
        if errs and len(errs) == len(cells):
            out[v] = {"mean": 100 * mean(errs), "max": 100 * max(errs)}
    out["rho_share"] = {f"{m}|{a}": 100 * mean(x) for (m, a), x in sorted(rho_share.items())}
    return out


if __name__ == "__main__":
    res = [score(*t) for t in TESTS]
    hdr = f"{'test':10s} {'family':6s} " + " ".join(f"{v:>15s}" for v in VARIANTS) + "   |rho|/pred by (mode|action), %"
    print("A1 ablation (retrospective): mean / max relative error over cells, %")
    print(hdr)
    for r in res:
        cols = " ".join(f"{r[v]['mean']:6.2f} /{r[v]['max']:6.2f}" if v in r else f"{'n/a':>15s}" for v in VARIANTS)
        print(f"{r['tag']:10s} {r['family']:6s} {cols}   " + ", ".join(f"{k} {v:.1f}" for k, v in r["rho_share"].items()))
    if "--json" in sys.argv:
        json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
