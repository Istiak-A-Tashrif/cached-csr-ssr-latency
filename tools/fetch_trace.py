#!/usr/bin/env python3
"""Fetch the public write-timing trace for the B2 staleness test (TWEB revision).

Source: German Wikipedia recent changes (edits and page creations, bots included), fixed historical
window 2026-10-14T08:00:00Z to 14:00:00Z (recent changes are retained for 30 days), via the MediaWiki API (rcprop=timestamp|ids). Only the
timestamps (1 s resolution) and revision ids are kept. The trace supplies write TIMING only; which
catalogue product a write updates is drawn by the testbed, so the combination is a trace-inspired
synthetic workload, not a production workload of this application.
Split (chronological): hours 1-3 = training window (the predictor may read it), hours 4-6 = test window
(replayed by the writer; never read by the predictor).
usage: python3 tools/fetch_trace.py   -> testbed/traces/dewiki-rc-20261014.json (+ sha256 printed)
"""
import hashlib, json, os, time, urllib.parse, urllib.request

API = "https://de.wikipedia.org/w/api.php"
START, END = "2026-10-14T08:00:00Z", "2026-10-14T14:00:00Z"
UA = "caching-research-trace/1.0 (academic; contact istiaktashrif@gmail.com)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "testbed", "traces", "dewiki-rc-20261014.json")

rows, cont = [], {}
while True:
    q = {"action": "query", "list": "recentchanges", "rcstart": START, "rcend": END, "rcdir": "newer",
         "rctype": "edit|new", "rcprop": "timestamp|ids", "rclimit": "500", "format": "json", **cont}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    rows += [{"ts": r["timestamp"], "revid": r.get("revid")} for r in d["query"]["recentchanges"]]
    if "continue" not in d: break
    cont = d["continue"]; time.sleep(0.5)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
blob = json.dumps({"source": API, "window": [START, END], "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "license": "Wikimedia API metadata (timestamps, revision ids); CC0/public metadata", "events": rows}, indent=0)
open(OUT, "w").write(blob)
print(f"{len(rows)} events -> {OUT}\nsha256 {hashlib.sha256(blob.encode()).hexdigest()}")
