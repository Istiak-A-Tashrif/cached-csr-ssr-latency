#!/usr/bin/env python3
"""Freeze model R2 (protocol v3): model R's frozen calibration and O2 reference, unchanged; new code hashes."""
import hashlib, json
R = json.load(open("results/modelR.frozen.json"))
body = {k: R[k] for k in ("gap", "lat", "modelX_sha", "outcome_reference", "trace_sha256")}
body["files"] = {f: hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
                 for f in ("staleness.py", "modelR2.py", "writeproc.py", "predict_runR2.py", "evaluateR2.py")}
body["sha"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
json.dump(body, open("results/modelR2.frozen.json", "w"), indent=1)
print("frozen modelR2", body["sha"], body["files"])
