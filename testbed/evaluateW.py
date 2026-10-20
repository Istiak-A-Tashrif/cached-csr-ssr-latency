"""Item 8: score a writes test against the pre-registered criteria.

Oracle: a view is stale iff any displayed row's stock differs from the DB value at display
time, reconstructed as stock0 (read before the writer started) + writes to that product
committed at or before the display instant (writes.jsonl; each write adds 1).
  W1 pooled mean |observed - predicted| over cells <= 0.03
  W2 every cell |observed - predicted| <= 0.05
  W3 every cell pair with |predicted difference| >= 0.05 has an observed difference of the same sign
  W4 oracle integrity: no displayed value ahead of the DB; writes logged for every run;
     push purge lag p99 <= 20 ms
  W5 every prediction written before its run started, by the frozen model
usage: python3 evaluateW.py testW|repW
"""
import bisect, collections, json, sys

tag = sys.argv[1]
M = json.load(open("results/modelW.frozen.json"))
runs = {r["runId"]: r for r in map(json.loads, open(f"results/{tag}-runs.jsonl"))}
preds = {p["runId"]: p for p in map(json.loads, open("results/predictionsW.jsonl")) if p["runId"] in runs}
writes = collections.defaultdict(lambda: collections.defaultdict(list))   # runId -> pid -> [committed]
lags = []
for w in map(json.loads, open("results/writes.jsonl")):
    if w["runId"] in runs:
        writes[w["runId"]][w["productId"]].append(w["committed"])
        if w["purgedAt"] is not None: lags.append(w["purgedAt"] - w["committed"])

views = collections.defaultdict(list)
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

cell = lambda run: f"{run['mode']}-fe{run['fe'] or 'off'}-redis{run['rp'] or 'off'}"
agg = collections.defaultdict(lambda: [0, 0, 0.0])     # cell -> [views, stale, pred*views]
for rid, v in views.items():
    a = agg[cell(runs[rid])]
    a[0] += len(v); a[1] += sum(v); a[2] += preds[rid]["pred"] * len(v) if rid in preds else float("nan")

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
for k, (ok, d) in crit.items(): print(f"{'PASS' if ok else 'FAIL'}  {k}: {d}")
print("ACCEPTED" if all(ok for ok, _ in crit.values()) else "NOT ACCEPTED")
