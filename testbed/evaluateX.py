"""Experiment X (server-work regime): staleness criteria W1-W5 (as item 8) plus latency
criteria L1-L3 against per-view predictions written before each run.

Oracle: a view is stale iff any displayed row's stock differs from the DB value at display
time, reconstructed as stock0 (read before the writer started) + writes to that product
committed at or before the display instant (writes.jsonl; each write adds 1).
  W1 pooled mean |observed - predicted| over cells <= 0.03
  W2 every cell |observed - predicted| <= 0.05
  W3 every cell pair with |predicted difference| >= 0.05 has an observed difference of the same sign
  W4 oracle integrity: no displayed value ahead of the DB; writes logged for every run;
     push purge lag p99 <= 20 ms
  W5 every prediction written before its run started, by the frozen model
  L1 mean relative latency error over (cell, action) <= 3%
  L2 every (cell, action) within max(5%, 10 ms)
  L3 each server-cache cell's navigation saving vs its mode's no-cache cell: observed sign
     (where |observed| >= 10 ms) and within max(10 ms, 10%)
usage: python3 evaluateX.py testX|repX
"""
import bisect, collections, json, sys

tag = sys.argv[1]
M = json.load(open("results/modelX.frozen.json"))
runs = {r["runId"]: r for r in map(json.loads, open(f"results/{tag}-runs.jsonl"))}
preds = {p["runId"]: p for p in map(json.loads, open("results/predictionsX.jsonl")) if p["runId"] in runs}
writes = collections.defaultdict(lambda: collections.defaultdict(list))   # runId -> pid -> [committed]
lags = []
for w in map(json.loads, open("results/writes.jsonl")):
    if w["runId"] in runs:
        writes[w["runId"]][w["productId"]].append(w["committed"])
        if w["purgedAt"] is not None: lags.append(w["purgedAt"] - w["committed"])

views = collections.defaultdict(list)
latc = collections.defaultdict(lambda: [[], []])     # (cell, action) -> [observed ms], [predicted ms]
ahead = errors = 0
for r in map(json.loads, open(f"results/{tag}.jsonl")):
    if r.get("runId") not in runs: continue
    if "error" in r: errors += 1; continue
    run = runs[r["runId"]]
    stale = False
    for pid, shown in r["rows"]:
        ts = writes[r["runId"]][pid]
        truth = run["stock0"][str(pid)] + bisect.bisect_right(sorted(ts), r["wall"])
        if shown > truth: ahead += 1
        stale |= shown != truth
    views[r["runId"]].append(stale)
    pl = {(x["user"], x["step"]): x["ms"] for x in preds[r["runId"]]["lat"]} if r["runId"] in preds else {}
    c = f"{run['mode']}-fe{run['fe'] or 'off'}-redis{run['rp'] or 'off'}"
    if (r["user"], r["step"]) in pl:
        latc[(c, r["action"])][0].append(r["latencyMs"]); latc[(c, r["action"])][1].append(pl[(r["user"], r["step"])])

cell = lambda run: f"{run['mode']}-fe{run['fe'] or 'off'}-redis{run['rp'] or 'off'}"
agg = collections.defaultdict(lambda: [0, 0, 0.0])     # cell -> [views, stale, pred*views]
for rid, v in views.items():
    a = agg[cell(runs[rid])]
    a[0] += len(v); a[1] += sum(v); a[2] += preds[rid]["stale"] * len(v) if rid in preds else float("nan")

print(f"{tag}: {len(runs)} runs, {sum(a[0] for a in agg.values())} views, {errors} errors, "
      f"{sum(len(x) for d in writes.values() for x in d.values())} writes")
print(f"{'cell':28s} {'views':>5s} {'observed':>9s} {'predicted':>9s} {'diff':>7s}")
res = {}
for c in sorted(agg):
    n, s, pv = agg[c]
    res[c] = (s / n, pv / n)
    print(f"{c:28s} {n:5d} {s/n:9.3f} {pv/n:9.3f} {s/n - pv/n:+7.3f}")

errs = [abs(o - p) for o, p in res.values()]
w1 = sum(errs) / len(errs)
pairs = [(a, b) for a in res for b in res if a < b and abs(res[a][1] - res[b][1]) >= 0.05]
bad = [(a, b) for a, b in pairs if (res[a][0] - res[b][0]) * (res[a][1] - res[b][1]) <= 0]
lags.sort()
p99 = lags[int(0.99 * (len(lags) - 1))] if lags else None
missing_w = [rid for rid in runs if runs[rid]["lam"] and not writes[rid]]
late = [rid for rid in runs if rid not in preds or preds[rid]["ts"] >= runs[rid]["t0"] or preds[rid]["sha"] != M["sha"]]
crit = {
    "W1 pooled MAE <= 0.03": (w1 <= 0.03, f"{w1:.4f}"),
    "W2 every cell within 0.05": (max(errs) <= 0.05, f"max {max(errs):.4f}"),
    "W3 orderings": (not bad, f"{len(pairs) - len(bad)}/{len(pairs)} pairs" + (f" wrong: {bad}" if bad else "")),
    "W4 oracle integrity": (ahead == 0 and not missing_w and errors == 0 and (p99 is None or p99 <= 20),
                            f"ahead {ahead}, runs without writes {len(missing_w)}, errors {errors}, purge lag p99 {p99} ms"),
    "W5 predictions before runs": (not late, f"{len(runs) - len(late)}/{len(runs)}"),
}
mn = lambda v: sum(v) / len(v)
print(f"\n{'latency cell':36s} {'obs ms':>8s} {'pred ms':>8s} {'err':>7s}")
lerr, lbad = [], []
for k in sorted(latc):
    o, p = mn(latc[k][0]), mn(latc[k][1]); e = (p - o) / o; lerr.append(abs(e))
    ok = abs(p - o) <= max(0.05 * o, 10.0)
    if not ok: lbad.append(k)
    print(f"{k[0] + ' ' + k[1]:36s} {o:8.1f} {p:8.1f} {100*e:+6.1f}%{'' if ok else '  <-- FAIL'}")
sav_bad, sav_n = [], 0
for mode in ("csr", "ssr"):
    base = latc.get((f"{mode}-feoff-redisoff", "nav"))
    if not base: continue
    for (c, act), (o, p) in latc.items():
        if act != "nav" or not c.startswith(mode) or c == f"{mode}-feoff-redisoff": continue
        so, sp = mn(base[0]) - mn(o), mn(base[1]) - mn(p); sav_n += 1
        ok = abs(sp - so) <= max(10.0, 0.10 * abs(so)) and (abs(so) < 10 or (so > 0) == (sp > 0))
        print(f"  saving vs no-cache, {c:28s} observed {so:7.1f} ms predicted {sp:7.1f} ms{'' if ok else '  <-- FAIL'}")
        if not ok: sav_bad.append(c)
crit["L1 mean latency error <= 3%"] = (mn(lerr) <= 0.03, f"{100*mn(lerr):.2f}%")
crit["L2 every latency cell within max(5%, 10 ms)"] = (not lbad, f"max {100*max(lerr):.2f}%")
crit["L3 server-cache savings"] = (not sav_bad, f"{sav_n - len(sav_bad)}/{sav_n}")
for k, (ok, d) in crit.items(): print(f"{'PASS' if ok else 'FAIL'}  {k}: {d}")
print("ACCEPTED" if all(ok for ok, _ in crit.values()) else "NOT ACCEPTED")
