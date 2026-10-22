# Revision protocol v1: catalogue blocks (B1, B2, B4)

Frozen on 21 Oct 2026, before any run of the blocks below. Hashes are in `protocol/FROZEN.json`, and the git commit that adds this file is the timestamp. Any change after freezing gets a dated amendment at the end of this file, with its reason. Earlier text is never edited.

## What informed this protocol (all retrospective, on data already used)

- **A1–A4.** Ablation, equal-information baselines, calibration efficiency and uncertainty, from `results/revision/`.
- **B1 offline (`b1_offline.py`).** The frozen modelX predicts which layer serves each view in W2/X with Brier 0.073–0.093, skill +0.57 to +0.76, top-1 accuracy 93–95%. P(db) is calibrated within 0.04 in every decile bin. The expected Brier of a calibrated forecaster on those views is ≈0.08, because push-invalidated entries survive at random. So the amended plan's fixed target of Brier ≤ 0.05 can't be met by any calibrated forecaster. The O1–O3 gates below replace it, and the reason is recorded here.
- **Logging bug found offline.** The SSR web log calls a response served from a background-refreshed (stale-while-revalidate) entry a "miss". For the fresh blocks, the runner exports the displayed response id (`resp`), and the evaluator classifies from it.
- **B4 offline (`b4_offline.py`).** On X's 9 coarse policies, selection is trivial: the selector, 2-run tuning and the oracle agree. The fresh blocks therefore use a 27-policy candidate set with four TTLs, so that stale shares straddle the limits.
- **Deferred: B3 (prediction intervals) and Redis eviction.** The amended plan marks both optional, to keep the paper on outcome prediction, freshness and selection. Both are reported as limitations.

## Model

`modelR` = experiment X's frozen calibration (calibW only: display gaps, and no-write latency per outcome as a linear function of RTT), with the declared write process in place of Poisson (`writeproc.py`, which gives P0(w) for Poisson, periodic, on/off MMPP and the empirical trace).

- **No refitting.** With Poisson writes, modelR reproduces modelX's stored predictions exactly (0.0 difference over 27,648 views).
- **P0 formulas checked.** They agree with Monte Carlo within 0.01 (periodic, on/off).
- **Frozen file.** `freezeR.py` writes `results/modelR.frozen.json`, which also holds the O2 outcome-frequency reference (class frequencies per policy, action and revisit flag in calibW).

## Blocks (manifests in `protocol/*.json`; seeds 800–999 only)

| Block | Seeds | Client RTT | d | Writes | Cells | Runs | Role |
|---|---|---|---|---|---|---|---|
| revDev | 800 | 100 | 25 ms | Poisson, periodic, on/off, trace (training window), mean 2/s | 3 policies | 12 | Development: pipeline check only, never scored as a test |
| revPilotT | 830 | 150 | 50 ms | Poisson 2.5/s | 27 policies × α {0.6, 1.0} | 54 | Tuning baseline's pilots for revT (excluded from scoring) |
| revT | 821–824 | 150 | 50 ms | Poisson 2.5/s | 54 | 216 | **Final test** for B1, latency, staleness and B4 |
| revPilotR | 850 | 80 | 15 ms | Poisson 1.5/s | 54 | 54 | Tuning pilots for revR |
| revR | 841–844 | 80 | 15 ms | Poisson 1.5/s | 54 | 216 | **Replication** |
| revB2T | 861–864 | 150 | 50 ms | periodic 2.5/s; on/off (10/s, ON 2 s, OFF 6 s); trace ×(2.5/0.307), test window, first half | 4 policies × 3 processes | 48 | **B2 final test** |
| revB2R | 871–874 | 80 | 15 ms | periodic 1.5/s; on/off (6/s, 2 s, 6 s); trace ×(1.5/0.307), test window, second half | 12 | 48 | **B2 replication** |

**Candidate policies (27).**
- No TTL: CSR no caches; SSR no caches; SSR Next push + Redis push.
- For each τ ∈ {1, 5, 20, 60} s: CSR Redis TTL; CSR TanStack TTL + Redis push; CSR TanStack TTL + Redis TTL; SSR Redis TTL; SSR Next TTL (stale-while-revalidate) + Redis push; SSR Next TTL + Redis TTL.
- Every TTL layer of a policy uses τ.

