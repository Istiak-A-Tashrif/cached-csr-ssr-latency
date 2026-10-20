# Pilot Report: Stage A (Weeks 1–3)

**Date:** 18 October 2026 · **Plan:** [RESEARCH_PLAN.md](RESEARCH_PLAN.md) §4.4–4.5 · **Code:** [testbed/](testbed/)
**Recommendation:** **Proceed to Stage B with a narrowed story** (see §6), subject to advisor review.

---

## 1. Setup

- **Containers:** Postgres 17 (the original dump), Redis 7.4, Express API, Next.js 16.1.1 (App Router, `/csr` and `/ssr`), and a Playwright 1.56 client.
- **Network:** every link is its own Docker network shaped by `netem`. The client links were set to 10 Mbit/s. The internal links had no added delay or rate limit.
- **Paths:**
  - CSR: TanStack Query in the browser → API → Redis → DB. Navigation uses `history.pushState`, with no server round trip.
  - SSR: Next data cache (`force-cache`) → API → Redis → DB. Navigation uses `router.push`.
- **Endpoint:** data-visible time, meaning the end of the first frame after the first data row enters the DOM. "Interactive" (hydration) is recorded separately for initial loads.
- **Outcome logging:** every action is classified by where it was served. Browser and server caches are logged where they occur, linked by request IDs carried out of band. All 10,368 actions were classified, with **0 errors and 0 unclassified actions**.

### Data and query corrections found in Week 1
- The aggregation query in the rejected manuscript overstated `total_orders` for **4,922 of 5,000 products** (corrected 19 Oct 2026; the earlier count of 2,442 was taken while the dump was still loading) (mean 6×, max 17×) through join fan-out. The corrected query matches an independent per-product reference exactly (`testbed/db/check_query.sql`).
- ~~The dump contains 8,169 reviews~~ **Correction (19 Oct 2026): the dump contains 30,000 reviews, matching the original Table 1.** The 8,169 figure was counted while the database was still loading (reviews load after products). All experiments ran after the load completed, so only this count was affected.

## 2. Pilot design (Stage A)

- **Configurations:** 2 modes × 4 cache combinations × client RTT {0, 170} ms × 2 workloads × 3 seeds = **96 runs, 6,912 actions**.
- **Workloads:** each run has 12 users with 6-step sessions. Every user is a fresh browser context, and every run starts with cold caches.
  - `reuse`: Zipf(1.0) over 50 pages.
  - `spread`: uniform over 200 pages.
- **Order:** configurations ran in a randomized order per seed.
- **Raw outputs:** `results/pilot*.jsonl` and `results/pilot-analysis.txt`.

## 3. Findings

### F1: A shared server cache makes Redis redundant
Database queries per action, with and without Redis:

| Path | Front-end cache | `reuse`: no Redis → Redis | `spread`: no Redis → Redis |
|---|---|---|---|
| CSR | off | 1.00 → 0.39 (−61%) | 1.00 → 0.85 (−15%) |
| CSR | TanStack on | 0.90 → 0.39 (−56%) | 0.98 → 0.85 (−13%) |
| SSR | off | 1.00 → 0.39 (−61%) | 1.00 → 0.85 (−15%) |
| SSR | Next cache on | 0.39 → 0.39 (**0%**) | 0.85 → 0.85 (**0%**) |

Behind the shared Next data cache, Redis's conditional hit ratio was **0.00**. Every repeated key is absorbed upstream, so Redis only ever sees first requests. A per-user browser cache leaves Redis almost all of its value. The filtering mechanism is known theory (Fofack et al. 2014; Che approximation); what's new is the measured effect in a default modern stack, where both layers have equal or unlimited lifetimes.

### F2: Initial load is decided by the rendering path, not by caches
SSR shows data 153 ms sooner at RTT 0 and **1,093 ms sooner at RTT 170**, regardless of cache settings. Caches change initial load by less than 1%. But SSR reaches interactivity only modestly earlier (1,149 vs 1,484 ms at RTT 170): **SSR data is visible about 756 ms before the page is interactive.** SSR's initial-load advantage is consistent with Pati & Zaki (WWW'25).

