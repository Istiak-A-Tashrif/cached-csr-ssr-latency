#!/usr/bin/env python3
"""Protocol v4 (chance-constrained selection, PROTOCOL_CC.md): run manifests, staleness limits and the
selector's per-candidate sampling sds, written once before any run and hashed into protocol/FROZEN_CC.json.
Seeds 1000-1020 (never used before). Candidate structure and limit placement as protocol v3
(make_manifests_hard.py), at new conditions: Zipf 0.7, TTLs 3/6/12 s, new RTT, server work and write rate.
sd_m and a come from results/revision/cc-derivation.json (derive_cc.py, development blocks only)."""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
from predict_runR2 import predict, sample_sessions
from selector_cc import block_sd

CANDS = [("ssr", "push", "push", None), ("ssr", False, False, None), ("csr", False, False, None), ("ssr", "ttl", "ttl", 3)]
for tau in (3, 6, 12):
    CANDS += [("ssr", False, "ttl", tau), ("ssr", "ttl", "push", tau), ("csr", "ttl", "push", tau), ("csr", False, "ttl", tau)]
ALPHA, PAGES, USERS, LEN, NSEEDS = 0.7, 8, 16, 12, 6
DER = json.load(open(os.path.join(HERE, "..", "results", "revision", "cc-derivation.json")))


def name(mode, fe, rp, tau):
    return f"{mode}-fe{fe or 'off'}-rd{rp or 'off'}" + (f"-tau{tau}" if tau else "") + f"-a{ALPHA}"


def nominal(rtt, d, lam):
    pts = []
    for mode, fe, rp, tau in CANDS:
        run = {"mode": mode, "fe": fe, "rp": rp, "S": tau or 3600, "T": tau or 3600, "pages": PAGES, "alpha": ALPHA,
               "proc": {"kind": "poisson", "lam": lam}, "dbDelayMs": d, "tcpPre": {"client_web": rtt + 1.2}}
        sess = [sample_sessions(USERS, LEN, PAGES, ALPHA, 31_337 * (k + 1)) for k in range(8)]
        s, l, _ = predict(run, sess)
        _, sd = block_sd(run, NSEEDS, USERS, LEN, reps=400, seed=7)
        pts.append((l, s, name(mode, fe, rp, tau), sd))
    eps = {}
    for setname, keep in (("all", lambda n: True), ("ttl_only", lambda n: "push" not in n)):
        sub = [p for p in pts if keep(p[2])]
        front = [p for p in sub if not any(q[0] <= p[0] and q[1] <= p[1] and q[:2] != p[:2] for q in sub)]
        eps[setname] = sorted({round(s + off, 3) for _, s, _, _ in front if 0.03 <= s <= 0.6 for off in (-0.01, 0.01)})
    return eps, sorted(pts)


def block(tag, seeds, rtt, d, lam):
    eps, pts = nominal(rtt, d, lam)
    runs = []
    for seed in seeds:
        for mode, fe, rp, tau in CANDS:
            runs.append({"seed": seed, "rtt": rtt, "mode": mode, "fe": fe, "rp": rp, "tau": tau or 3600, "alpha": ALPHA, "d": d,
                         "proc": {"kind": "poisson", "lam": lam}, "cellName": name(mode, fe, rp, tau)})
    random.Random(sum(map(ord, tag))).shuffle(runs)
    for i, r in enumerate(runs):
        r["runId"] = f"{tag}-s{r['seed']}-r{rtt}-{r['cellName']}"; r["wseed"] = r["seed"] * 101 + i
    man = {"tag": tag, "predictor": "predict_runR2.py", "eps": eps, "margin": 0.05, "cc": {"a": DER["a"], "z": DER["z"], "sd_m": DER["sd_m"],
           "sd_s": {n: sd for _, _, n, sd in pts}}, "predicted_nominal": [p[:3] for p in pts], "runs": runs}
    json.dump(man, open(os.path.join(HERE, f"{tag}.json"), "w"), indent=0)
    print(f"{tag}: {len(runs)} runs; eps {eps}")
    for l, s, n, sd in pts: print(f"   {n:32s} L {l:7.1f} ms  S {s:.3f}  sd_s {sd:.4f}")


if __name__ == "__main__":
    block("revCCdev", [1020], 140, 35, 1.8)                                  # pipeline check only, never scored
    block("revCCT", [1000, 1001, 1002, 1003, 1004, 1005], 160, 40, 1.6)
    block("revCCR", [1010, 1011, 1012, 1013, 1014, 1015], 90, 20, 2.4)
