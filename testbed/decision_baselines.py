#!/usr/bin/env python3
"""Decision quality of simpler predictors (final TWEB revision, RETROSPECTIVE: every block below was
already scored with the frozen model; nothing here was pre-registered).

Question: would a simpler predictor have chosen policies as well as the frozen model did? Every
predictor gets only what the frozen model got before each run (the run's policy, declared write
process, pre-run client and internal RTT probes, added server work d, and the sessions: declared
sessions for the 27-candidate blocks, the K = 8 distribution-sampled session sets of predict_runR2.py
for the near-threshold blocks) and is fitted only on the calibration block its model was frozen from
(calibW for the catalogue, cdCal / cdCalH for Conduit). The selection rules, staleness limits and
margins are the frozen ones (evaluateR.py, evaluateRC.py, evaluateR2.py); only the predicted
(latency, stale share) per candidate changes.

Latency components
  model      the frozen predictions (timeline serving-layer distribution; per-layer line a + b c; + d P(db))
  ridge      ridge regression (alpha 1) on serving-layer indicators x (1, client RTT, internal RTT), fitted
             on the calibration views, given the model's predicted serving-layer distribution, + d P(db)
  calfreq    no timeline: serving-layer probabilities are the calibration frequencies per policy, action
             and revisit flag (the O2 reference frozen with each model), with the model's per-layer lines
             and d P(db)
  blind      cache-blind: one line in client RTT per (mode, action) pooled over the calibration
             policies; no serving layer, no d
Staleness components
  model      the frozen predictions (session timeline over stacked layers, Proposition 1)
  single     single-layer textbook rule: a view served from a TTL-configured layer (probability from the
             calibration frequencies) shows data of age uniform on [0, TTL], so it is stale with probability
             1 - (1/TTL) int_0^TTL P0(w) dw; push-invalidated layers and database reads count as fresh
Predictors: model (= model/model), ridge/model, calfreq/model, blind/model, model/single, calfreq/single.
Tied predicted latencies (cache-blind) are scored as the expected outcome of a uniformly random tied pick.

Also: latency given the TRUE serving layer. Each view's latency is re-predicted from its logged serving
layer (per-layer line + d if it was a database read) and scored with criterion L1 (mean relative error over
(cell, action)), against L1 of the frozen predictions, to separate serving-layer error from latency error.

Paired run bootstrap: seeds are resampled within every cell (all predictors together), 2,000 resamples;
95% intervals of each predictor's mean regret minus the model's, per block family.
usage: python3 decision_baselines.py   -> results/revision/decision-baselines.json
"""
import bisect, collections, json, os, random

import modelR, modelR2, modelRC
from modelR2 import layer_cfg, outcomes
from modelRC import page_p0
from predict_runR2 import sample_sessions, K
from writeproc import p0_factory

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
CLS = ("tq_hit", "next_hit", "redis_hit", "db")
EPS = (0.05, 0.10, 0.25, 0.50)
mean = lambda x: sum(x) / len(x)
# block: (results root, family, frozen model, calibration tag, predictions file, selection kind)
BLOCKS = {
    "revT": ("", "cat", "modelR.frozen.json", "calibW", "predictionsR.jsonl", "b4"),
    "revR": ("", "cat", "modelR.frozen.json", "calibW", "predictionsR.jsonl", "b4"),
    "cdT": ("", "cd", "modelRC.frozen.json", "cdCal", "predictionsRC.jsonl", "b4"),
    "cdR": ("", "cd", "modelRC.frozen.json", "cdCal", "predictionsRC.jsonl", "b4"),
    "cdHT": ("server-cd", "cd", "modelRC.frozen.json", "cdCalH", "predictionsRC.jsonl", "b4"),
    "cdHR": ("server-cd", "cd", "modelRC.frozen.json", "cdCalH", "predictionsRC.jsonl", "b4"),
    "revHT": ("", "cat", "modelR2.frozen.json", "calibW", "predictionsR2.jsonl", "hard"),
    "revHR": ("", "cat", "modelR2.frozen.json", "calibW", "predictionsR2.jsonl", "hard"),
    "revCCT": ("", "cat", "modelR2.frozen.json", "calibW", "predictionsR2.jsonl", "cc"),     # protocol v4
    "revCCR": ("", "cat", "modelR2.frozen.json", "calibW", "predictionsR2.jsonl", "cc"),
}
PREDICTORS = ("model", "ridge/model", "calfreq/model", "blind/model", "model/single", "calfreq/single")