### F3: Navigation crossover between CSR and SSR (tested prospectively)
- In the pilot, SSR navigation was faster at RTT 0 (−4 ms), but **CSR was faster at RTT 170 when front-end caching was on** (+9 to +11 ms, CI excludes 0). The effect was small because only about 10% of navigations revisited a page.
- **Mechanism:** a browser-cache hit avoids the client round trip. A Next data-cache hit avoids only server-side work, which is small when the API link is fast.

**Prospective test (Week 3).**
1. Cost lines (latency against measured client RTT) were fitted on pilot data only.
2. Outcome mixes came from a separate calibration run (seed 11, RTT 0).
3. Predictions were **frozen before evaluation** (`results/predictions.frozen.json`, SHA-256 `96d6020c…`).
4. Evaluation: a new high-revisit workload (12 users × 12 steps over 8 pages), new seeds (21–23), and RTTs never used for fitting (40 and 300 ms). That's 24 runs and 3,456 actions.

| Measure | Model | Baseline: no cache | Baseline: fixed mean |
|---|---|---|---|
| Mean relative error (16 cells) | **4.5%** | 15.9% | 14.3% |
| Worst cell | **11.8%** | 112% | 98% |
| MAE | **13.9 ms** | 28.4 ms | 25.7 ms |

SSR − CSR navigation latency with both caches on:

| RTT | Predicted | Observed [95% CI] |
|---|---|---|
| 40 ms | +22.0 ms | **+15.2** [13.3, 16.4] |
| 300 ms | +170.5 ms | **+165.4** [154.3, 173.3]; prediction inside the CI |

The direction of the CSR/SSR difference was right in all 8 comparisons; both baselines predicted no navigation difference. The calibration mixes matched the measured mixes exactly, so the hit mix was independent of RTT here.

**A rule that follows from this:** with front-end caching, CSR navigation beats SSR roughly when P(browser hit) × (client RTT + transfer) exceeds the server-side work the shared cache saves. Here that was 53% browser hits against negligible savings from SSR's 95% data-cache hits.

## 4. Where the model failed
- **Initial loads at 40 ms:** CSR was over-predicted by about 50 ms (11.8%). A cost that's linear in RTT and fitted at 0 and 170 ms can't capture TCP slow start or bundle transfer. A different cost form for initial loads is needed.
- **Navigation without caches at 40 ms:** SSR − CSR was −10.0 ms observed vs −2.6 predicted. This is a small absolute error, but the CI excludes the prediction.
- **At RTT 0**, frame quantization (0–16 ms) dominates the differences; relative errors there aren't meaningful.

## 5. Limitations
- Everything runs on one host (Docker Desktop VM), with emulated delay; containers share CPU.
- One framework version (Next.js 16.1.1), one query, fixed page size (25), sequential users (no concurrency), and read-only operation (no writes or invalidation).
- Hit mixes were measured, not predicted from the workload (no analytical hit model yet).
- Internal links were unshaped, so the server-side cache's savings are at their smallest. **F3 depends on that.** A slow API/DB link would shift the crossover, and Stage B should test it.
- 3 seeds per cell. CIs come from bootstrapping run means and are approximate with this few units.

## 6. Recommendation and candidate story

**Proceed to Stage B, narrowed to:**
> *Where a cache sits determines what it can save. Browser caches remove client round trips; shared server caches remove only backend work and absorb the reuse that downstream caches would otherwise get. A path model built from these per-outcome costs predicts, out of sample, when CSR or SSR navigation wins, and baselines that ignore cache placement cannot.*

