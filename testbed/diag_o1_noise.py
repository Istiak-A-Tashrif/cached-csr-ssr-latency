#!/usr/bin/env python3
"""Post-hoc (not a test): are the O1 decile deviations larger than run-level sampling noise? For each
decile of predicted P(db) (frozen predictions), the observed-minus-predicted deviation with a 95% interval
from a bootstrap over runs (views of one run are correlated). usage: python3 diag_o1_noise.py <tag> [R|RC]"""
import collections, json, os, random, sys
tag = sys.argv[1]; kind = sys.argv[2] if len(sys.argv) > 2 else "R"
ev = "evaluateR.py" if kind == "R" else "evaluateRC.py"
src = open(ev).read().split("runs, views, preds, W, lags, errors, ahead, unl = load_block(tag)")[0]
g = {"__name__": "diag", "__file__": os.path.abspath(ev)}; sys.argv = [sys.argv[0], tag]
exec(compile(src, "ev", "exec"), g)
runs, views, preds, *_ = g["load_block"](tag)
per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0]))   # run -> decile -> [n, pred, obs]
for rid, vs in views.items():
    pl = {(x["user"], x["step"]): x["dist"] for x in preds[rid]["views"]}
    for v in vs:
        d = pl.get((v["u"], v["s"]))
        if d and v["y"] and 0 < d["db"] < 1:
            b = per[rid][min(9, int(d["db"] * 10))]; b[0] += 1; b[1] += d["db"]; b[2] += v["y"] == "db"
rids = sorted(per); rng = random.Random(11); out = []
for k in range(10):
    tot = [sum(per[r][k][i] for r in rids) for i in range(3)]
    if tot[0] < 100: continue
    dev = tot[2] / tot[0] - tot[1] / tot[0]
    bs = []
    for _ in range(2000):
        s = [rng.choice(rids) for _ in rids]; n = sum(per[r][k][0] for r in s)
        if n: bs.append((sum(per[r][k][2] for r in s) - sum(per[r][k][1] for r in s)) / n)
    bs.sort(); lo, hi = bs[50], bs[1949]
    nr = sum(1 for r in rids if per[r][k][0])
    out.append((k, tot[0], nr, dev, lo, hi))
    pass
    print(f"{tag} decile {k}: n={tot[0]:5d} views from {nr:3d} runs  obs-pred {dev:+.3f}  95% run-bootstrap [{lo:+.3f}, {hi:+.3f}]  {'|dev|>0.05' if abs(dev) > 0.05 else ''} {'interval excludes 0' if lo > 0 or hi < 0 else ''}")
json.dump([{"decile": k, "views": a, "runs": b, "dev": c, "lo": d, "hi": e} for k, a, b, c, d, e in out],
          open(f"results/revision/diag-o1-noise-{tag}.json", "w"), indent=1)