def jl(root, name):
    p = os.path.join(RES, root, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def cell(run):
    c = f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}"
    if run["fe"] == "ttl" or run["rp"] == "ttl": c += f"-tau{run['tau']}"
    return c + f"-a{run['alpha']}"


def pol(run): return f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}"


def load_views(root, fam, tag):
    """Observed per-view latency, staleness (oracle) and serving layer, as the evaluators compute them."""
    runs = {r["runId"]: r for r in jl(root, f"{tag}-runs.jsonl")}
    api_rid, api_resp = {}, {}
    for x in jl(root, "api.jsonl"):
        if x.get("runId") in runs:
            if x.get("reqId"): api_rid[x["reqId"]] = x
            if x.get("respId"): api_resp[x["respId"]] = x
    W = collections.defaultdict(lambda: collections.defaultdict(list))
    for w in jl(root, "writes.jsonl"):
        if w["runId"] in runs: W[w["runId"]][w["productId"]].append(w["committed"])
    for d in W.values():
        for v in d.values(): v.sort()
    views = collections.defaultdict(list)
    for v in jl(root, f"{tag}.jsonl"):
        if v.get("runId") not in runs or "error" in v: continue
        run = runs[v["runId"]]
        st = any(shown != run["stock0"][str(pid)] + bisect.bisect_right(W[v["runId"]][pid], v["wall"]) for pid, shown in v["rows"])
        if v["mode"] == "csr":
            y = "tq_hit" if not v["tqRids"] else None
            x = None if y else api_rid.get(v["tqRids"][-1])
        else:
            y = None; x = api_resp.get(v.get("resp"))
            if x is not None and x["ts"] < v["wall"] - v["domMs"]: y = "next_hit"
        if y is None and x is not None: y = "redis_hit" if x["redis"] == "hit" else "db"
        views[v["runId"]].append({"u": v["user"], "s": v["step"], "action": v["action"], "lat": v["latencyMs"], "stale": st, "y": y})
    return runs, views


def solve(A, b):
    n = len(b); M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[c][c]:
                f = M[r][c] / M[c][c]; M[r] = [a - f * b_ for a, b_ in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] if M[i][i] else 0.0 for i in range(n)]


def ridge_fit(rows, alpha=1.0):
    """rows: (group, features, y). Per group, ridge on centred features (intercept unpenalized); the
    one-hot x feature design decouples by group, so this is the joint ridge fit."""
    by = collections.defaultdict(list)
    for g, f, y in rows: by[g].append((f, y))
    out = {}
    for g, pts in by.items():
        k = len(pts[0][0]); mf = [mean([p[0][j] for p in pts]) for j in range(k)]; my = mean([p[1] for p in pts])
        A = [[sum((p[0][a] - mf[a]) * (p[0][b] - mf[b]) for p in pts) + (alpha if a == b else 0.0) for b in range(k)] for a in range(k)]
        bv = [sum((p[0][a] - mf[a]) * (p[1] - my) for p in pts) for a in range(k)]
        w = solve(A, bv); out[g] = (my - sum(wj * m for wj, m in zip(w, mf)), w)
    return lambda g, f: out[g][0] + sum(wj * x for wj, x in zip(out[g][1], f))


