# Literature search log

**Date:** 21 Oct 2026. Earlier searches (October 2026) are recorded in RESEARCH_PLAN.md Part 3.

**Saved results:** the full OpenAlex results (title, venue, year, citations, DOI for the top 25 per query) are kept with the session's working files. They can be regenerated with the queries below.

## Sources
- **OpenAlex** (api.openalex.org): works published from 2010, relevance-ranked, top 25 per query.
- **arXiv** API (export.arxiv.org), relevance-ranked, top 12 per query.
- **Crossref** (api.crossref.org) and official proceedings pages (USENIX), to verify bibliographic details.
- **Earlier October 2026 searches:** web search; OpenAlex citation tracing of Fofack et al. (2014); Crossref restricted to ACM venues (IMC, SIGMETRICS, WWW, NSDI, SIGCOMM, HotNets, CoNEXT, MobiSys, ICPE); ACM Digital Library full-text search in a browser.
- **IEEE Xplore** (21 Oct 2026): searched in a headed browser, 8 queries, years 2015–2026 (results kept with the session's working files).
- **Google Scholar** (21 Oct 2026): Google blocked the network outright ("automated queries"; no solvable challenge), so it was not searched. To be checked manually by the author from another network before submission.
- **Semantic Scholar API** (21 Oct 2026): the shared anonymous rate limit was exhausted (HTTP 429), so it was not searched. OpenAlex covers a comparable corpus.
- **SCImago:** behind a bot check; journal quartiles were taken from aggregators and are to be confirmed by the author.

## Queries (OpenAlex)

| # | Query | Hits |
|---|---|---|
| Q1 | server-side rendering client-side rendering performance | 18,707 |
| Q2 | Next.js React server-side rendering latency | 214 |
| Q3 | web page load time prediction model | 122,478 |
| Q4 | web application cache staleness invalidation TTL | 179 |
| Q5 | stale reads application-level cache database invalidation | 977 |
| Q6 | hierarchical cache filtering hit ratio upstream cache | 732 |
| Q7 | network emulation netem accuracy web page load | 78 |
| Q8 | validated performance model web application latency prediction | 150,681 |
| Q9 | single-page application hydration performance | 34,978 (dominated by chemistry) |
| Q10 | HTTP/2 page load time measurement | 386,442 |

**arXiv queries:**
- "server-side rendering"
- "client-side rendering" AND latency
- "page load" AND prediction AND model
- "pre-registered" in cs.NI
- "prospective" AND "performance model" in cs.PF
- "stale" AND "cache" AND "web application"

## Screening
- **Included:** peer-reviewed or archival works on any of the following:
  - CSR/SSR performance
  - predictive models of web page performance
  - consistency or freshness of application or web caches
  - cache-hierarchy theory
  - fidelity of network emulation for web workloads
  - HTTP/2 page-load performance
- **Excluded:**
  - unrelated domains (chemistry, ML benchmarks, epidemiology)
  - hardware cache coherence
  - information-centric networking (ICN) caching without web or application context
  - non-archival blog posts
- Low-tier CSR/SSR comparison papers were screened. Representative ones are cited; they report point measurements of page-load metrics and none provides a predictive model.

## IEEE Xplore queries and outcome
The same 8 query strings as OpenAlex Q1–Q5, Q8 and Q10, plus "React Server Components performance". Most hits were off-topic: cloud gaming, CAD rendering, federated learning and React textbooks. One relevant study was added: Savenko & Babii, IEEE Access 13 (2025), on Next.js performance optimization. Nothing found predicts per-action latency or staleness across stacked caches.

## Added to the paper (verified)
| Work | Why |
|---|---|
| Iskandar et al., IOP CS:MSE 801 (2020), doi:10.1088/1757-899X/801/1/012136 | CSR vs SSR comparison (most-cited in Q1) |
| Hanafi et al., Teknika 13 (2024), doi:10.34148/teknika.v13i1.769 | Next.js rendering methods vs page-load time |
| Ramakrishnan & Kaur, IST 123 (2020), doi:10.1016/j.infsof.2020.106307 | Closest "prediction" work: statistical/ML models of page performance from page characteristics. Not prospective, not cache-aware. |
| Ports et al., OSDI '10 (TxCache) | Transactional consistency for application data caches |
| Wijnants et al., WWW '18, doi:10.1145/3178876.3186181 | HTTP/2 prioritization and page-load performance |
| Rajiullah et al., WWW '19, doi:10.1145/3308558.3313606 | Large-scale measurement of web experience in mobile networks |
| Pediaditakis et al., ANCS '14, doi:10.1145/2658260.2658274 | Fidelity of reproduced network experiments |
| Chen, arXiv 2504.03884 (2025) | Modular rendering and adaptive hydration in React/Next.js |
| Savenko & Babii, IEEE Access 13 (2025), doi:10.1109/ACCESS.2025.3647563 | Next.js performance optimization (found via IEEE Xplore) |

## Result for the novelty claims
- **Not found:** a model that predicts per-action data-visible latency across stacked browser, framework and application caches, validated prospectively (predictions written before runs, fresh conditions, replication), on emulated and real paths.
- **Not found:** a predictive and validated model of the stale-view share across stacked browser, framework and application caches under TTL and push invalidation, nor its joint use with latency.
- **Found and cited:**
  - CSR/SSR measurements, single-layer staleness studies, TTL-hierarchy theory, and ML predictors of page performance.
  - Earlier work on emulation fidelity exists in general. We found none reporting the specific Chromium connection-race shift, nor the Playwright certificate-handling cost.
- **Wording kept in the paper:** "to our knowledge", not "first", because Google Scholar and Semantic Scholar could not be searched (blocked or rate-limited).
