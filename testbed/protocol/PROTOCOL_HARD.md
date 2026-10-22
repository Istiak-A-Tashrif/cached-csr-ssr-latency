# Revision protocol v3: near-threshold policy selection, distribution-only predictions, model R2

Frozen on 22 Oct 2026, before any run of these blocks. Hashes are in `protocol/FROZEN_HARD.json`, and the commit that adds this file is the timestamp. This protocol answers a second external review. Rules are those of v1 unless stated here.

## What informed it (retrospective, on data already scored)

- **SSR framework-push bias (`diag_push.py`, `diag_o1_variants.py`).**
  - The cache transitions follow the model's rule. In revT, a write since the last fill always led to a fetch, and 97.7% of views with no write were served from cache.
  - With the observed time since the last access, the Poisson formula predicts the observed miss share (0.370 against 0.369 observed in revT; 0.162 against 0.152 in revR).
  - The model's excess comes from its exposure window, which ran to display instead of to the request's arrival at the server. Correcting that (model R2) removes about half of the excess.
- **O1 decile calibration against noise (`diag_o1_noise.py`).** Run-bootstrap 95% intervals of the decile deviations are about ±0.05 wide, so the v1 tolerance of 0.05 is at the noise floor. A few deciles still show real biases of 0.04–0.07.
- **Staleness decomposition (`diag_decomp.py`).** In Poisson blocks, write-rate drift explains little of the cell errors: pooled MAE moves only from 0.016 to 0.015 and from 0.020 to 0.019. The largest cell misses fall where run-to-run variability is large. Write-rate drift explains about half of the worst trace miss.
- **Distribution-only predictions (`diag_distonly.py`).** Predicting from the access distribution alone, instead of the declared sessions, gave the same accuracy on revT, revR, cdT and cdR (staleness MAE 0.016/0.020/0.010/0.013, latency 1.2–1.8%).
- **Safety margin.** The 95th percentile of per-cell |observed − predicted| staleness over the 216 cells of revT, revR, cdT, cdR, cdHT and cdHR is 0.051. The pre-registered margin is **0.05**.

## Model R2

Model R with one correction: a framework-push entry's exposure to writes ends when the request reaches the server.
- Calibration and the O2 reference are model R's, unchanged (from calibW).
- `freezeR2.py` freezes it.
- **Predictions use the access distribution only.** Zipf α = 0.8 over 8 pages, 16 users × 12 views, averaged over 8 session sets sampled with seeds unrelated to the run (`predict_runR2.py`). The prediction with the declared sessions is recorded beside it, for comparison only.

## Blocks

| Block | Seeds | Client RTT | d | Writes | Runs |
|---|---|---|---|---|---|
| revHT | 960–965 | 120 ms | 30 ms | Poisson 2.0/s | 96 (16 policies × 6 seeds) |
| revHR | 980–985 | 200 ms | 60 ms | Poisson 1.2/s | 96 |

The 16 policies are chosen to be close in latency or staleness:
- SSR push+push; SSR no cache; CSR no cache; SSR Next TTL + Redis TTL at 2 s;
- and for τ ∈ {2, 4, 8} s: SSR Redis TTL, SSR Next TTL + Redis push, CSR TanStack TTL + Redis push, CSR Redis TTL.

**Staleness limits, written into the manifests before any run.** They come from R2's distribution-only predictions at each block's nominal condition. For every Pareto-front candidate of a decision set whose predicted stale share lies in [0.03, 0.6], two limits are placed: its predicted share +0.01 and −0.01. That puts every decision at the predicted boundary of the best policy.

**Decision sets.**
- **all:** all 16 policies.
- **ttl_only:** the policies without push invalidation, as when an application cannot hook its writes.

That gives 8 decisions per block, 16 in total.

## Criteria (`evaluateR2.py`)

- **W1–W5:** as v1, scored on the distribution-only stale shares.
- **L1–L2:** as v1, scored per view on the declared-session predictions.
- **O1, O2, O3:** as v1.
- **O1′ (noise-aware):** in every decile with ≥ 100 views, |observed − predicted| ≤ max(0.05, the half-width of its 95% run-bootstrap interval). Both O1 and O1′ are reported.
- **B4h-a:** the uncertainty-aware selector (predicted stale share + 0.05 ≤ ε) has mean regret ≤ 5% over its feasible decisions.
- **B4h-b:** the uncertainty-aware selector makes no confirmed violation (the run-bootstrap 2.5% bound of the observed stale share above ε).
- **Point selector (margin 0):** reported, not gated: violations, confirmed violations, oracle choices, regret.

Abstentions are reported. With 16 decisions, no violation rate is bounded.

**Acceptance.** Model R2 and the selection claim are accepted if revHT and revHR both pass every criterion except O1, whose result is reported alongside O1′.

Blocks run once, in the order revHT, revHR.
