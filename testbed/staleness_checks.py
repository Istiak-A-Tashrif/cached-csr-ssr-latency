#!/usr/bin/env python3
"""A5 checks (TWEB revision), retrospective, on the accepted staleness tests (W2, X):
(1) every view's snapshot holds the whole displayed table (rows read in one MutationObserver
callback at DOM insertion); (2) sensitivity of the oracle to a browser/database clock offset:
write commit times shifted by delta ms before comparing; (3) restoring writes: none possible,
every write is stock + 1 (api/server.js), so a changed value never returns to a shown one.
usage: python3 staleness_checks.py"""
import bisect, collections, json, os
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
W = collections.defaultdict(lambda: collections.defaultdict(list))
for w in map(json.loads, open(os.path.join(R, "writes.jsonl"))):
    W[w["runId"]][w["productId"]].append(w["committed"])
for d in W.values():
    for v in d.values(): v.sort()
out = {}
for tag in ("testW2", "repW2", "testX", "repX"):
    runs = {r["runId"]: r for r in map(json.loads, open(os.path.join(R, f"{tag}-runs.jsonl")))}
    views = [r for r in map(json.loads, open(os.path.join(R, f"{tag}.jsonl"))) if r.get("runId") in runs and "error" not in r]
    sizes = collections.Counter(len(r["rows"]) for r in views)
    res = {"views": len(views), "row_counts": dict(sizes)}
    for delta in (-20, -5, 0, 5, 20):
        st = ahead = 0
        for r in views:
            run = runs[r["runId"]]; s = False
            for pid, shown in r["rows"]:
                truth = run["stock0"][str(pid)] + bisect.bisect_right(W[r["runId"]][pid], r["wall"] - delta)
                s |= shown != truth; ahead += shown > truth
            st += s
        res[f"stale@{delta:+d}ms"] = round(st / len(views), 4); res[f"ahead@{delta:+d}ms"] = ahead
    out[tag] = res
    print(tag, res)
json.dump(out, open(os.path.join(R, "revision", "A5-staleness-checks.json"), "w"), indent=1)
