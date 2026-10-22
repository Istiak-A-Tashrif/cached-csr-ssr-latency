#!/usr/bin/env python3
"""Post-hoc (not a test): criterion O1 (P(db) calibration per decile, bins with >= 100 views) recomputed on
a scored block with modelR and with candidate fixes to the timing of the framework-push exposure:
  R   frozen model (exposure from the last access to the view's DISPLAY time)
  R2  exposure to the request's arrival at the server (display - half RTT - render)
  R3  exposure to action start + half RTT (display - predicted latency + half RTT)
usage: python3 diag_o1_variants.py <tag> ..."""
import collections, json, os, sys, types
from writeproc import p0_factory
src = open("evaluateR.py").read().split("runs, views, preds, W, lags, errors, ahead, unl = load_block(tag)")[0]
base = open("modelR.py").read()
OLD = 'p_db = 1 - p0(t + gap(cfg["mode"], action, o) - ent[2])'
VAR = {"R": base,
       "R2": base.replace(OLD, 'p_db = 1 - p0(t + gap(cfg["mode"], action, o) - crtt_s / 2 - RENDER_S - ent[2])'),
       "R3": base.replace(OLD, 'p_db = 1 - p0(t + gap(cfg["mode"], action, o) - lat(cfg["mode"], action, o) + crtt_s / 2 - ent[2])')}
mods = {}
for k, s in VAR.items():
    m = types.ModuleType(k); exec(compile(s, k, "exec"), m.__dict__); mods[k] = m
M = json.load(open("results/modelR.frozen.json"))
for tag in sys.argv[1:]:
    g = {"__name__": "diag", "__file__": os.path.abspath("evaluateR.py")}; sys.argv = [sys.argv[0], tag]
    exec(compile(src, "ev", "exec"), g)
    runs, views, *_ = g["load_block"](tag)
    for name, mod in mods.items():
        bins = collections.defaultdict(lambda: [0, 0.0, 0])
        for rid, vs in views.items():
            run = runs[rid]; crtt = run["tcpPre"]["client_web"]
            fit = lambda tab: (lambda mm, a, o: tab[f"{mm}|{a}|{o}"]["a"] + tab[f"{mm}|{a}|{o}"]["b"] * crtt)
            sim = mod.simulate(run["users"], fit(M["gap"]), fit(M["lat"]), mod.layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0_factory(run["proc"], run["pages"]))
            steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
            dist = {k: d for k, (_, _, d) in zip(steps, sim)}
            for v in vs:
                d = dist.get((v["u"], v["s"]))
                if d and v["y"] and 0 < d["db"] < 1:
                    b = bins[min(9, int(d["db"] * 10))]; b[0] += 1; b[1] += d["db"]; b[2] += v["y"] == "db"
        dev = [(k, b[0], b[1] / b[0], b[2] / b[0]) for k, b in sorted(bins.items()) if b[0] >= 100]
        worst = max(dev, key=lambda x: abs(x[2] - x[3]))
        print(f"{tag} {name}: O1 {'PASS' if all(abs(p - o) <= 0.05 for _, _, p, o in dev) else 'FAIL'}; worst decile {worst[0]} (n={worst[1]}) pred {worst[2]:.3f} obs {worst[3]:.3f}; "
              f"mean |dev| {sum(abs(p - o) for _, _, p, o in dev) / len(dev):.3f}")