def calibration(root, ctag):
    """Calibration views: (mode, action class, outcome class, client RTT, internal RTT, latency s)."""
    runs = jl(root, f"{ctag}-runs.jsonl"); recs = collections.defaultdict(list)
    for r in jl(root, f"{ctag}.jsonl"): recs[r["runId"]].append(r)
    rows = []
    for run in runs:
        rs = sorted(recs[run["runId"]], key=lambda r: (r["user"], r["step"]))
        for r, (a, o) in zip(rs, outcomes(run["users"], layer_cfg(run))):
            rows.append((run["mode"], a, o, run["tcpPre"]["client_web"], run["tcpPre"]["web_api"], r["latencyMs"] / 1000))
    ridge = ridge_fit([(f"{m}|{a}|{o}", (c, i), y) for m, a, o, c, i, y in rows])
    blind = ridge_fit([(f"{m}|{a}", (c,), y) for m, a, o, c, i, y in rows], alpha=0.0)
    return ridge, blind


def int_p0(p0, tau, page=None, n=200):
    f = (lambda w: p0(w, page)) if page is not None else p0
    h = tau / n
    return h * (f(0) / 2 + sum(f(k * h) for k in range(1, n)) + f(tau) / 2) / tau


def ttl_layer(run, y):
    if y == "tq_hit": return run["fe"] == "ttl"
    if y == "next_hit": return run["fe"] == "ttl"
    if y == "redis_hit": return run["rp"] == "ttl"
    return False


def predict_run(run, fam, M, ridge, blind, sessions_list, probs, sim):
    """Per-run predicted mean latency (ms) and stale share for every non-stored component."""
    c, i, d = run["tcpPre"]["client_web"], run["tcpPre"]["web_api"], run["dbDelayMs"] / 1000
    line = lambda m, a, o: M["lat"][f"{m}|{a}|{o}"]["a"] + M["lat"][f"{m}|{a}|{o}"]["b"] * c
    gap = lambda m, a, o: M["gap"][f"{m}|{a}|{o}"]["a"] + M["gap"][f"{m}|{a}|{o}"]["b"] * c
    cfg = layer_cfg(run)
    if fam == "cd": p0 = page_p0(run["proc"], probs)
    else: p0b = p0_factory(run["proc"], run["pages"]); p0 = lambda w, page: p0b(w)
    REF = M["outcome_reference"]
    acc = collections.defaultdict(float)
    for sess in sessions_list:
        if fam == "cd": v = [x[:3] for x in modelRC.simulate(sess, gap, line, cfg, c / 1000, d, p0)]
        else: v = sim(sess, gap, line, cfg, c / 1000, d, lambda w: p0(w, None))
        oc = outcomes(sess, cfg); k = 0; n = len(oc)
        lr = lc = lb = ss = 0.0
        for seq in sess:
            seen = set()
            for page in seq:
                a, o = oc[k]; dist = v[k][2]; k += 1
                rev = page in seen; seen.add(page)
                ocl = lambda y: "tq_hit" if y == "tq_hit" else "next_hit" if y == "next_hit" else "db"
                # ridge, given the model's serving-layer distribution
                lr += sum(p * ridge(f"{run['mode']}|{a}|{ocl(y)}", (c, i)) for y, p in dist.items() if p) + d * dist["db"]
                # calibration frequencies, no timeline
                key = f"{pol(run)}|{'initial' if a == 'initial' else 'nav'}|{rev}"
                rf = REF.get(key) or ({"db": 1.0} if not run["fe"] and not run["rp"] else None)
                if rf is None: raise SystemExit(f"no calibration frequency for {key}")
                lc += sum(p * line(run["mode"], a, ocl(y)) for y, p in rf.items() if p) + d * rf.get("db", 0.0)
                lb += blind(f"{run['mode']}|{a}", (c,))
                h = sum(p for y, p in rf.items() if p and ttl_layer(run, y))
                if h: ss += h * (1 - int_p0(p0, run["tau"], page))
        acc["ridge"] += 1000 * lr / n / len(sessions_list); acc["calfreq"] += 1000 * lc / n / len(sessions_list)
        acc["blind"] += 1000 * lb / n / len(sessions_list); acc["single"] += ss / n / len(sessions_list)
    return acc


