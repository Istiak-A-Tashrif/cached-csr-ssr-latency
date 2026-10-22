#!/usr/bin/env python3
"""Model R2, protocol v3: per-run prediction written BEFORE the run from the access DISTRIBUTION only
(Zipf alpha over the pages, users, session length) -- K = 8 session sets sampled with seeds unrelated to
the run's -- plus, for comparison, the prediction with the declared sessions. Output: predictionsR2.jsonl."""
import hashlib, json, os, random, sys, time
from modelR2 import layer_cfg, simulate, stale_fraction
from writeproc import p0_factory

here = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(here, "results", "modelR2.frozen.json")))
for f, h in M["files"].items():
    if hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()[:16] != h: raise SystemExit(f"{f} changed since freeze")
K = 8


def sample_sessions(n_users, length, pages, alpha, seed):
    rng = random.Random(seed); w = [1 / (i + 1) ** alpha for i in range(pages)]; out = []
    for _ in range(n_users):
        seq = []
        while len(seq) < length:
            p = rng.choices(range(1, pages + 1), weights=w)[0]
            if not seq or p != seq[-1]: seq.append(p)
        out.append(seq)
    return out


def predict(run, sessions_list):
    crtt = run["tcpPre"]["client_web"]
    fit = lambda tab: (lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt)
    p0 = p0_factory(run["proc"], run["pages"]); st = lat = pdb = 0.0
    for sess in sessions_list:
        v = simulate(sess, fit(M["gap"]), fit(M["lat"]), layer_cfg(run), crtt / 1000, run["dbDelayMs"] / 1000, p0)
        st += stale_fraction(v, p0) / len(sessions_list); lat += 1000 * sum(x[1] for x in v) / len(v) / len(sessions_list)
    return st, lat, v


if __name__ == "__main__":
    run = json.loads(open(sys.argv[1]).read())
    n, L = len(run["users"]), len(run["users"][0])
    dist = [sample_sessions(n, L, run["pages"], run["alpha"], 9_000_011 * (k + 1) + run["seed"]) for k in range(K)]
    s_dist, l_dist, _ = predict(run, dist)
    s_dec, l_dec, v = predict(run, [run["users"]])
    steps = [(u, s) for u, seq in enumerate(run["users"]) for s in range(len(seq))]
    with open(os.path.join(here, "results", "predictionsR2.jsonl"), "a") as fh:
        fh.write(json.dumps({"runId": run["runId"], "ts": time.time() * 1000, "sha": M["sha"], "stale": s_dist, "lat": l_dist,
                             "stale_declared": s_dec, "lat_declared": l_dec,
                             "views": [{"user": u, "step": s, "ms": 1000 * l, "dist": d} for (u, s), (_, l, d) in zip(steps, v)]}) + "\n")
    print(f"predicted stale {s_dist:.3f} (distribution only), {s_dec:.3f} (declared sessions)")