**Workload.** 16 users × 12 views over 8 pages, Zipf α, every page 25 products. Writes update a product drawn uniformly over the 8 pages, and every write is stock + 1.

**Trace.** German Wikipedia recent-change timestamps, 14 Oct 2026, 08:00–14:00 UTC (`traces/dewiki-rc-20261014.json`, sha256 in FROZEN.json).
- Hours 1–3 are the training window: the predictor reads only these.
- Hours 4–6 are the test window: only the writer replays these, in disjoint 40 s segments per run.
- It supplies timing only, so this is a trace-inspired synthetic workload.

## Criteria (per block; `evaluateR.py`)

**Staleness**
- **W1:** pooled MAE ≤ 0.03.
- **W2:** every cell within 0.05.
- **W3:** cells whose predictions differ by ≥ 0.05 are ordered correctly.
- **W4:** oracle integrity: nothing shown ahead of the database, writes logged in every run, errors 0, push purge lag p99 ≤ 20 ms.
- **W5:** every prediction written before its run, by the frozen model.

**Latency**
- **L1:** mean relative error over (cell, action) ≤ 3%.
- **L2:** every (cell, action) within max(5%, 10 ms).

**Outcomes (B1)**
- **O1, calibration:** in every predicted-P(db) decile bin with ≥ 100 views (0 < p < 1), |mean predicted − observed DB share| ≤ 0.05.
- **O2, skill:** multiclass Brier score below the calibration-frequency reference.
- **O3:** Brier minus the forecaster's own expected Brier (mean Σ p(1−p)) ≤ 0.03.
- **Descriptive:** top-1 accuracy, per-class confusion.

**Selection (B4; revT and revR, per α, ε ∈ {0.05, 0.10, 0.25, 0.50})**
- **Selector:** argmin predicted mean latency subject to predicted stale share ≤ ε; it abstains if nothing is feasible.
- **Oracle:** argmin observed mean latency subject to observed stale share ≤ ε.
- **Regret:** (L_sel − L_oracle)/L_oracle on the block's observed values.
- **Violation:** a selected policy whose observed stale share exceeds ε. It is confirmed if the run-bootstrap 2.5% bound also exceeds ε.
- **B4a:** mean selector regret over feasible decisions ≤ 5%.
- **B4b:** no confirmed violation.
- **Comparison policies (scored the same way, not gated):**
  - **tuning:** one pilot run per candidate at the test condition (54 runs per block, a measurement budget comparable to the model's 32 calibration runs, but paid at every new condition), pick by pilot means;
  - **fixed:** SSR Next push + Redis push, the best robust policy in experiment X;
  - **default:** SSR Next TTL + Redis TTL with τ = 60 s;
  - **no cache:** SSR without caches.
- **Reporting:** worst-case regret, abstentions and violation magnitudes. With 8 decisions per block, no violation *rate* can be bounded usefully (rule of three: < 3/16 with 16 decisions), so no reliability claim is made.

**Acceptance.**
- B1, latency and staleness are accepted if revT and revR both pass every W, L and O criterion.
- B4 is accepted if both pass B4a and B4b.
- B2 is accepted if revB2T and revB2R both pass W1–W5. L1–L2 are reported for B2 but not gated.
- Each process is also reported separately.

## Development and stopping

- **revDev runs first.** It only checks the pipeline: predictions written, outcomes classified, writer processes logged. Its data may be used to fix bugs and is never used to fit parameters.
- **Freezing.** A model change after the freeze makes a new version (R2, R3; at most 3), which is frozen again before any final block runs.
- **Final blocks.** They run once, in the order revPilotT, revT, revPilotR, revR, revB2T, revB2R.
- **Failures.** A failed gate is reported as a limitation, with its diagnosis. Nothing is retested on used conditions.
- **Run hygiene.**
  - Runs are in a randomized order per block, from the manifest.
  - Each run starts from cold caches (Redis flushed, web container recreated) and has an unmeasured warm-up.
  - A run that throws is repeated once from configuration, with a fresh prediction, and logged.
  - Views with an error record count against W4.
  - No other exclusions.