def decisions(kind, MAN, cs_obs, cs_pred, alpha_cells):
    """Yield (decision id, candidate cells, eps, margin) for the frozen selection rule."""
    if kind == "b4":
        for alpha, cs in alpha_cells.items():
            for eps in EPS: yield f"a{alpha}|{eps}", cs, eps, 0.0
    else:
        cs = list(cs_obs)
        for setname, eps_list in MAN["eps"].items():
            sub = [c for c in cs if setname == "all" or "push" not in c]
            for eps in eps_list:
                for name, margin in (("point", 0.0), ("margin", MAN["margin"])):
                    yield f"{setname}|{eps}|{name}", sub, eps, margin


def score(dec, obs, prd, lo):
    """Score every decision for one predictor; ties in predicted latency -> expected outcome."""
    out = []
    for did, cs, eps, margin in dec:
        feas = [c for c in cs if obs[c][1] <= eps]
        best = min(feas, key=lambda c: obs[c][0]) if feas else None
        ok = [c for c in cs if prd[c][1] + margin <= eps]
        if not ok: out.append({"id": did, "abstain": True}); continue
        lmin = min(prd[c][0] for c in ok); picks = [c for c in ok if prd[c][0] - lmin < 1e-6]
        viol = mean([obs[c][1] > eps for c in picks]); conf = mean([lo[c] > eps for c in picks]) if lo else 0.0
        exc = max(max(0.0, obs[c][1] - eps) for c in picks)
        fr = [(obs[c][0] - obs[best][0]) / obs[best][0] for c in picks if obs[c][1] <= eps] if best else []
        out.append({"id": did, "abstain": False, "picks": picks, "viol": viol, "confirmed": conf, "excess": exc,
                    "regret": mean(fr) if fr else None, "right": mean([c == best for c in picks]) if best else 0.0})
    return out


def summarize(rs):
    sel = [r for r in rs if not r["abstain"]]; reg = [r["regret"] for r in sel if r["regret"] is not None]
    return {"decisions": len(rs), "abstentions": len(rs) - len(sel), "violations": round(sum(r["viol"] for r in sel), 2),
            "confirmed": round(sum(r["confirmed"] for r in sel), 2), "max_excess": max([r["excess"] for r in sel], default=0.0),
            "oracle_choices": round(sum(r["right"] for r in sel), 2),
            "mean_regret": 100 * mean(reg) if reg else None, "worst_regret": 100 * max(reg) if reg else None}


