#!/usr/bin/env python3
"""Run manifests of the Conduit blocks (protocol/PROTOCOL_CONDUIT.md), written once before any Conduit
run and hashed into protocol/FROZEN_CONDUIT.json. Seeds 900-999 (never used before)."""
import json, os, random, sys

# Same 27 candidate policies and cell names as protocol/make_manifests.py (copied, not imported: importing
# that script would rerun it and rewrite the frozen catalogue manifests).
TAUS = (1, 5, 20, 60)


def candidates():
    out = [("csr", False, False, None), ("ssr", False, False, None), ("ssr", "push", "push", None)]
    for tau in TAUS:
        out += [("csr", False, "ttl", tau), ("csr", "ttl", "push", tau), ("csr", "ttl", "ttl", tau),
                ("ssr", False, "ttl", tau), ("ssr", "ttl", "push", tau), ("ssr", "ttl", "ttl", tau)]
    return out


def name(mode, fe, rp, tau, alpha, kind="poisson"):
    s = f"{mode}-fe{fe or 'off'}-rd{rp or 'off'}" + (f"-tau{tau}" if tau else "") + f"-a{alpha}"
    return s + ("" if kind == "poisson" else f"-{kind}")

HERE = os.path.dirname(os.path.abspath(__file__))
POP = json.load(open(os.path.join(HERE, "..", "traces", "dewiki-top-20261013.json")))["articles"]
W = [a["views"] for a in POP]
CAL = [("csr", "ttl", "ttl", 3), ("csr", "ttl", "push", 3), ("csr", False, "ttl", 3), ("csr", False, False, None),
       ("ssr", "ttl", "ttl", 3), ("ssr", "ttl", "push", 3), ("ssr", "push", "push", None), ("ssr", False, "ttl", 3), ("ssr", False, False, None)]


def block(tag, seeds, rtts, lam, policies, pilot=False, calibration=False):
    runs = []
    for seed in seeds:
        for rtt in rtts:
            for mode, fe, rp, tau in policies:
                runs.append({"seed": seed, "rtt": rtt, "mode": mode, "fe": fe, "rp": rp, "tau": tau or 3600, "alpha": "pop", "d": 0,
                             "proc": {"kind": "poisson", "lam": lam} if lam else {}, "cellName": name(mode, fe, rp, tau, "pop")})
    random.Random(sum(map(ord, tag))).shuffle(runs)
    for i, r in enumerate(runs):
        r["runId"] = f"{tag}-s{r['seed']}-r{r['rtt']}-{r['cellName']}"
        r["wseed"] = r["seed"] * 101 + i
    json.dump({"tag": tag, "app": "conduit", "pages": len(W), "limit": 1, "weights": W, "pilot": pilot, "calibration": calibration,
               "runs": runs}, open(os.path.join(HERE, f"{tag}.json"), "w"), indent=0)
    print(f"{tag}: {len(runs)} runs")


P = candidates()
block("cdDev", [900], [100], 2.0, [CAL[0], CAL[5], CAL[6], CAL[8]])
block("cdCal", [901, 902], [50, 250], 0, CAL, calibration=True)
block("cdPilotT", [910], [150], 2.5, P, pilot=True)
block("cdT", [911, 912, 913, 914], [150], 2.5, P)
block("cdPilotR", [920], [80], 1.5, P, pilot=True)
block("cdR", [921, 922, 923, 924], [80], 1.5, P)
# Different host (Linux, pinned cores): recalibrated there, then a test and a replication.
block("cdCalH", [931, 932], [50, 250], 0, CAL, calibration=True)
block("cdHT", [941, 942, 943, 944], [120], 2.0, P)
block("cdHR", [951, 952, 953, 954], [60], 1.2, P)
