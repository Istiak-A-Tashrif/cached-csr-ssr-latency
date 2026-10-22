#!/usr/bin/env python3
"""Harness changes for the Conduit blocks (TWEB revision B5), applied AFTER the catalogue blocks so the
frozen catalogue harness (protocol/FROZEN.json) is the one those blocks ran with. Every change is
guarded by APP=conduit or by manifest fields the catalogue manifests do not have; the catalogue
code paths are unchanged.
  1. makeWorkload: optional page weights (popularity) instead of Zipf alpha.
  2. warmup: Conduit warm-up article (page 199) through both rendering paths and the API.
  3. rev blocks: manifest-level pages, limit, weights and app; Conduit runs reset favourites to the
     seeded baseline before the stock snapshot; predictions by predict_runRC.py (and the
     zero-recalibration prediction, descriptive) when the manifest says app = conduit.
usage: python3 protocol/apply_conduit_harness.py"""
import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness.mjs")
s = open(P).read()


def sub(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


sub('''export function makeWorkload({ users, sessionLen, pages, alpha, seed }) {
  const rand = rng(seed);
  const draw = zipfSampler(pages, alpha, rand);''',
    '''export function makeWorkload({ users, sessionLen, pages, alpha, seed, weights }) {
  const rand = rng(seed);
  const draw = weights ? weightedSampler(weights, rand) : zipfSampler(pages, alpha, rand);''')
sub('''// Pages are drawn per step; consecutive duplicates are redrawn''',
    '''// TWEB revision B5 (Conduit): pages drawn with given weights (article popularity).
function weightedSampler(w, rand) {
  const cdf = []; let acc = 0;
  for (const x of w) cdf.push((acc += x));
  return () => { const r = rand() * acc; return cdf.findIndex((c) => c >= r) + 1; };
}
// Pages are drawn per step; consecutive duplicates are redrawn''')
sub('''function warmup() {
  exec(''', '''function warmup() {
  if (process.env.APP === "conduit") {
    exec("client", `sh -c "${NODE_TLS}node -e \\\\"Promise.all([fetch('${BASE_WEB}/ssr?page=${WARMUP_PAGE}&limit=1&a=warmup'),fetch('${BASE_WEB}/csr?page=${WARMUP_PAGE}&limit=1'),fetch('${BASE_API}/api/articles/a${WARMUP_PAGE}?caller=warmup')]).then(rs=>Promise.all(rs.map(r=>r.text())))\\\\""`);
    return;
  }
  exec(''')
sub('''  const pages = 8;
  const done = new Set(''', '''  const pages = man.pages ?? 8, limit = man.limit ?? 25;
  const conduit = man.app === "conduit";
  if (conduit !== (process.env.APP === "conduit")) throw new Error("set APP=conduit exactly for Conduit manifests");
  const done = new Set(''')
sub('''    const users = makeWorkload({ users: 16, sessionLen: 12, pages, alpha: c.alpha, seed: c.seed * 1000 + 7 });''',
    '''    const users = makeWorkload({ users: 16, sessionLen: 12, pages, alpha: c.alpha, seed: c.seed * 1000 + 7, weights: man.weights });''')
sub('''      try { sh(`python3 predict_runR.py ${f}`); } finally { fs.rmSync(f, { force: true }); }''',
    '''      try {
        if (conduit) { if (!man.calibration) { sh(`python3 predict_runRC.py ${f}`); sh(`python3 predict_runRC.py ${f} --zero`); } }
        else sh(`python3 predict_runR.py ${f}`);
      } finally { fs.rmSync(f, { force: true }); }''')
sub('''    const stock0 = apiCall(`/__admin/stock?pages=${pages}`);
    apiCall("/__admin/writes", { ...c.proc, pages, seed: c.wseed });''',
    '''    if (conduit) apiCall("/__admin/reset", {});
    const stock0 = apiCall(`/__admin/stock?pages=${pages}`);
    if (c.proc.kind) apiCall("/__admin/writes", { ...c.proc, pages, seed: c.wseed });''')
sub('''    try { runBrowser({ mode: c.mode, runId, out: `/results/${cmd}.jsonl`, users, limit: 25, warm: true, snap: true }); }
    finally { apiCall("/__admin/writes", {}); }
    const { times, ...procLog } = c.proc;''',
    '''    try { runBrowser({ mode: c.mode, runId, out: `/results/${cmd}.jsonl`, users, limit, warm: true, snap: true }); }
    finally { apiCall("/__admin/writes", {}); }
    const { times, ...procLog } = c.proc;''')
sub('''  if (!man.pilot && !fs.existsSync(`${import.meta.dirname}/results/modelR.frozen.json`)) throw new Error("freeze modelR first");''',
    '''  if (!man.pilot && !man.calibration && !fs.existsSync(`${import.meta.dirname}/results/${man.app === "conduit" ? "modelRC" : "modelR"}.frozen.json`)) throw new Error("freeze the model first");''')
sub('''    if (!man.pilot) {''', '''    if (!man.pilot && !(conduit && man.calibration)) {''')
sub('''} else if (cmd.startsWith("rev")) {''', '''} else if (cmd.startsWith("rev") || cmd.startsWith("cd")) {''')
open(P, "w").write(s)
print("harness patched for Conduit")
