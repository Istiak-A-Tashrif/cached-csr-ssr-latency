#!/usr/bin/env python3
"""Protocol v3 (near-threshold policy selection): run manifests and the staleness limits eps, written once
before any run and hashed into protocol/FROZEN_HARD.json. Seeds 960-999 (never used before).
16 candidate policies chosen to be close (finer TTLs 2/4/8 s). The limits are placed where decisions are
hardest: from the frozen model R2's distribution-only predictions at the block's nominal condition, each
eps is the predicted stale share of a Pareto-front candidate plus 0.01, so the point selector picks a
policy whose predicted staleness sits just under the limit, and minus 0.01, so it sits just over it.
Two decision sets: all 16 candidates, and the TTL-only subset (no push invalidation, as when an
application cannot hook its writes)."""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from predict_runR2 import predict, sample_sessions

CANDS = [("ssr", "push", "push", None), ("ssr", False, False, None), ("csr", False, False, None), ("ssr", "ttl", "ttl", 2)]
for tau in (2, 4, 8):
    CANDS += [("ssr", False, "ttl", tau), ("ssr", "ttl", "push", tau), ("csr", "ttl", "push", tau), ("csr", False, "ttl", tau)]
ALPHA, PAGES, USERS, LEN = 0.8, 8, 16, 12


def name(mode, fe, rp, tau):
    return f"{mode}-fe{fe or 'off'}-rd{rp or 'off'}" + (f"-tau{tau}" if tau else "") + f"-a{ALPHA}"


def eps_for(rtt, d, lam):
    pts = []
    for mode, fe, rp, tau in CANDS:
        run = {"mode": mode, "fe": fe, "rp": rp, "S": tau or 3600, "T": tau or 3600, "pages": PAGES, "alpha": ALPHA,
               "proc": {"kind": "poisson", "lam": lam}, "dbDelayMs": d, "tcpPre": {"client_web": rtt + 1.2}}
        sess = [sample_sessions(USERS, LEN, PAGES, ALPHA, 31_337 * (k + 1)) for k in range(8)]
        s, l, _ = predict(run, sess)
        pts.append((l, s, name(mode, fe, rp, tau)))
    eps = {}
    for setname, keep in (("all", lambda n: True), ("ttl_only", lambda n: "push" not in n)):
        sub = [p for p in pts if keep(p[2])]
        front = [p for p in sub if not any(q[0] <= p[0] and q[1] <= p[1] and q != p for q in sub)]
        eps[setname] = sorted({round(s + off, 3) for _, s, _ in front if 0.03 <= s <= 0.6 for off in (-0.01, 0.01)})
    return eps, sorted(pts)


def block(tag, seeds, rtt, d, lam):
    eps, pts = eps_for(rtt, d, lam)
    runs = []
    for seed in seeds:
        for mode, fe, rp, tau in CANDS:
            runs.append({"seed": seed, "rtt": rtt, "mode": mode, "fe": fe, "rp": rp, "tau": tau or 3600, "alpha": ALPHA, "d": d,
                         "proc": {"kind": "poisson", "lam": lam}, "cellName": name(mode, fe, rp, tau)})
    random.Random(sum(map(ord, tag))).shuffle(runs)
    for i, r in enumerate(runs):
        r["runId"] = f"{tag}-s{r['seed']}-r{rtt}-{r['cellName']}"; r["wseed"] = r["seed"] * 101 + i
    json.dump({"tag": tag, "predictor": "predict_runR2.py", "eps": eps, "margin": 0.05, "predicted_nominal": pts, "runs": runs},
              open(os.path.join(HERE, f"{tag}.json"), "w"), indent=0)
    print(f"{tag}: {len(runs)} runs; eps {eps}")
    for l, s, n in pts: print(f"   {n:32s} L {l:7.1f} ms  S {s:.3f}")


if __name__ == "__main__":
    block("revHT", [960, 961, 962, 963, 964, 965], 120, 30, 2.0)
    block("revHR", [980, 981, 982, 983, 984, 985], 200, 60, 1.2)