**Stage B priorities**, a declared, small extension of the pilot:
1. Add internal-link delay (web↔api and api↔db) as a factor. The rule above predicts the crossover moves; test that prospectively.
2. Replace the linear initial-load cost with a transfer-aware form; re-test at unseen RTTs.
3. Freeze predictions before every evaluation batch, as in Week 3.
4. Optional: a controlled test of F1 with a short Next data-cache lifetime vs Redis TTL, which should restore Redis hits.

**Novelty caveats:** F1's mechanism and F2 are known. The candidate contribution is F3: the validated, prospective decision rule with its placement explanation. Priority must still be checked (plan §3.3) before any claim is made.

**Checkpoint:** the plan requires advisor review of this report before committing to Stage B.

---

## 7. Addendum (19 Oct 2026): weak points addressed with model v2

At the author's direction, the weak points in §4–5 were addressed before advisor review. The internal-link factor (originally a Stage B item) was included.

**Changes in model v2** (`testbed/model2.py`):
1. **Analytic cache outcomes.** Each hit or miss is computed from the request sequence alone: sequential users, cold caches, no expiry within a run. They are no longer measured. The analytic outcomes matched the measured ones for **all 19,584 actions** in the pilot, Week 3 and v2 evaluation data.
2. **Transfer-aware critical-path network time:**
   - connection handshakes;
   - TCP slow start (initcwnd 10, rounds of max(RTT, bytes/bandwidth); Cardwell et al. 2000);
   - Chromium's 6 concurrent connections per origin for the JS bundle;
   - a 10 Mbit/s bottleneck.
   Byte sizes come from Resource Timing at RTT 0. Nothing is fitted across RTTs.
3. **Internal web↔API RTT** is on the SSR critical path whenever the Next data cache misses.
4. **Calibration** at RTT 0 on the evaluation workload.

**Disclosure:** the bundle scheduler was corrected after a Resource Timing diagnostic at 170 ms (an RTT already used earlier). The 40/170/300 ms data informed v2's design, so it isn't used as validation.

**Fresh prospective test.**
- Predictions were frozen first: `results/predictions2.frozen.json`, SHA-256 `3c48397a…`.
- Conditions: client RTT 80/230 ms × internal RTT 0/60 ms; new seeds 31–34; 64 runs; 9,216 actions; 0 errors.

| Model | MAE | Mean rel. error | Worst cell |
|---|---|---|---|
| **v2** | **14.5 ms** | **3.3%** | **11.8%** |
| v1 (pilot model) | 19.6 ms | 6.0% | 39.4% |
| No-cache baseline | 29.6 ms | 16.9% | 96.3% |
| Fixed-mean baseline | 28.4 ms | 15.2% | 83.1% |

**New prediction confirmed (internal link).** With a slow web↔API link and no caches, CSR navigation beats SSR by **+66.5 ms** (observed) vs **+62.7** (v2). v1 and both baselines predicted about −2 ms. With caches on, the Next data cache shields SSR from the internal delay: **+42.8** observed vs **+43.4** predicted.

**Crossover reproduced at fresh RTTs (caches on).** SSR − CSR navigation:

| Client RTT | Internal RTT | Observed | v2 predicted |
|---|---|---|---|
| 80 | 0 | +39.7 | +40.4 (in CI) |
| 230 | 0 | +119.4 | +117.1 (in CI) |
| 230 | 60 | +122.9 | +120.0 (in CI) |

**Status of each weak point:**

| Weak point (§4–5) | Status |
|---|---|
| Initial-load nonlinearity (11.8% → 39% for v1 at fresh RTTs) | **Fixed for CSR**: within 0.2–6.2% |
| SSR−CSR navigation error at 40 ms | **Fixed**: navigation differences now within 0.5–5 ms |
| Internal link unshaped | **Added and validated** (above) |
| Hit mixes measured, not predicted | **Fixed**: exact analytic outcomes |
| 3 seeds | 4 new seeds in this test |
| Frame quantization at RTT 0 | Unchanged (test RTTs ≥ 80 ms); limitation stated |
| Single host, one framework, no concurrency or writes | Unchanged; scope limits |

