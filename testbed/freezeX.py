"""Experiment X: freeze the regime model from data already collected without writes or added
server work (calibW, RTT 50/250): display gaps (from modelW) and the no-write latency per
(mode, action, outcome) as a + b * client RTT. No experiment-X data is used."""
import hashlib, json, collections
from staleness import layer_cfg, outcomes

W = json.load(open("results/modelW.frozen.json"))
runs = [json.loads(l) for l in open("results/calibW-runs.jsonl")]
recs = collections.defaultdict(list)
for l in open("results/calibW.jsonl"):
    r = json.loads(l); recs[r["runId"]].append(r)
pts = collections.defaultdict(list)
for run in runs:
    rs = sorted(recs[run["runId"]], key=lambda r: (r["user"], r["step"]))
    oc = outcomes(run["users"], layer_cfg(run))
    crtt = (run["tcpPre"]["client_web"] + run["tcpPost"]["client_web"]) / 2
    for r, o in zip(rs, oc): pts[(run["mode"],) + o].append((crtt, r["latencyMs"] / 1000))
lat = {}
for key, xy in sorted(pts.items()):
    x, y = zip(*xy); n = len(y); mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x); b = sum((u - mx) * (v - my) for u, v in xy) / sxx if sxx > 1 else 0.0
    lat["|".join(key)] = {"a": my - b * mx, "b": b, "n": n}
    print(f"{'|'.join(key):22s} n={n:4d} latency = {1000*(my-b*mx):7.1f} ms + {b:6.3f} x RTT")
body = {"gap": W["gap"], "lat": lat, "modelW_sha": W["sha"]}
body["files"] = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in ("staleness.py", "modelX.py", "predict_runX.py", "evaluateX.py")}
body["sha"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
json.dump(body, open("results/modelX.frozen.json", "w"), indent=1)
print("frozen modelX", body["sha"], body["files"])
