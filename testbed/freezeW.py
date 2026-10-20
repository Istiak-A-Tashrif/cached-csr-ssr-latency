"""Item 8: freeze the display-gap timeline from calibW (no writes).
gap(mode, action, outcome) = a + b * client RTT (ms), least squares over every view after a
run's first; outcome classes are timing-independent (staleness.outcomes)."""
import hashlib, json, collections
from staleness import layer_cfg, outcomes

runs = [json.loads(l) for l in open("results/calibW-runs.jsonl")]
recs = collections.defaultdict(list)
for l in open("results/calibW.jsonl"):
    r = json.loads(l)
    if "error" in r: raise SystemExit(f"error record in calibration: {r}")
    recs[r["runId"]].append(r)

pts = collections.defaultdict(list)
for run in runs:
    rs = sorted(recs[run["runId"]], key=lambda r: (r["user"], r["step"]))
    oc = outcomes(run["users"], layer_cfg(run))
    assert len(rs) == len(oc) == sum(map(len, run["users"])), run["runId"]
    crtt = (run["tcpPre"]["client_web"] + run["tcpPost"]["client_web"]) / 2
    for k in range(1, len(rs)):
        pts[(run["mode"],) + oc[k]].append((crtt, (rs[k]["wall"] - rs[k - 1]["wall"]) / 1000))

fit = {}
for key, xy in sorted(pts.items()):
    x, y = zip(*xy); n = len(y); mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((u - mx) * (v - my) for u, v in xy) / sxx if sxx > 1 else 0.0
    a = my - b * mx
    sd = (sum((v - a - b * u) ** 2 for u, v in xy) / n) ** 0.5
    fit["|".join(key)] = {"a": a, "b": b, "n": n, "sd": sd}
    print(f"{'|'.join(key):22s} n={n:4d} gap = {a*1000:7.1f} ms + {b:6.3f} x RTT  (resid sd {sd*1000:.0f} ms)")

body = {"gap": fit}
sha = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
body["sha"] = sha
for f in ["staleness.py", "predict_runW.py", "evaluateW.py"]:
    body.setdefault("files", {})[f] = hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
json.dump(body, open("results/modelW.frozen.json", "w"), indent=1)
print("frozen modelW", sha, body["files"])
