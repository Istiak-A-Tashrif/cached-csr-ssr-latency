#!/usr/bin/env python3
"""Freeze revision model R (TWEB revision): modelX's calibration (display gaps, no-write latency per
outcome; from calibW only) plus the code of the write processes, and the outcome-frequency reference
for criterion O2 (class frequencies per policy, action and revisit flag in calibW, classified as in
b1_offline.py). No revision-test data exists when this runs."""
import collections, hashlib, json, os
X = json.load(open("results/modelX.frozen.json"))
src = open("b1_offline.py").read().split("summary = {}")[0]
g = {"__file__": os.path.abspath("b1_offline.py"), "__name__": "b1"}; exec(compile(src, "b1_offline.py", "exec"), g)
ref = {}
for k, c in g["freq"].items():
    (cl, action, revisit), n = k, sum(c.values())
    cl = cl.replace("-rd", "-rd")
    ref[f"{cl}|{action}|{revisit}"] = {o: c[o] / n for o in g["CLS"]}
body = {"gap": X["gap"], "lat": X["lat"], "modelX_sha": X["sha"], "outcome_reference": ref,
        "trace_sha256": hashlib.sha256(open("traces/dewiki-rc-20261014.json", "rb").read()).hexdigest()}
body["files"] = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
                 for f in ("staleness.py", "modelR.py", "writeproc.py", "predict_runR.py", "evaluateR.py")}
body["sha"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
json.dump(body, open("results/modelR.frozen.json", "w"), indent=1)
print("frozen modelR", body["sha"], body["files"], f"{len(ref)} reference cells")
