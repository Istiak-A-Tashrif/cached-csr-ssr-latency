#!/usr/bin/env python3
"""Fetch the access-popularity source for the Conduit workload (TWEB revision, B5): German Wikipedia's
most viewed articles on 13 Oct 2026 (Wikimedia REST pageviews API, all-access). Main page, special and
other namespace pages are dropped; the top 50 articles give the Conduit articles' titles and their
relative popularity (sessions draw article pages with probability proportional to views; writes target
articles with the same probabilities). Popularity of a different site mapped onto Conduit articles:
a trace-inspired synthetic workload.
usage: python3 tools/fetch_popularity.py -> testbed/traces/dewiki-top-20261013.json (+ sha256)"""
import hashlib, json, os, urllib.request
URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/de.wikipedia/all-access/2026/10/13"
UA = "caching-research-trace/1.0 (academic; contact istiaktashrif@gmail.com)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "testbed", "traces", "dewiki-top-20261013.json")
d = json.load(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": UA}), timeout=60))
arts = d["items"][0]["articles"]
keep = [a for a in arts if ":" not in a["article"] and a["article"] not in ("Wikipedia:Hauptseite", "Hauptseite", "-")][:50]
blob = json.dumps({"source": URL, "articles": [{"title": a["article"].replace("_", " "), "views": a["views"]} for a in keep]}, indent=0, ensure_ascii=False)
open(OUT, "w").write(blob)
print(len(keep), "articles; top views", keep[0]["views"], "50th", keep[-1]["views"], "sha256", hashlib.sha256(blob.encode()).hexdigest())