def block(tag, rng):
    root, fam, mfile, ctag, pfile, group = BLOCKS[tag]
    kind = "hard" if group == "cc" else group    # v4 blocks are scored like v3's, reported as their own group
    M = json.load(open(os.path.join(RES, root, mfile)))
    MAN = json.load(open(os.path.join(HERE, "protocol", f"{tag}.json"))) if kind == "hard" else None
    probs = {int(k): v for k, v in M["page_probs"].items()} if fam == "cd" else None
    runs, views = load_views(root, fam, tag)
    stored = {p["runId"]: p for p in jl(root, pfile) if p["runId"] in runs}
    ridge, blind = calibration(root, ctag)
    per = collections.defaultdict(list)       # cell -> per-run dict of observed and predicted values
    lat_true = collections.defaultdict(lambda: [[], [], []])
    for rid, vs in views.items():
        run, p = runs[rid], stored[rid]
        if kind == "hard":
            n, L = len(run["users"]), len(run["users"][0])
            sl = [sample_sessions(n, L, run["pages"], run["alpha"], 9_000_011 * (k + 1) + run["seed"]) for k in range(K)]
            m_lat, m_st = p["lat"], p["stale"]
        else:
            sl = [run["users"]]; m_lat, m_st = mean([x["ms"] for x in p["views"]]), p["stale"]
        acc = predict_run(run, fam, M, ridge, blind, sl, probs, modelR2.simulate if kind == "hard" else modelR.simulate)
        per[cell(run)].append({"L": mean([v["lat"] for v in vs]), "S": mean([v["stale"] for v in vs]),
                               "model": (m_lat, m_st), "ridge/model": (acc["ridge"], m_st), "calfreq/model": (acc["calfreq"], m_st),
                               "blind/model": (acc["blind"], m_st), "model/single": (m_lat, acc["single"]),
                               "calfreq/single": (acc["calfreq"], acc["single"])})
        # latency given the true serving layer (declared-session predictions, as criterion L1)
        c = run["tcpPre"]["client_web"]; pl = {(x["user"], x["step"]): x["ms"] for x in p["views"]}
        for v in vs:
            if v["y"] is None or (v["u"], v["s"]) not in pl: continue
            a = "initial" if v["s"] == 0 else "nav1" if v["s"] == 1 else "nav"
            o = v["y"] if v["y"] in ("tq_hit", "next_hit") else "db"
            t = 1000 * (M["lat"][f"{run['mode']}|{a}|{o}"]["a"] + M["lat"][f"{run['mode']}|{a}|{o}"]["b"] * c) + run["dbDelayMs"] * (v["y"] == "db")
            k = (cell(run), v["action"]); lat_true[k][0].append(v["lat"]); lat_true[k][1].append(pl[(v["u"], v["s"])]); lat_true[k][2].append(t)
    l1 = lambda j: 100 * mean([abs(mean(x[j]) - mean(x[0])) / mean(x[0]) for x in lat_true.values()])
    lo = {}
    for c, xs in per.items():
        bs = sorted(mean([rng.choice(xs)["S"] for _ in xs]) for _ in range(4000)); lo[c] = bs[int(0.025 * len(bs))]
    alpha_cells = collections.defaultdict(list)
    for c in per: alpha_cells[c.split("-a")[1]].append(c)
    obs = {c: (mean([x["L"] for x in xs]), mean([x["S"] for x in xs])) for c, xs in per.items()}
    dec = list(decisions(kind, MAN, obs, None, alpha_cells))
    res = {"tag": tag, "kind": group, "cells": len(per), "seeds_per_cell": sorted({len(x) for x in per.values()}),
           "L1_predicted_layer": l1(1), "L1_true_layer": l1(2), "predictors": {}, "scenarios": len(alpha_cells) if kind == "b4" else len(MAN["eps"])}
    scored = {}
    for name in PREDICTORS:
        prd = {c: (mean([x[name][0] for x in xs]), mean([x[name][1] for x in xs])) for c, xs in per.items()}
        scored[name] = score(dec, obs, prd, lo)
        if kind == "hard":
            res["predictors"][name] = {sel: summarize([r for r in scored[name] if r["id"].endswith("|" + sel)]) for sel in ("point", "margin")}
        else:
            res["predictors"][name] = summarize(scored[name])
    res["per_decision"] = {name: [{k: v for k, v in r.items() if k != "picks"} for r in rs] for name, rs in scored.items()}
    # consistency with the stored evaluation (regret of the frozen model's own choices)
    ev = json.load(open(os.path.join(RES, "revision", f"{tag}-evaluation.json")))
    if kind == "b4":
        st = [r["selector"]["regret"] for r in ev["selection"].values() if not r["selector"].get("abstain") and r["selector"]["regret"] is not None]
        assert abs(100 * mean(st) - res["predictors"]["model"]["mean_regret"]) < 1e-9, (tag, mean(st), res["predictors"]["model"])
        for m in ("tuning", "fixed", "default", "nocache"):
            rs = [r[m] for r in ev["selection"].values()]
            if all(r.get("abstain") for r in rs): continue
            sel = [r for r in rs if not r.get("abstain")]; reg = [r["regret"] for r in sel if r["regret"] is not None]
            res["per_decision"][m] = [{"id": k, "abstain": bool(r.get("abstain")), "viol": float(r.get("violation", 0)), "excess": r.get("excess", 0.0),
                                       "regret": r.get("regret")} for k, r in ((k, row[m]) for k, row in ev["selection"].items())]
            res["predictors"][m] = {"decisions": len(rs), "abstentions": len(rs) - len(sel), "violations": sum(r["violation"] for r in sel),
                                    "max_excess": max(r["excess"] for r in sel), "mean_regret": 100 * mean(reg) if reg else None,
                                    "worst_regret": 100 * max(reg) if reg else None}
    else:
        assert abs(ev["selectors"]["aware" if group == "hard" else "margin"]["mean_regret"] - res["predictors"]["model"]["margin"]["mean_regret"]) < 1e-9, tag
    # paired run bootstrap of mean regret differences vs the model
    keys = sorted(per); diffs = collections.defaultdict(list)
    for _ in range(2000):
        smp = {c: [rng.choice(per[c]) for _ in per[c]] for c in keys}
        o = {c: (mean([x["L"] for x in xs]), mean([x["S"] for x in xs])) for c, xs in smp.items()}
        base = None
        for name in PREDICTORS:
            prd = {c: (mean([x[name][0] for x in xs]), mean([x[name][1] for x in xs])) for c, xs in smp.items()}
            rs = [r for r in score(dec, o, prd, None) if not r["abstain"] and (kind == "b4" or r["id"].endswith("|margin"))]
            # regret with violations counted at their regret if feasible, else excluded; plus violation count
            reg = [r["regret"] for r in rs if r["regret"] is not None]
            val = (100 * mean(reg) if reg else 0.0, sum(r["viol"] for r in rs))
            if name == "model": base = val
            else: diffs[name].append((val[0] - base[0], val[1] - base[1]))
    res["bootstrap"] = {}
    for name, xs in diffs.items():
        r_ = sorted(x[0] for x in xs); v_ = sorted(x[1] for x in xs)
        res["bootstrap"][name] = {"regret_diff_ci": (r_[49], r_[1949]), "viol_diff_ci": (v_[49], v_[1949])}
    return res


