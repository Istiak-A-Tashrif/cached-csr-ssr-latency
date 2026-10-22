#!/usr/bin/env python3
"""Score a prospective test against its per-run predictions and the pre-registered
acceptance criteria (RESEARCH_PLAN.md, decision log, 19 Oct 2026).

usage: python3 evaluate_n.py <tag>      e.g. prosp4  (reads <tag>.jsonl, <tag>-runs.jsonl,
                                                       predictions<N>.jsonl where N = tag digits)
"""
import json, random, re, sys
from collections import defaultdict
from lib import jl, load, mean

tag = sys.argv[1]
n = re.sub(r"\D", "", tag)
acts, runs, errors, unc = load(f"{tag}.jsonl", f"{tag}-runs.jsonl")
pred_file = sys.argv[2] if len(sys.argv) > 2 else f"predictions{n}.jsonl"
preds = {p["runId"]: p for p in jl(pred_file)}  # one line per run (discards removed)

def boot(xs, it=4000, seed=1):
    r = random.Random(seed); k = len(xs)
    ms = sorted(mean(xs[r.randrange(k)] for _ in range(k)) for _ in range(it))
    return ms[int(.025 * it)], ms[int(.975 * it)]

# A rerun keeps its runId; log entries from the discarded attempt (before the
# logged discard time) are ignored so they cannot be mistaken for the run start.
import datetime as _dt
import os as _os
# The discard log sits next to the server logs (an archived subdirectory has its own).
discarded = {d["runId"]: _dt.datetime.fromisoformat(d["at"].replace("Z", "+00:00")).timestamp()
             for d in jl(_os.path.join(_os.environ.get("SERVER_LOGS", ""), "discarded-runs.jsonl"))}
first_ts = defaultdict(lambda: float("inf"))
for x in jl(_os.path.join(_os.environ.get("SERVER_LOGS", ""), "api.jsonl")):
    r = x.get("runId")
    if r in runs and x["ts"] / 1000 > discarded.get(r, 0):
        first_ts[r] = min(first_ts[r], x["ts"] / 1000)
late = [r for r in runs if r not in preds or preds[r]["writtenAt"] >= first_ts[r]]
pmap = {(r, x["user"], x["step"]): x for r, p in preds.items() for x in p["preds"]}
agree = sum(pmap[(a["runId"], a["user"], a["step"])]["o"] == a["o"] for a in acts if (a["runId"], a["user"], a["step"]) in pmap)

cells = defaultdict(lambda: defaultdict(lambda: {"obs": [], "pred": []}))
for a in acts:
    c = cells[(a["mode"], a["fe"], a["rtt"], a["irtt"], a["action"])][a["seed"]]
    c["obs"].append(a["latencyMs"]); c["pred"].append(pmap[(a["runId"], a["user"], a["step"])]["pred"])

print(f"{tag}: runs={len(runs)} actions={len(acts)} errors={len(errors)} unclassified={len(unc)}")
rows, fails_cell = [], []
for k in sorted(cells):
    s = cells[k]
    obs = mean(mean(v["obs"]) for v in s.values()); pred = mean(mean(v["pred"]) for v in s.values())
    lo, hi = boot([mean(v["obs"]) for v in s.values()])
    tol = max(0.05 * obs, 10.0); ok = abs(pred - obs) <= tol
    rows.append(abs(pred - obs) / obs)
    if not ok: fails_cell.append(k)
    print(f"  {k[4]:7} {k[0]} caches={'on ' if k[1] else 'off'} crtt={k[2]:3} irtt={k[3]:3}: obs {obs:7.1f} [{lo:7.1f},{hi:7.1f}] pred {pred:7.1f} ({100 * (pred - obs) / obs:+5.1f}%){'' if ok else '  <-- FAIL'}")

fails_diff = []
print("  SSR - CSR differences:")
for crtt in sorted({k[2] for k in cells}):
    for irtt in sorted({k[3] for k in cells}):
        for fe in (False, True):
            for act in ("initial", "nav"):
                c, s = cells.get(("csr", fe, crtt, irtt, act)), cells.get(("ssr", fe, crtt, irtt, act))
                if not c or not s: continue
                ks = [x for x in c if x in s]
                d_obs = mean(mean(s[x]["obs"]) - mean(c[x]["obs"]) for x in ks)
                d_pred = mean(mean(s[x]["pred"]) - mean(c[x]["pred"]) for x in ks)
                tol = max(10.0, 0.10 * abs(d_obs))
                sign_ok = (d_obs > 0) == (d_pred > 0) or abs(d_obs) < 10
                ok = sign_ok and abs(d_pred - d_obs) <= tol
                if not ok: fails_diff.append((act, crtt, irtt, fe))
                print(f"    {act:7} crtt={crtt:3} irtt={irtt:3} caches={'on ' if fe else 'off'}: obs {d_obs:8.1f} pred {d_pred:8.1f}{'' if ok else '  <-- FAIL'}")

crit = {
    "C1 mean rel error <= 3%": mean(rows) <= 0.03,
    "C2 every cell within max(5%, 10 ms)": not fails_cell,
    "C3 every SSR-CSR difference correct sign, within max(10 ms, 10%)": not fails_diff,
    "C4 analytic outcomes 100%": agree == len(acts),
    "C5 all predictions written before run start": not late and len(runs) > 0,
}
print(f"\n  mean rel error {100 * mean(rows):.2f}%  max {100 * max(rows):.2f}%  outcomes {agree}/{len(acts)}  late predictions {len(late)}")
for k, v in crit.items(): print(f"  {'PASS' if v else 'FAIL'}  {k}")
print("ACCEPTED" if all(crit.values()) else "NOT ACCEPTED")
