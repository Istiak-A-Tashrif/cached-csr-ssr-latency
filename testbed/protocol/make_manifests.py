#!/usr/bin/env python3
"""Write the run manifests of the revision blocks (protocol/PROTOCOL.md). Run once, before any run;
the manifests are hashed into protocol/FROZEN.json. Seeds are from 800-999 only (never used before)."""
import json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from writeproc import trace_rate, trace_times

HERE = os.path.dirname(os.path.abspath(__file__))
TAUS = (1, 5, 20, 60)
ALPHAS = (0.6, 1.0)


def candidates():
    out = [("csr", False, False, None), ("ssr", False, False, None), ("ssr", "push", "push", None)]
    for tau in TAUS:
        out += [("csr", False, "ttl", tau), ("csr", "ttl", "push", tau), ("csr", "ttl", "ttl", tau),
                ("ssr", False, "ttl", tau), ("ssr", "ttl", "push", tau), ("ssr", "ttl", "ttl", tau)]
    return out   # 27 policies


def name(mode, fe, rp, tau, alpha, kind="poisson"):
    s = f"{mode}-fe{fe or 'off'}-rd{rp or 'off'}" + (f"-tau{tau}" if tau else "") + f"-a{alpha}"
    return s + ("" if kind == "poisson" else f"-{kind}")


def block(tag, seeds, rtt, d, procs, policies, alphas, pilot=False, trace_half=0, trace_window="test"):
    runs, k = [], 0
    for seed in seeds:
        for kind, proc in procs:
            for alpha in alphas:
                for mode, fe, rp, tau in policies:
                    runs.append({"seed": seed, "rtt": rtt, "mode": mode, "fe": fe, "rp": rp, "tau": tau or 3600,
                                 "alpha": alpha, "d": d, "proc": dict(proc), "cellName": name(mode, fe, rp, tau, alpha, kind)})
    random.Random(sum(map(ord, tag))).shuffle(runs)
    seg = 0
    for i, r in enumerate(runs):
        r["runId"] = f"{tag}-s{r['seed']}-r{rtt}-{r['cellName']}"
        r["wseed"] = r["seed"] * 101 + i
        if r["proc"]["kind"] == "trace":
            t, span = trace_times(trace_window, r["proc"]["compress"])
            start = span / 2 * trace_half + 40.0 * seg; seg += 1
            assert start + 40.0 <= span / 2 * (trace_half + 1), "trace segments exhausted"
            r["proc"]["times"] = [round(1000 * (x - start), 1) for x in t if start <= x < start + 40.0]
            r["proc"]["segment"] = [round(start, 1), round(start + 40.0, 1)]
    json.dump({"tag": tag, "pilot": pilot, "rtt": rtt, "d": d, "runs": runs}, open(os.path.join(HERE, f"{tag}.json"), "w"), indent=0)
    print(f"{tag}: {len(runs)} runs")


P = candidates()
B2P = [("csr", "ttl", "push", 5), ("ssr", False, "ttl", 5), ("ssr", "ttl", "ttl", 5), ("ssr", "push", "push", None)]
tr = trace_rate("train")
pois = lambda lam: [("poisson", {"kind": "poisson", "lam": lam})]
block("revDev", [800], 100, 25, [("poisson", {"kind": "poisson", "lam": 2.0}), ("periodic", {"kind": "periodic", "lam": 2.0}),
                                 ("onoff", {"kind": "onoff", "onRate": 8.0, "onMean": 2.0, "offMean": 6.0, "lam": 2.0}),
                                 ("trace", {"kind": "trace", "compress": 2.0 / tr, "lam": 2.0})],
      [("csr", "ttl", "ttl", 1), ("ssr", "ttl", "ttl", 5), ("ssr", "push", "push", None)], (0.6,), trace_window="train")
block("revPilotT", [830], 150, 50, pois(2.5), P, ALPHAS, pilot=True)
block("revT", [821, 822, 823, 824], 150, 50, pois(2.5), P, ALPHAS)
block("revPilotR", [850], 80, 15, pois(1.5), P, ALPHAS, pilot=True)
block("revR", [841, 842, 843, 844], 80, 15, pois(1.5), P, ALPHAS)
block("revB2T", [861, 862, 863, 864], 150, 50,
      [("periodic", {"kind": "periodic", "lam": 2.5}), ("onoff", {"kind": "onoff", "onRate": 10.0, "onMean": 2.0, "offMean": 6.0, "lam": 2.5}),
       ("trace", {"kind": "trace", "compress": 2.5 / tr, "lam": 2.5})], B2P, (0.6,), trace_half=0)
block("revB2R", [871, 872, 873, 874], 80, 15,
      [("periodic", {"kind": "periodic", "lam": 1.5}), ("onoff", {"kind": "onoff", "onRate": 6.0, "onMean": 2.0, "offMean": 6.0, "lam": 1.5}),
       ("trace", {"kind": "trace", "compress": 1.5 / tr, "lam": 1.5})], B2P, (0.6,), trace_half=1)
