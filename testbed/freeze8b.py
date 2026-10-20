#!/usr/bin/env python3
"""Freeze model v8b: the v8 frozen parameters + the SSR-navigation transfer offset,
pooled from all completed real-path tests (used conditions only)."""
import hashlib, json, os, time
from lib import R, load, mean
from model8 import predict

here = os.path.dirname(os.path.abspath(__file__))
sha = lambda f: hashlib.sha256(open(os.path.join(here, f), "rb").read()).hexdigest()
F = json.load(open(f"{R}/model8.frozen.json")); t0 = F["tcp0"]
resid = []
for tag in ("real6", "rep6", "real7", "rep7", "real8", "rep8"):
    acts, runs, _, _ = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
    for a in acts:
        if a["mode"] != "ssr" or a["action"] != "nav": continue
        r = runs[a["runId"]]; p = r["tcpPre"]
        c = (p["client_web"] - t0["client_web"] + p["client_api"] - t0["client_api"]) / 2
        race = r.get("raceP") if r.get("raceP") is not None else F["cap"]["p_netem"]
        resid.append(a["latencyMs"] - predict(a["mode"], a["action"], a["o"], c, 0, F, r.get("bwBps") or 10e6, race))
G = dict(F)
G.update(frozenAt=time.strftime("%Y-%m-%dT%H:%M:%S"), transfer={"ssr|nav": mean(resid)}, transferN=len(resid),
         model8b_sha256=sha("model8b.py"))
blob = json.dumps(G, indent=1, sort_keys=True)
open(os.path.join(R, "model8b.frozen.json"), "w").write(blob)
print("frozen model8b; sha256", hashlib.sha256(blob.encode()).hexdigest()[:16], "transfer", {k: round(v, 2) for k, v in G["transfer"].items()}, "n", len(resid))
