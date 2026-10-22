# Cached CSR/SSR latency and staleness: testbed, models and data

[![DOI](https://zenodo.org/badge/1427513690.svg)](https://doi.org/10.5281/zenodo.23512120)

Artifact for the paper *Predicting Latency and Freshness of Cached Client- and Server-Rendered Web Applications* (Istiak Ahmed Tashrif, submitted to ACM Transactions on the Web). Version 1.1.0 adds the revision's experiments: predicted serving layers, other write processes, policy selection, a second application (Conduit) and the retrospective analyses.

It contains everything needed to rerun the experiments, re-score every test from its logs, and regenerate the paper's figures and tables.

## Contents

| Path | What it is |
|---|---|
| `testbed/` | Docker testbed: PostgreSQL 17, Redis 7.4, Express API (`api/`), Next.js 16 app (`web/`), SvelteKit app (`web-svelte/`), Playwright client (`client/`), per-link network shaping (`netem/`), HTTPS/HTTP-2 edge (`edge/`), harness container (`controller/`) |
| `testbed/harness.mjs` | Experiment harness: calibration, prospective tests, replications. Every command is listed at the end of the file |
| `testbed/model*.py`, `staleness.py` | Latency models (v2–v9, H, P, L variants), staleness and server-work regime models (`staleness.py`, `modelX.py`) |
| `testbed/freeze*.py`, `predict_run*.py` | Freeze a model (hashed parameters); write a run's predictions before it starts |
| `testbed/evaluate_n.py`, `evaluateW.py`, `evaluateX.py`, `baselines.py` | Score tests against the pre-registered criteria; naive baselines |
| `testbed/results/` | Frozen models (`*.frozen.json`) and every evaluation report (`*-evaluation.txt`), including failed versions |
| `data/raw-results.tar.gz` | Raw logs: per-action browser records, server logs, per-run metadata, predictions, write logs |
| `paper/` | LaTeX sources; `make_figs.py` rebuilds every figure and table from the evaluation reports |
| `docs/DECISION_LOG.md` | Dated log of design decisions, pre-registered criteria, results and diagnoses |
| `docs/EXPERIMENT_REPORT.md` | Detailed experiment report |
| `testbed/protocol/` | Revision protocols frozen before their runs (`PROTOCOL.md`, `PROTOCOL_CONDUIT.md`), hashes (`FROZEN*.json`), run manifests (`rev*.json`, `cd*.json`) |
| `testbed/modelR.py`, `modelRC.py`, `writeproc.py` | Revision models: serving layer per view, latency and staleness under any declared write process (Poisson, periodic, on/off, trace) |
| `testbed/evaluateR.py`, `evaluateRC.py` | Score revision blocks: staleness (W), latency (L), serving layer (O) and policy selection (B4) |
| `testbed/conduit/` | Second application: the RealWorld "Conduit" reference backend (fetched at a pinned commit, unmodified) and the bench entry point that adds logging, a Redis layer, a writer and admin endpoints |
| `testbed/traces/` | Public inputs: German Wikipedia edit timestamps (write timing) and top-article pageviews (popularity), with the fetch scripts in `tools/` |
| `testbed/ablation.py`, `baselines_eq.py`, `calib_efficiency.py`, `uncertainty.py`, `staleness_checks.py`, `b1_offline.py`, `b4_offline.py` | Retrospective analyses of the frozen predictions (ablation, equal-information baselines, calibration cost, bootstrap intervals, oracle checks, serving-layer and selection scoring); outputs in `testbed/results/revision/` |
| `tools/reproduce_evaluations.sh` | Re-scores every prospective test from the raw logs and checks them against the published evaluations and `tools/raw-data.sha256` |

Server names and addresses in configs, logs and docs are replaced by placeholders. The documentation ranges `203.0.113.0/24` and `198.51.100.0/24` stand in for the servers and the home network. Set your own hosts in the `docker-compose.*.yml` overrides.

## Quick start (emulated network, one machine)

Requirements: Docker with Compose v2, Node.js 20+, Python 3.9+. Use a Linux x86 host for CPU-dependent experiments (concurrency, CPU throttling). On Apple Silicon, load-dependent core scheduling distorts service times (see the paper, Section 10).

```sh
cd testbed
docker compose up -d --build          # loads the database dump on first start (about 1 minute)
node harness.mjs smoke                # all 8 cache configurations at RTT 0
node harness.mjs calibW               # example: staleness calibration (no writes)
python3 freezeW.py                    # freeze the staleness model
node harness.mjs testW2               # fresh test: predictions are written before each run
python3 evaluateW.py testW2           # score against criteria W1-W5
```

Commands for each experiment (`calibS/gridS/testS/repS`, `calibQ/…`, `calibR2/…`, `calibP2/…`, `testX/repX`, real-path `real7/rep7`, `real8b/rep8b`, `real9/rep9`, …) are in `harness.mjs`. Real-path experiments need a second host as a layer-3 relay; see `docker-compose.relay*.yml`.

## Re-scoring and figures from the published logs

```sh
tar xzf data/raw-results.tar.gz       # restores testbed/results/*
cd testbed && python3 evaluate_n.py rep5 predictions5.jsonl   # any test
cd ../paper && python3 -m venv .venv && .venv/bin/pip install matplotlib==3.9.2 numpy==2.0.2
.venv/bin/python make_figs.py         # figures and tables
```

Revision blocks (the catalogue first, then Conduit with `APP=conduit` and `COMPOSE_FILE=docker-compose.yml:docker-compose.conduit.yml`):

```sh
python3 freezeR.py && sh protocol/run_catalogue.sh      # revPilotT, revT, revPilotR, revR, revB2T, revB2R
python3 evaluateR.py revT --pilot revPilotT
```

To check every published evaluation from the raw logs: `tar xzf data/raw-results.tar.gz && bash tools/reproduce_evaluations.sh`.

## Prospective protocol

Each model version is calibrated under emulation and frozen (code and parameters hashed). The harness then writes every run's prediction before the run starts, on conditions and seeds never used for fitting. A version is accepted only if a fresh test and an independent replication both pass criteria fixed in advance. Failed versions and their diagnoses are kept in `docs/DECISION_LOG.md` and `testbed/results/`.

## Security note

Dependency versions are pinned to the exact versions the measurements were taken with (e.g. Next.js 16.1.1, PostgreSQL 17.0, Redis 7.4.1), because the models depend on their behaviour. Some of these versions have known vulnerabilities (GitHub flags several for Next.js 16.1.1). This is a measurement testbed: run it on a local machine or an isolated network and do not expose it to the internet. To reuse the application code in production, upgrade dependencies first (and recalibrate any model you use).

## License

Code: MIT (`LICENSE`). Data, logs and documentation: CC BY 4.0 (`DATA_LICENSE.md`). Please cite the paper (`CITATION.cff`).
