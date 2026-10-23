# Protocol v4: chance-constrained policy selection near the threshold

Frozen on 23 Oct 2026, before any run of these blocks. Hashes are in `protocol/FROZEN_CC.json`; the commit that adds this file is the timestamp. Rules are those of v3 (`PROTOCOL_HARD.md`) unless stated here.

## Why

Protocol v3's margin selector (predicted stale share + 0.05 ≤ ε) made no violation in 16 decisions. Its mean regret, however, was 5.81% in the replication, missing the pre-registered 5% bound, so v3 was not accepted. That result stands. The v3 margin was one number for every candidate: the 95th percentile of earlier per-cell errors. Protocol v4 tests a selector whose margin is derived per candidate from the model's own uncertainty. It is fixed before any v4 run and decided on fresh conditions, with an independent replication.

## The selector (`selector_cc.py`)

Choose the fastest predicted candidate x with

    S^(x) + z_{1-a} · sqrt(sd_s(x)² + sd_m²) ≤ ε,   a = 0.05 (z = 1.645).

- **S^(x)** is model R2's distribution-only predicted stale share (`predict_runR2.py`, unchanged), averaged over the block's runs of x.
- **sd_s(x)** is the sampling sd of the block's observed stale share (the mean over its 6 runs) under the model. It comes from a Monte Carlo of the frozen R2 timeline with sessions sampled from the access distribution and Poisson writes realized per page. It is computed at each block's nominal condition and written into the manifest (`cc.sd_s`).
- **sd_m** is the model-error sd beyond sampling, from development blocks only: revT, revR, revHT and revHR, already scored (`derive_cc.py` → `results/revision/cc-derivation.json`). The estimate is sd_m² = max(0, mean(e² − sd_s²)) over 140 cells: RMSE 0.0238, rms sd_s 0.0223, giving **sd_m = 0.0084**. The envelope z·sqrt(sd_s² + sd_m²) contains |e| in 90.0% of these cells.
- **a = 0.05** was fixed before sd_m was estimated and before any in-sample look. It matches the coverage of v3's margin, a 95th percentile, now applied per candidate. It is not tuned.
- **In-sample look (development data, not evidence):** on revHT and revHR this selector makes the same 16 choices as the v3 margin selector (regret 4.07% and 5.81%). The limits there sit 0.01 from the predictions, inside any margin of this size. The fresh blocks therefore test whether the derived selector meets the bound at new conditions; they are not expected to differ from v3 by construction.

One development version; no further versions under this protocol.

## Blocks (`make_manifests_cc.py`)

Candidate structure and limit placement are as in v3 (16 policies; limits at ±0.01 around the predicted share of each Pareto-front candidate with a predicted share in [0.03, 0.6]; decision sets all and ttl_only). The conditions are new: Zipf α = 0.7, TTLs of 3, 6 and 12 s, and new RTTs, server work and write rates. No v4 condition was used for fitting or development.

| Block | Seeds | Client RTT | d | Writes | Runs | Decisions |
|---|---|---|---|---|---|---|
| revCCdev | 1020 | 140 ms | 35 ms | Poisson 1.8/s | 16 | pipeline check only, never scored |
| revCCT | 1000–1005 | 160 ms | 40 ms | Poisson 1.6/s | 96 | 10 |
| revCCR | 1010–1015 | 90 ms | 20 ms | Poisson 2.4/s | 96 | 6 |

## Criteria (`evaluateCC.py`)

`evaluateCC.py` is `evaluateR2.py` with only its selection section changed.

- **W1–W5, L1–L2, O1, O1′, O2, O3:** as v3 and reported. They are not part of v4's acceptance, which concerns the selector.
- **B4cc-a:** the chance-constrained selector's mean regret ≤ 5% over its feasible decisions.
- **B4cc-b:** the chance-constrained selector makes no confirmed violation (the run-bootstrap 2.5% bound of the observed stale share above ε).
- **Reported, not gated:** the point selector and the v3 margin selector (0.05) on the same decisions, with violations, confirmed violations, oracle choices, mean and worst regret, and abstentions.

**Acceptance.** The chance-constrained selection claim is accepted if revCCT and revCCR both pass B4cc-a and B4cc-b. With 16 decisions in 4 candidate sets, no violation rate is bounded.

Blocks run once, in the order revCCdev, revCCT, revCCR (`run_cc.sh`). A failure is reported as such and is not retested with a different a, sd_m or margin.
