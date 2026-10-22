# Closest-work comparison (step 0, 21 Oct 2026)

This is the plan's §0 checkpoint: the closest prior work, quoted exactly, before any Phase B work. Each quote was extracted from the paper's PDF, which is kept in `papers/` and not redistributed. Search additions to `LITERATURE_SEARCH.md`: what-if web performance prediction, probabilistic staleness, freshness under Poisson updates, and TTL selection. Those searches found four works the earlier search had missed (WebProphet, WebPerf, PBS, Cho & Garcia-Molina). All four are now in `refs.bib` with DOIs checked through Crossref (WebProphet has no DOI; its USENIX page was checked).

## 1. What-if latency prediction for web services

**WebProphet (Li et al., NSDI '10).**
- "a tool that predicts the impact of various optimizations on user-perceived PLT of web services"
- "Given the dependency graph of a webpage, the performance predictor implements a simple and yet accurate method to simulate the page load process"
- "predicts the median and 95th percentiles of the page load time distribution with an error rate smaller than 16% in most cases"

It needs dependency extraction by timing perturbation for each page. It doesn't model application caches, rendering paths or data freshness.

**WebPerf (Jiang et al., SIGCOMM '16).**
- "estimates the distribution of cloud-side latency of a web request under hypothetical changes (called what-if scenarios) to the cloud-side configuration"
- "The back-end data tier consists of various data storage services, such as SQL databases, key-value stores, blob stores, Redis caches"
- "WebPerf's median estimation error was within < 7% in all cases"
- "While WebPerf's primary goal is to predict an application's cloud-side latency, its prediction can be combined with network latency and client-side latency (predicted by existing tools such as WebProphet [25])"

In WebPerf, Redis is a resource tier whose speed changes, not a cache whose hit or miss decides the request path. It doesn't model freshness.

**What we can't claim:** that predicting web latency under hypothetical configurations is new, or that our approach is the first what-if predictor.

**What remains open:**
- one model, end to end, of *data-visible* time (client, network, rendering path and server together), not cloud-side time alone and not page-load time;
- which stacked cache layer answers each action, which decides the critical path, and how it changes the CSR-versus-SSR comparison;
- doing this from a small calibration grid without tracing each page.

## 2. Staleness prediction and freshness models

**Cho & Garcia-Molina (SIGMOD '00).** This is the classical freshness/age framework for a local copy of a source that changes independently, with updates modeled as Poisson processes and refresh policies analyzed. Our P(stale) = 1 − e^{−λ(t−τ)} is the standard probability that a Poisson source changes after the last synchronization. It must be cited as such.

**Quaestor (Gessert et al., PVLDB '17).**
- "The result set Q of a query of cardinality n can then be regarded as a set of independent exponentially distributed random variables X_i, ..., X_n with different write-rates λ_w1, ..., λ_wn"
- "min{X1, ..., Xn}, which is again exponentially distributed with λmin = λw1 + ... + λwn"
- "The quantile function then provides estimates that have a probability p of seeing a write before expiration"
- staleness "using simulation", "through Monte Carlo simulation that is similar to PBS"

This is exactly our per-page λ_p (the sum over displayed rows). Quaestor uses it to *choose TTLs* for a target staleness probability. Its staleness evaluation is simulated, not measured against a display-time oracle.

**PBS (Bailis et al., PVLDB '12).**
- "algorithms and models for predicting the staleness of partial quorums"
- "use Monte Carlo methods to explore the trade-off between latency and t-visibility"
- "we compared our predicted t-visibility and latency with measured values observed in a commercially available, open source Dynamo-style data store. Our average t-visibility prediction RMSE was 0.28%"

This is a joint latency and staleness predictor validated against measurement. It covers replica quorums, not cache layers or rendering paths.

**Mao et al. (HotNets '24).** A cost model of TTL versus update and invalidation freshness, under "bounded staleness" (fresh if it "reflects all writes made ≥ T time ago"), with Poisson and trace workloads. It is about a single cache layer and backend cost, not view-level staleness or latency.

**Ji et al. (arXiv '23).** TTL versus transparent invalidation for an application cache, measured.

**What we can't claim:**
- that the staleness formula, the sum-of-rates over a result set, or TTL choice for a staleness target is new;
- that jointly predicting latency and staleness is new in general (PBS does it for quorums).

**What remains open:**
- the *display-time* stale-view probability across **stacked layers with different semantics** (browser staleTime with background refetch, framework stale-while-revalidate, Redis TTL or push with purge lag) over a session timeline;
- validating it against an oracle that compares every displayed row with the database at display time;
- linking it to data-visible latency through the same cache outcomes.

## 3. TTL and cache-hierarchy optimization

**Elsayed et al. (2024).** "We optimize hierarchies of Time-to-Live (TTL) caches under random network delays", formulated as utility maximization over "the exact object hit probability", with numerical and trace-based evaluation. This is the theory side.

**Che et al. (2002), Fofack et al. (2014), Berger et al. (2014).** Hierarchical and TTL cache analysis.

**What we can't claim:** new cache-hierarchy theory.

**What remains open:** choosing a *rendering mode together with a cache policy* under a measured staleness limit, scored by regret on a real stack.

## 4. CSR/SSR measurement (unchanged from LITERATURE_SEARCH.md)

Pati & Zaki (WWW '25), Gopal (SSRN '26), and the other measurement studies all report fixed operating points with no prediction.

## 5. Contribution statement (narrowed after this comparison)

> A per-action predictor of data-visible latency and stale-view probability for client- and server-rendered paths through stacked browser, framework and application caches. It derives which layer serves each view from the declared workload and cache policies. It is calibrated from a small emulated grid and checked prospectively on fresh conditions, including real internet paths and a second, independently written application. It is used to choose a rendering-and-caching policy under a staleness limit.

The staleness formula and the what-if idea are credited to prior work (Cho & Garcia-Molina; Quaestor; WebProphet and WebPerf). What is new is their combination along the actual request path of modern stacked caches, and the evidence that it predicts and decides correctly.

**One concrete, falsifiable advantage.** On conditions outside the calibration grid, the structural model predicts data-visible latency more accurately than equal-information learned baselines (ridge regression, random forest, gradient-boosted trees) fitted to the same calibration data. Its policy choices reach lower regret than matched-budget direct tuning, at a lower measurement cost.

This is tested by A2 (accuracy) and B4 (decisions). If either fails, the contribution narrows to the explanatory and measurement results, as plan §0 requires.

## 6. Mapping claims to experiments

| Claim | Evidence | Status |
|---|---|---|
| Structure, not only the fitted residual, carries the accuracy | A1 ablation | to run (retrospective) |
| Beats equal-information baselines outside the grid | A2 | to run (retrospective) |
| Cheap to calibrate | A3 | to run (retrospective) |
| Cache outcomes can be predicted, not given | B1 | offline on W2/X, then fresh |
| Staleness across stacked layers is predictable beyond Poisson writes | B2 | fresh |
| Policy choice beats fixed and tuned policies | B4 | offline on X, then fresh |
| Transfers to an independent application | B5 (Conduit) | fresh |
| Real paths, HTTP/2 | existing v7, v8b, v9 | done |
| Where it fails | home path, concurrency, throttled devices | done (reported) |
