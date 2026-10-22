#!/usr/bin/env python3
"""Freeze model RC (Conduit, B5) from the Conduit calibration block cdCal only (no writes, no test data):
display gaps (freezeW.py's fit) and no-write latency per (mode, action, outcome) as a + b * client RTT
(freezeX.py's fit), the article write/access probabilities from the popularity source, the outcome-
frequency reference for O2 (class frequencies per policy, action and revisit flag in cdCal), and the
hashes of the code that predicts and scores.
usage: python3 freezeRC.py [calibration tag]   (cdCal on the Mac, cdCalH on the second host)"""
import collections, hashlib, json, os, sys
from staleness import layer_cfg, outcomes

TAG = sys.argv[1] if len(sys.argv) > 1 else "cdCal"
runs = [json.loads(l) for l in open(f"results/{TAG}-runs.jsonl")]
recs = collections.defaultdict(list)
for l in open(f"results/{TAG}.jsonl"):
    r = json.loads(l)
    if "error" in r: raise SystemExit(f"error record in calibration: {r}")
    recs[r["runId"]].append(r)
gp, lp = collections.defaultdict(list), collections.defaultdict(list)
for run in runs:
    rs = sorted(recs[run["runId"]], key=lambda r: (r["user"], r["step"]))
    oc = outcomes(run["users"], layer_cfg(run))
    assert len(rs) == len(oc) == sum(map(len, run["users"])), run["runId"]
    c_gap = (run["tcpPre"]["client_web"] + run["tcpPost"]["client_web"]) / 2
    for k in range(len(rs)):
        lp[(run["mode"],) + oc[k]].append((c_gap, rs[k]["latencyMs"] / 1000))
        if k: gp[(run["mode"],) + oc[k]].append((c_gap, (rs[k]["wall"] - rs[k - 1]["wall"]) / 1000))


def lin(pts):
    out = {}
    for key, xy in sorted(pts.items()):
        x, y = zip(*xy); n = len(y); mx, my = sum(x) / n, sum(y) / n
        sxx = sum((v - mx) ** 2 for v in x); b = sum((u - mx) * (v - my) for u, v in xy) / sxx if sxx > 1 else 0.0
        out["|".join(key)] = {"a": my - b * mx, "b": b, "n": n}
    return out


pop = json.load(open("traces/dewiki-top-20261013.json"))["articles"]
tot = sum(a["views"] for a in pop)
probs = {str(i + 1): a["views"] / tot for i, a in enumerate(pop)}
# O2 reference from cdCal, classified with the evaluator's displayed-response rule.
body = {"calibration": TAG, "gap": lin(gp), "lat": lin(lp), "page_probs": probs,
        "popularity_sha256": hashlib.sha256(open("traces/dewiki-top-20261013.json", "rb").read()).hexdigest()}
cnt = collections.defaultdict(collections.Counter)
api_rid, api_resp = {}, {}
rids = {r["runId"] for r in runs}
for l in open("results/api.jsonl"):
    x = json.loads(l)
    if x.get("runId") in rids:
        if x.get("reqId"): api_rid[x["reqId"]] = x
        if x.get("respId"): api_resp[x["respId"]] = x
for run in runs:
    cl = f"{run['mode']}-fe{run['fe'] or 'off'}-rd{run['rp'] or 'off'}"
    for v in recs[run["runId"]]:
        if v["mode"] == "csr":
            x = None if not v["tqRids"] else api_rid.get(v["tqRids"][-1]); y = "tq_hit" if not v["tqRids"] else None
        else:
            x = api_resp.get(v.get("resp")); y = "next_hit" if x is not None and x["ts"] < v["wall"] - v["domMs"] else None
        if y is None and x is not None: y = "redis_hit" if x["redis"] == "hit" else "db"
        if y: cnt[f"{cl}|{v['action']}|{v['revisit']}"][y] += 1
body["outcome_reference"] = {k: {o: c[o] / sum(c.values()) for o in ("tq_hit", "next_hit", "redis_hit", "db")} for k, c in cnt.items()}
body["files"] = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
                 for f in ("staleness.py", "modelR.py", "modelRC.py", "writeproc.py", "predict_runRC.py", "evaluateRC.py")}
body["sha"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
json.dump(body, open("results/modelRC.frozen.json", "w"), indent=1)
print("frozen modelRC", body["sha"], body["files"], len(body["lat"]), "latency fits,", len(body["gap"]), "gap fits")