if __name__ == "__main__":
    rng = random.Random(23); out = []
    for tag in BLOCKS:
        r = block(tag, rng); out.append(r)
        print(f"{tag}: {r['cells']} cells, seeds/cell {r['seeds_per_cell']}, scenarios {r['scenarios']}; "
              f"L1 with predicted layer {r['L1_predicted_layer']:.2f}%, with true layer {r['L1_true_layer']:.2f}%")
        for name, s in r["predictors"].items():
            for sub, x in ((s.items()) if "point" in s else [("", s)]):
                mr = "-" if x["mean_regret"] is None else f"{x['mean_regret']:.2f}"
                wr = "-" if x["worst_regret"] is None else f"{x['worst_regret']:.2f}"
                bs = r["bootstrap"].get(name)
                b = f"  d-regret CI [{bs['regret_diff_ci'][0]:+.2f}, {bs['regret_diff_ci'][1]:+.2f}] d-viol CI [{bs['viol_diff_ci'][0]:+.1f}, {bs['viol_diff_ci'][1]:+.1f}]" if bs and sub != "point" else ""
                print(f"   {name + (' ' + sub if sub else ''):22s} dec {x['decisions']:2d} abst {x['abstentions']:2d} viol {x['violations']:5} "
                      f"(max +{x['max_excess']:.3f}) regret mean {mr} worst {wr}{b}")
    json.dump(out, open(os.path.join(RES, "revision", "decision-baselines.json"), "w"), indent=1)
