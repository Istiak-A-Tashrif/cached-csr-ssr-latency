#!/usr/bin/env python3
"""Post-hoc margin sensitivity (not a test; only margin 0.05 was pre-registered) for the near-threshold
blocks: the selector requires predicted stale share + m <= eps. For each m: decisions, violations (observed
stale share > eps), violations confirmed by the run-bootstrap 2.5% bound, oracle choices, abstentions,
mean and worst regret. Uses the frozen distribution-only predictions and the scored observations."""
import collections, json, os, random, sys
R = "results"
out = {}
for tag in ("revHT", "revHR"):
    man = json.load(open(f"protocol/{tag}.json"))
    src = open("evaluateR2.py").read().split("runs, views, preds, W, lags, errors, ahead, unl = load_block(tag)")[0]
    g = {"__name__": "diag", "__file__": os.path.abspath("evaluateR2.py")}; sys.argv = ["x", tag]
    exec(compile(src, "ev", "exec"), g)
    runs, views, preds, *_ = g["load_block"](tag)
    per = collections.defaultdict(list)
    for rid, vs in views.items():
        per[g["cell"](runs[rid])].append((sum(v["lat"] for v in vs) / len(vs), sum(v["stale"] for v in vs) / len(vs), preds[rid]["lat"], preds[rid]["stale"]))
    m_ = lambda x: sum(x) / len(x)
    obs = {c: (m_([x[0] for x in xs]), m_([x[1] for x in xs])) for c, xs in per.items()}
    prd = {c: (m_([x[2] for x in xs]), m_([x[3] for x in xs])) for c, xs in per.items()}
    rng = random.Random(7); lo = {}
    for c, xs in per.items():
        bs = sorted(m_([rng.choice(xs)[1] for _ in xs]) for _ in range(4000)); lo[c] = bs[100]
    for margin in (0.0, 0.02, 0.03, 0.05, 0.07):
        rec = []
        for setname, eps_list in man["eps"].items():
            cs = [c for c in obs if setname == "all" or "push" not in c]
            for eps in eps_list:
                feas = [c for c in cs if obs[c][1] <= eps]; best = min(feas, key=lambda c: obs[c][0]) if feas else None
                ok = [c for c in cs if prd[c][1] + margin <= eps]
                if not ok: rec.append({"abstain": True}); continue
                pick = min(ok, key=lambda c: prd[c][0])
                rec.append({"viol": obs[pick][1] > eps, "conf": lo[pick] > eps, "right": pick == best,
                            "regret": (obs[pick][0] - obs[best][0]) / obs[best][0] if best else None})
        r = out.setdefault(str(margin), collections.Counter()); regs = out.setdefault(f"reg{margin}", [])
        for x in rec:
            r["decisions"] += 1
            if x.get("abstain"): r["abstain"] += 1; continue
            r["viol"] += x["viol"]; r["conf"] += x["conf"]; r["right"] += x["right"]
            if not x["viol"] and x["regret"] is not None: regs.append(x["regret"])
res = {}
for margin in ("0.0", "0.02", "0.03", "0.05", "0.07"):
    c = out[margin]; regs = out[f"reg{float(margin)}"]
    res[margin] = {**c, "mean_regret": 100 * sum(regs) / len(regs) if regs else None, "worst_regret": 100 * max(regs) if regs else None}
    print(f"margin {margin}: {c['decisions']} decisions, {c['viol']} violations ({c['conf']} confirmed), {c['abstain']} abstentions, {c['right']} oracle choices, "
          f"mean regret {res[margin]['mean_regret']:.1f}%, worst {res[margin]['worst_regret']:.1f}%")
json.dump(res, open("results/revision/diag-margin.json", "w"), indent=1)
