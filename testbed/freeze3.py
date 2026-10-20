#!/usr/bin/env python3
"""Freeze model v3 = model2.py (unchanged equations) + calib3 parameters.
v3 differs from v2 only in inputs/procedure: TCP-measured per-run link RTTs
(pre-run), warm-up after cold start, calibration under the same procedure."""
import hashlib, json, os, time
from lib import R, load, mean
from model2 import calibrate_bytes, calibrate_T0

here = os.path.dirname(os.path.abspath(__file__))
calib, runs, err, unc = load("calib3.jsonl", "calib3-runs.jsonl")
assert not err and not unc, (len(err), len(unc))
links = ("client_web", "client_api", "web_api")
tcp0 = {l: mean([(r["tcpPre"][l] + r["tcpPost"][l]) / 2 for r in runs.values()]) for l in links}
frozen = {
    "frozenAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "model2_sha256": hashlib.sha256(open(os.path.join(here, "model2.py"), "rb").read()).hexdigest(),
    "bytes": calibrate_bytes(calib),
    "T0": {"|".join(k): v for k, v in calibrate_T0(calib).items()},
    "tcp0": tcp0,  # probe reading at RTT 0 (instrument + base RTT), subtracted from run readings
}
blob = json.dumps(frozen, indent=1, sort_keys=True)
open(os.path.join(R, "model3.frozen.json"), "w").write(blob)
print("frozen model3; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "tcp0", {k: round(v, 2) for k, v in tcp0.items()})
print("T0:", {k: round(v, 1) for k, v in frozen["T0"].items()})
