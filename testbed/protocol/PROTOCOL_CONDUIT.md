# Revision protocol v2: Conduit blocks (B5, second application)

Frozen on 21 Oct 2026, before any Conduit run. Hashes are in `protocol/FROZEN_CONDUIT.json`, and the git commit that adds this file is the timestamp. Criteria, analysis rules and stopping rules are those of `PROTOCOL.md` (v1) unless stated here.

## Application

**Backend.** The RealWorld "Conduit" reference backend, `gothinkster/node-express-realworld-example-app` at commit `30b68e1e`: Express, Prisma 4, PostgreSQL, MIT per its package.json. It is fetched at build time and used unmodified, including its routes, services, schema and queries. `conduit/bench/main.ts` adds only an entry point:
- request logging with response ids;
- a Redis read-through layer for `GET /api/articles/:slug` (TTL or delete-on-write);
- a writer that favourites articles through the application's own `favoriteArticle` service, using the same write processes as the catalogue;
- admin endpoints and deterministic seeding.

**Seed data.**
- 50 articles titled after German Wikipedia's 50 most viewed articles of 13 Oct 2026 (`traces/dewiki-top-20261013.json`), plus a warm-up article.
- 20 authors and 3,000 users.
- Baseline favourites per article grow with popularity. They are reset before every run, because the reference query loads every favouriting user, so its cost grows with favourites.

**Front end.** The same Next.js application, its cache layers and instrumentation, with an adapter (`web/src/lib/app.ts`, `APP=conduit`). Page *n* is article *n* (`GET /api/articles/a<n>`), shown as one row whose favourites count is the value the oracle checks. This reuses framework code; the backend, schema, queries and data shape are independent of the catalogue.

**Workload.** 16 users × 12 views over the 50 article pages, drawn with probability proportional to the Wikipedia views. Writes favourite an article drawn with the same probabilities, so a page receives a write with probability p_n. Every write raises the count by one, so Proposition 1 applies with q = p_n.

This is a trace-inspired synthetic workload: real popularity, synthetic users and writes.

## Model

**modelRC** is modelR with a per-page write probability. `writeproc`'s formulas are exact with an effective page count of 1/p_n.

**Calibration (block cdCal).**
- No writes, client RTT 50 and 250 ms.
- The 9 policies of the catalogue's calibration, with every TTL layer at 3 s.
- `freezeRC.py` fits display gaps and the no-write latency per serving layer, exactly as freezeW/freezeX did for the catalogue, plus the O2 reference.
- The model is frozen after cdCal and before any test block.

**Zero-recalibration predictions.** The catalogue's modelR calibration is applied to Conduit (`predict_runRC.py --zero`). These predictions are written before each run beside the recalibrated ones and reported descriptively.

## Blocks (manifests in `protocol/cd*.json`; seeds 900–999)

| Block | Seeds | Client RTT | Writes | Cells | Runs | Role |
|---|---|---|---|---|---|---|
| cdDev | 900 | 100 | Poisson 2/s | 4 policies | 4 | Pipeline check only |
| cdCal | 901–902 | 50, 250 | none | 9 policies | 36 | Calibration |
| cdPilotT | 910 | 150 | Poisson 2.5/s | 27 | 27 | Tuning pilots for cdT |
| cdT | 911–914 | 150 | Poisson 2.5/s | 27 | 108 | **Final test** |
| cdPilotR | 920 | 80 | Poisson 1.5/s | 27 | 27 | Tuning pilots for cdR |
| cdR | 921–924 | 80 | Poisson 1.5/s | 27 | 108 | **Replication** |
| cdCalH | 931–932 | 50, 250 | none | 9 | 36 | Calibration on the second host |
| cdHT | 941–944 | 120 | Poisson 2/s | 27 | 108 | **Different-host test** |
| cdHR | 951–954 | 60 | Poisson 1.2/s | 27 | 108 | **Different-host replication** |

**Second host.** A Linux x86 server, with each service pinned to its own core, no published ports and no firewall changes. Every change is recorded in `SERVER_CHANGES.md` and reverted after the blocks.

**Criteria (`evaluateRC.py` = `evaluateR.py` with model RC):** W1–W5, L1–L2, O1–O3, and B4a–B4b with the same comparison policies:
- default: SSR, Next TTL + Redis TTL, τ = 60 s;
- fixed: SSR, Next push + Redis push;
- no cache;
- tuning from the pilot block.

**Acceptance.** B5 is accepted on this machine if cdT and cdR both pass every criterion, and on the second host if cdHT and cdHR both do. Zero-recalibration errors are descriptive.

## Development and stopping

These are the same as in v1:
- cdDev only checks the pipeline.
- A bug found there is fixed before cdCal. Code changes after the freeze are recorded as amendments, and the frozen model is never refitted on test data.
- At most 3 model versions.
- Final blocks run once. A failed gate is reported as a limitation.

## Amendments

**A1 (21 Oct 2026, before any Conduit run): different-host blocks not run.** cdCalH, cdHT and cdHR need a second machine that can run the whole stack.
- The Linux server used for the catalogue's real-path, concurrency and throttling tests (4 cores, 15 GB) is reachable, but the experiment account has no Docker access without sudo, which is not available in this session.
- The other hosts are unsuitable: the relay host has 2 vCPUs and 1 GB of RAM, and a third host runs production services.

So B5 is evaluated on this machine only (cdT, cdR). The manuscript states that the Conduit transfer was not tested on a second host. The different-host evidence for the latency model is the catalogue's: it was recalibrated and tested on the Linux server (v6–v9, R2, P2–P4).

The manifests stay frozen, so the blocks can still run unchanged if Docker access is granted.

**A2 (21 Oct 2026): second host available; the different-host blocks will run.** The author gave sudo access on the Linux server, so A1 is withdrawn and cdCalH, cdHT and cdHR run as specified.

The pipeline check (cdDev) found two start-up bugs, neither of which affects any measurement:
- The harness dispatched only commands starting with `rev`. The patch script now also routes `cd…` manifests.
- On the very first database start, the API raced the initial dump load. The API was restarted once Postgres was healthy.
- cdDev needs a frozen model for its predictions, so on each host the calibration block runs first, then the model is frozen, then cdDev runs as the pipeline check before any test block.
- freezeRC.py takes the calibration block as an argument (cdCal or cdCalH) and records it in the frozen file.