**Remaining error.** v2 under-predicts **SSR initial load** by 3–12%:
- a roughly constant 15–20 ms gap that doesn't scale with RTT, probably from how Next streams the HTML (not yet diagnosed);
- extra error with the slow internal link, which measured about **79 ms instead of 60 ms nominal**. netem overshoot on that link is larger than the calibration assumed.

Neither was tuned away. Doing so would need another fresh test.

---

## 8. Model iteration to acceptance (v3–v5, 19 Oct 2026)

**Acceptance criteria were fixed before scoring v4** (RESEARCH_PLAN.md decision log):
- (1) mean relative error ≤ 3%;
- (2) every cell within max(5%, 10 ms);
- (3) every SSR−CSR difference has the correct sign and is within max(10 ms, 10%);
- (4) analytic outcomes 100%;
- (5) every prediction written before its run starts.

**Rules:**
- Every model change gets a fresh test, with conditions and seeds never used before.
- Diagnostics use only conditions that have already been used.
- No version cap; the first version that passes must also pass an independent replication.

| Version | Change (each traced to a measured mechanism) | Fresh test | Result |
|---|---|---|---|
| v3 | TCP-connect RTT measured before/after each run (ICMP read 2–3 ms low and drifted between runs); warm-up on an unused page (cold first render cost ~40 ms); recalibration | client 120/350 × internal 30/90 | Stopped part-way (author's decision): CSR initial off by +1 RTT |
| v4 | JS dispatch order from loads with real latency (at RTT 0 Resource Timing order is arbitrary: "70 KB last" 4/24 at 0 ms, 0/24 at 170 ms); per-connection congestion windows (chunk on the reused document connection saves one slow-start round: 960 vs 1,110 ms); transfer = rounds × RTT + bytes/bandwidth (the measured 52 ms shortfall = 56 ms serialization of the 70 KB chunk); κ at 170 ms | client 60/260 × internal 45/120, seeds 51–54 | **Not accepted**: mean 3.68%, two cells at 5.3–5.8% (low RTT) |
| v5 | Correction per (mode, action, outcome), piecewise-linear over the used client RTTs. Covers (a) the frame wait at RTT 0 (5–12 ms), which shrinks to 1–3 ms once the page idles on the network (headless Chromium renders a frame on demand), and (b) round-trip cost growing ~2–3% faster than the probe RTT, multiplied by the path's round-trip count | client 90/210 × internal 20/75, seeds 61–64 | **Passed all 5**: mean **1.10%**, max **3.78%** |
| v5 replication | Model unchanged (same frozen file, SHA-256 `f29d7258…`) | client 150/320 × internal 35/100, seeds 71–74 | **Passed all 5**: mean **0.77%**, max **3.64%** → **ACCEPTED** |

**Integrity notes:**
- In the v5 test, one run was slowed by host sleep (491 s vs ~65 s). Per protocol it was discarded (logged in `results/discarded-runs.jsonl`) and rerun under the frozen model, with its prediction written 2.0 s before its first request.
- A bookkeeping bug in the discard step (JSON spacing) briefly made C5 report a false "late" prediction. The tool was fixed and the unchanged data re-scored. The harness now runs `caffeinate`.

**Replicated SSR − CSR navigation differences (observed vs v5):**

| Client RTT | Internal RTT | Caches | Observed (ms) | v5 (ms) |
|---|---|---|---|---|
| 150 | 35 | off | +37.7 | +39.6 |
| 150 | 100 | off | +108.5 | +105.3 |
| 150 | 35 | on | +83.8 | +82.0 |
| 320 | 35 | on | +171.7 | +171.2 |
| 320 | 100 | on | +175.8 | +175.1 |

The internal-link effect with caches off and the browser-cache crossover with caches on both replicate.

**Remaining limitations** (scope, not model error):
- single host with emulated delay;
- one framework (Next.js 16.1.1);
- sequential users (no concurrency);
- read-only operation;
- v5's correction is calibrated for client RTTs of 60–350 ms and is held constant outside that range (no extrapolation claim).

**Artifacts:**
- Model: `testbed/model2.py`, `model4.py`, `model5.py`.
- Frozen parameters: `results/model5.frozen.json`.
- Per-run predictions: `results/predictions5.jsonl`.
- Scoring: `testbed/evaluate_n.py`, with outputs in `results/prosp5-evaluation.txt` and `results/rep5-evaluation.txt`.

---

## 9. Stage B2: real-network validation (v6 → v7, 19 Oct 2026)

**Question.** Does a model calibrated **only under emulated delay (netem)** predict latency over a **real internet path**?

**Setup.**
- **Compute:** both client and server run on one host (server, 4 cores; capped at 3 cores and 4 GB, beside live co-hosted production apps that were not touched). Calibration and test therefore use identical hardware.
- **Network:** real path server → relay VPS (NAT relay, end-to-end TCP) → server, RTT ~490 ms with real jitter and queuing.
- **Bandwidth:** held at 10 Mbit/s with netem rate limiting, so only the latency is real.
- **Records:** all server changes, with undo commands, are in [SERVER_CHANGES.md](SERVER_CHANGES.md).

**v6: v5's equations, recalibrated on server with netem only** (RTT 0 plus a grid at 120–550 ms).
- Real path: mean error 2.28% (replication 2.34%).
- **Not accepted.** CSR initial load was under-predicted by 6–8% in both runs; every other cell was within 2%.

**Diagnosis** (Resource Timing on the used real path vs the netem grid):
- **Only the JS-bundle phase differed:** 3.76 vs 3.23 RTT.
- **Cause: Chromium's connection-assignment race.** The 70 KB chunk runs either on a reused connection (grown window) or on a new one (one more slow-start round). Both become free about 1 RTT after the request, so the winner depends on path micro-timing.
- **Under netem a new connection won 11% of the time; on the real path, 75%.**
- v6's simulator had also mis-modelled the reused case on this host: two warm connections, not one. The netem-fitted correction had hidden that, but only at netem's odds.

**v7: race-aware bundle, calibrated from netem data only.**
- E[bundle] = p · B_new(RTT) + (1 − p) · B_reused(RTT).
- **Per-group curves** come from netem calibration loads.
- The **correction is re-fitted with each action's actual race group**, so it no longer encodes any race odds.
- **p is measured on the path before each run:** 8 probe loads of a page no workload uses, logged under a separate run ID.
- Prediction inputs per run: frozen netem calibration, declared workload, pre-run TCP RTT, pre-run p.

**v7 fresh tests** (real path plus emulated extra delay, conditions and seeds never used; predictions written before each run):

| Test | Condition | Mean error | Worst cell | Result |
|---|---|---|---|---|
| real7 | real + 40 ms (~530 ms), seeds 101–104 | **0.61%** | 1.15% | **5/5 pass** |
| rep7 | real + 20 ms (~510 ms), seeds 121–124 | **1.08%** | 2.27% | **5/5 pass**, **ACCEPTED** |

Per-run race probability ranged from 0.50 to 1.00 on the real paths, against 0.11 under netem.

**Findings for the paper:**
1. **Calibrate once in the lab, predict real networks.** The same equations, calibrated per environment under emulation, predict real-internet latency within about 1% from two cheap pre-run measurements: TCP RTT and the race probability.
2. **netem does not reproduce real-path connection timing.** It systematically distorts Chromium's connection-assignment race (11% vs 75%), and so the slow-start round count. This matters for emulation-based web-performance studies.

**Limitations:**
- Only one real path (plus emulated extensions of it).
- The relay host sits in the path (L3 NAT, end-to-end TCP preserved).
- Bandwidth is still emulated.
- One framework, HTTP/1.1 without TLS.
- Sequential users.

## 10. Open issues addressed (19–20 Oct 2026)

Every item used the same protocol as §8–9: calibrate (netem unless noted), freeze with hashes, write per-run predictions before each run, then a fresh test and an independent replication on new conditions and seeds. Criteria C1–C5 as in the decision log (W1–W5 for staleness). Failed versions are listed with their diagnoses; full detail is in the RESEARCH_PLAN.md decision log.

### 10.1 Summary

| Item | Final model | Fresh test | Replication | Verdict |
|---|---|---|---|---|
| Bandwidth as a measured input (real path, uncapped, probed per run) | v8b | real8b 0.62% (max 2.23%) | rep8b 0.70% (max 2.38%) | **Accepted** |
| HTTPS + HTTP/2 via a Caddy edge (real path) | v9 | real9 0.26% (max 0.44%) | rep9 0.23% (max 0.61%) | **Accepted** (see 10.3 caveat) |
| Second framework (SvelteKit) | modelS | testS 0.69% (max 2.78%) | repS 0.33% (max 0.90%) | **Accepted** |
| Writes and invalidation (staleness, Mac) | modelW | testW2 pooled MAE 0.011 (max 0.037), 24/24 orderings | repW2 0.009 (max 0.022), 22/22 | **Accepted** |
| Concurrency (server, pinned cores) | modelP3 / P4 | P3 N=4 3.16%; P4 N=3 2.26% (one cell −6.4%) | P3 N=8 2.00% (all five pass); P4 N=7 4.74% | **Near-miss** (2–5% on fresh N) |
| Second real path (home broadband → server) | modelH3 | realH3 8.26% | repH3 5.28% | **Not accepted; reported limitation** |

### 10.2 Baselines on every final test

Naive baselines fitted on each model's own pre-freeze calibration data (`testbed/baselines.py`): B_mean is a latency-vs-RTT line per (mode, action) ignoring cache layers; B_nocache is the same line from cache-off runs.

| Test | Model mean / max | B_mean mean / max | B_nocache mean / max |
|---|---|---|---|
| prosp5 / rep5 (emulated) | 1.10 / 3.78%, 0.77 / 3.64% | 15.3 / 56.8%, 14.8 / 60.7% | 21.6 / 88.3%, 19.3 / 98.2% |
| testS / repS (SvelteKit) | 0.69 / 2.78%, 0.33 / 0.90% | 10.2 / 53.8%, 11.0 / 60.7% | 13.2 / 104.6%, 14.6 / 114.1% |
| real7 / rep7 | 0.61 / 1.15%, 1.08 / 2.27% | 47.2 / 60.5%, 47.5 / 60.2% | 43.5 / 51.6%, 43.0 / 51.4% |
| real8b / rep8b | 0.62 / 2.23%, 0.70 / 2.38% | 47.9 / 61.5%, 47.0 / 60.7% | 43.5 / 51.6%, 43.4 / 51.4% |
| real9 / rep9 | 0.26 / 0.44%, 0.23 / 0.61% | 47.5 / 61.4%, 46.9 / 61.3% | 42.8 / 49.4%, 43.5 / 49.2% |

### 10.3 Findings from this phase

1. **Staleness is predictable, and server-side TTL caches buy freshness loss for almost no latency here.**
   - With a fast query and a local API link, Redis/Next TTL caches saved < 1 ms of navigation latency but made 40–69% of views stale.
   - The browser cache alone cut navigation latency about 45% (170 → 90 ms at RTT 150).
   - Push invalidation removed almost all staleness (0.5–3%) at no measurable latency cost.
   - The model gives the boundary at which server caches start paying off.
2. **HTTPS measurement artifact.** Playwright's `ignoreHTTPSErrors` adds 2 RTT before every new TLS connection (417 ms vs 0.8 ms at RTT 207; CSR initial 2,849 vs 2,022 ms).
   - v9 still predicts accurately, because the netem-fitted correction absorbed the artifact.
   - Its absolute HTTP/2 latencies overstate trusted-certificate deployments.
   - v9b, recalibrated with the certificate trusted by key, cut the correction for SSR initial from +223…+1,081 ms to about −30 ms. Its fresh test is waiting for a clean relay path (the server↔relay VPS path showed heavy loss on 20 Oct).
   - The HTTP/1.1 vs HTTP/2 transfer of the JS bundle was the same; the h2 penalty was entirely this per-connection setup cost.
3. **Concurrency needs cpusets, a start barrier and separate on-path vs total demand.**
   - CFS CPU quotas distort queueing and created a heavy Postgres tail (p99 58 vs 17 ms).
   - Launching N browsers at the start of a short run contaminated the measurements (throughput at N=8 below N=4).
   - Charging an action its total client CPU over-predicted SSR initial loads by 38–84%.
   - With all three fixed, plus load-dependent demand, MVA predicts concurrent latency within 2–5% on fresh population sizes, close to but not within the 3% bar.
4. **Consumer access links bound prospective accuracy.**
   - On home broadband the RTT drifted up to 22 ms within a run, and bandwidth varied 3–12 Mbit/s between runs.
   - A tail of slow requests raised mean navigation latency above what any pre-run probe predicted.
   - The model matched typical navigations, but means were 5–8% off.
   - Iteration stopped at H3 to avoid fitting noise and to limit the author's home data use (the 8/32 MB bandwidth probe used ~4 GB over two tests before it was reduced).

### 10.4 Limitations after this phase
- One application and data shape.
- Headless Chromium only.
- The datacenter real path is a relay through one VPS.
- Concurrency covers no-cache configurations only (cache outcomes under interleaving are not analytic).
- The HTTP/2 result with a trusted certificate (v9b) is pending.

## 11. Additional experiments (20 Oct 2026): server-work regime, heavier page, slow devices

| Experiment | Model | Fresh test | Replication | Verdict |
|---|---|---|---|---|
| X: server-work regime (added DB work 25 / 100 ms; latency and staleness of 9 policies) | modelX (staleness model + expected DB-read probability), frozen from no-write data | testX: staleness MAE 0.013 (max 0.038), 24/24 orderings; latency 1.87% (max 4.91%); 7/7 savings | repX: staleness 0.006 (max 0.018), 27/27; latency 0.95% (max 2.14%); 7/7 | **Accepted** |
| Q: heavier page (+~300 kB client bundle, 4× payload; ~25 ms DB work per read, see note) | v7 equations recalibrated | 1.23% (max 2.91%) | 0.61% (max 2.27%) | **Accepted** |
| R: slow devices, Mac | v7 at 1× and 6× CPU throttle, linear in rate | 3.26% | 6.18% | Invalid platform: Apple Silicon core switching made the server ~4.5 ms slower per DB read only in unthrottled runs |
| R2: slow devices, server (Linux, pinned cores) | same | 4×: 2.28% (max 7.05%) | 2×: 2.08% (max 7.22%) | **Near-miss**: navigations all within 2.3%; initial loads at low RTT (60–80 ms, between grid points) over-predicted 4–7% |

**Server-work regime finding (X, measured and predicted).** With 100 ms of DB work per read (RTT 200):
- SSR with no caches: 328 ms per navigation, 2.8% stale.
- Next push + Redis push: 260 ms (saves 68 ms), 2.3% stale.
- TTL caches: about 225 ms (save about 100 ms), but 38–58% stale.

So server caches pay once server work is real, and push invalidation captures most of the saving at almost no freshness cost. With fast queries (item 8) the same caches saved < 1 ms. The model predicts where between these regimes a deployment sits.

**Notes.**
- Experiment X's 25 ms DB delay persisted in the API through Q and R; the harness now resets it on every configuration. Q's calibration and tests all ran with it, so Q's acceptance stands as a page with ~25 ms of DB work per read.
- Two lessons: CPU-dependent experiments are invalid on Apple Silicon Macs; calibration grids need points below 120 ms RTT (v9b and R2 both missed only there).
