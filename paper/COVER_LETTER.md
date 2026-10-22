Dear Editors of ACM Transactions on the Web,

I submit the manuscript "Predicting Latency and Freshness of Cached Client- and Server-Rendered Web Applications: Which Cache Layer Answers, What It Costs, and Which Policy to Choose" for consideration as a research article.

Modern web frameworks let developers choose, per page, between client- and server-side rendering, and they stack several caches on each path: a browser cache, a framework data cache and an application cache. The paper predicts, from cache policies, a description of the expected workload and network probes, which of these layers serves each user action, how long its data takes to appear and how likely it is to be stale. It then uses those predictions to choose a rendering and caching policy under a staleness limit. Every prediction was written before its run, on conditions never used for fitting. The protocols for the newest experiments were frozen and committed before any of their runs, and every model version is reported, including those that failed.

The main results are these:
- Latency is predicted within 0.2–1.8% mean error. This holds on emulated paths, on one real relayed internet path in three configurations (including HTTPS with HTTP/2), for a second framework, and for an independently written second application (the RealWorld "Conduit" backend) on two hosts.
- In the tests with 27 candidate policies, the selector chose a policy within 2% of the observed best without violating the staleness limit, while framework-default TTLs violated the limit in 29 of 32 decisions.
- With limits placed at the predicted boundary, a selector with a staleness margin made no violation in 16 decisions. Its latency regret met the pre-registered 5% bound in the test (4.1%) but not in the replication (5.8%), and we report that failure.
- We also report the pre-registered criteria the first models missed, the corrected model that passed them on fresh tests, and the conditions under which prediction fails (consumer broadband, shared-core concurrency, write rates that drift from history).
- An audit of the experimental record, which the author carried out and which is repeatable from the artifact, is included. It covers commit chronology, frozen manifests, seed use, and the re-scoring of every block from raw logs.

**Relation to earlier work.** An earlier manuscript on the same testbed ("Impact of Application-Layer Caching on Backend and Frontend Latency in CSR and SSR") was rejected by Computer Networks in October 2026. It measured fixed configurations and contained no predictive model. The present manuscript is new work with a different question, model, protocol and evaluation. Neither manuscript is published or under consideration elsewhere.

**Artifact.** The testbed, frozen models and protocols, per-run predictions, raw logs, analysis scripts and a script that re-scores every test from the raw logs are archived on Zenodo, and the DOI is given in the manuscript.

**AI assistance.** A generative AI tool assisted with code, experiment execution, analysis, figures and the drafting and editing of text. The disclosure is in the acknowledgments. I directed the research and take responsibility for all content.

Thank you for your consideration.

Sincerely,
Istiak Ahmed Tashrif
Department of Computer Science and Engineering, Sonargaon University, Dhaka, Bangladesh
istiaktashrif@gmail.com · ORCID 0009-0001-6363-4129
