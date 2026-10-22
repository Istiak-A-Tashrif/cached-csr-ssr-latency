# Audit of the revision's experimental evidence (22 Oct 2026)

**Who audited.** The author did this audit, with the AI assistant credited in the paper, using the scripts and records listed below. It is a self-audit, not an independent verification. Everything it relies on is in the artifact, so a third party can repeat it.

This audit answers an external reviewer's request to check that every prediction was written before its run, that no evaluation seed was reused during model development, that the archive reproduces the reported results, and that the adaptive steps (model versions, amendments) are on record. Times are UTC. Commit hashes refer to the development repository. The public artifact has no git history, so the commit times are recorded here.

## Chronology: protocol freezes vs. first runs

| Protocol / change | Commit | Committed | First run it governs | Lead |
|---|---|---|---|---|
| v1 catalogue (manifests, modelR, criteria) | 25b157c | 15:48:41 (21 Oct) | revDev 15:49:21; final blocks from revPilotT 15:59:49 | +40 s / +11 min |
| v2 Conduit (manifests, modelRC code, criteria) | 0a133a8 | 16:05:35 | cdCalH (second host) 16:33:02 | +27 min |
| v2 amendment A1 (second host unavailable) | 70fdda7 | 16:08:25 | — (withdrawn by A2) | — |
| v2 amendment A2 (second host available; harness routing of `cd…` blocks; calibration before the dev check) | 21033cd | 16:34:58 | cdCalH 16:33:02 | **−2 min** (see lapse 1) |
| `freezeRC.py` takes the calibration block as an argument | 4215444 | 17:28:23 | cdHT 17:27:11 | **−1 min** (see lapse 2) |
| v3 near-threshold (manifests with limits, model R2, criteria) | 33ad2a1 | 06:33:28 (22 Oct) | revHT 06:34:12 | +44 s |

**Lapse 1.** The text of amendment A2 was written into `PROTOCOL_CONDUIT.md` and copied to the second host in the same command that launched its calibration block. It was committed 2 minutes after that block started. The block is a calibration block: it has no predictions and is not scored.

**Lapse 2.** The change to `freezeRC.py` (reading the calibration block's name instead of a fixed name) was copied to the second host and used to freeze model RC before its development check (cdDev, 17:22:29). It was committed 1 minute after the test block started. It does not change the fitting.

Evidence that the model was frozen before any test run:
- The second host's frozen file `results/server-cd/modelRC.frozen.json` records `"calibration": "cdCalH"` and its hash.
- Every cdHT and cdHR prediction carries that hash.
- Criterion W5 (prediction written before its run, by the frozen model) passes for all 216 runs.

## Per-block chronology (UTC; from `results/revision/chronology.json`)

Every test block's first prediction comes after its protocol commit and before its first run. No prediction was written after its own run started.

| Block | Host | Protocol commit | First prediction written | First run starts | Predictions written before their run |
|---|---|---|---|---|---|
| revDev | this machine | v1 25b157c (15:48:41, 21 Oct) | 2026-10-21 15:49:20 | 2026-10-21 15:49:21 | 12 of 12 |
| revPilotT | this machine | v1 25b157c (15:48:41, 21 Oct) | none (calibration or pilot block) | 2026-10-21 15:59:49 | n/a |
| cdCalH | second host | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | none (calibration or pilot block) | 2026-10-21 16:33:02 | n/a |
| revT | this machine | v1 25b157c (15:48:41, 21 Oct) | 2026-10-21 16:59:19 | 2026-10-21 16:59:19 | 216 of 216 |
| cdDev | second host | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-21 17:22:27 | 2026-10-21 17:22:29 | 4 of 4 |
| cdHT | second host | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-21 17:27:09 | 2026-10-21 17:27:11 | 108 of 108 |
| cdHR | second host | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-21 19:38:02 | 2026-10-21 19:38:04 | 108 of 108 |
| revPilotR | this machine | v1 25b157c (15:48:41, 21 Oct) | none (calibration or pilot block) | 2026-10-21 20:55:19 | n/a |
| revR | this machine | v1 25b157c (15:48:41, 21 Oct) | 2026-10-21 21:31:15 | 2026-10-21 21:31:16 | 216 of 216 |
| revB2T | this machine | v1 25b157c (15:48:41, 21 Oct) | 2026-10-21 23:55:01 | 2026-10-21 23:55:02 | 48 of 48 |
| revB2R | this machine | v1 25b157c (15:48:41, 21 Oct) | 2026-10-22 00:47:52 | 2026-10-22 00:47:52 | 48 of 48 |
| cdCal | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | none (calibration or pilot block) | 2026-10-22 01:21:30 | n/a |
| cdDev | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-22 02:00:02 | 2026-10-22 02:00:03 | 4 of 4 |
| cdPilotT | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | none (calibration or pilot block) | 2026-10-22 02:03:10 | n/a |
| cdT | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-22 02:32:20 | 2026-10-22 02:32:21 | 108 of 108 |
| cdPilotR | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | none (calibration or pilot block) | 2026-10-22 04:28:55 | n/a |
| cdR | this machine | v2 0a133a8 (16:05:35, 21 Oct); A2 21033cd (16:34:58) | 2026-10-22 04:46:59 | 2026-10-22 04:47:00 | 108 of 108 |
| revHT | this machine | v3 33ad2a1 (06:33:28, 22 Oct) | 2026-10-22 06:34:11 | 2026-10-22 06:34:12 | 96 of 96 |
| revHR | this machine | v3 33ad2a1 (06:33:28, 22 Oct) | 2026-10-22 08:04:21 | 2026-10-22 08:04:21 | 96 of 96 |

## Frozen inputs unchanged

The run manifests hashed in `FROZEN.json`, `FROZEN_CONDUIT.json` and `FROZEN_HARD.json` still match their hashes. No manifest changed after its freeze.

Code that changed after a freeze is recorded as an amendment:
- the Conduit harness patch (A2);
- `freezeRC.py` (A2);
- the harness's optional `predictor` field (v3).

Two more checks:
- The catalogue harness, API and runner were not modified between the v1 freeze and the end of the catalogue blocks (01:19:56 on 22 Oct). The Conduit patch was applied after that.
- The web image used by the catalogue blocks was built from the v1 source right after the freeze. The front-end adapter for Conduit was rebuilt into the image only after the catalogue blocks ended.

## Predictions before runs

The following criteria pass in every scored block:
- C5 (latency tests);
- W5 (staleness and revision blocks), which also checks the frozen model's hash.

Each prediction record carries its write time, and each run record carries its start time `t0`.

## Seeds

The revision used 54 seeds in 800–999. Each was used in exactly one block, and none was used before the revision (the earlier maximum is 712). Development blocks (revDev, cdDev) and pilot blocks have their own seeds.

## Model development and fresh tests

| Model | Built from | Tested on (fresh) | Outcome |
|---|---|---|---|
| R | experiment X's calibration (calibW, Oct 20), no refitting | revT, revR, revB2T, revB2R | Selection accepted; W2/W3/O1 missed |
| RC | Conduit calibration (cdCal on this host; cdCalH on the second host) | cdT, cdR, cdHT, cdHR | Selection accepted; O1/W2/W3 missed |
| R2 | R plus one timing correction found post hoc on revT/revR (scored by 01:23 on 22 Oct; `diag_push.py`) | revHT, revHR (from 06:34) | All prediction criteria pass in both; selection regret missed in revHR |

No test block was rerun. No model was refitted on test data. The R2 correction was found on data that had already been scored, and it was tested only on blocks run after its freeze.

The 0.05 staleness margin and the limits ε were fixed in v3 before its runs:
- the margin from earlier blocks' per-cell errors;
- the limits from model R2's predictions alone.

## Reproduction

`tools/reproduce_evaluations.sh` re-scores 38 evaluations from the raw logs and checks `tools/raw-data.sha256` (514 files). Run from the extracted public artifact (`tar xzf data/raw-results.tar.gz && bash tools/reproduce_evaluations.sh`), all 39 checks pass: every evaluation is byte-identical to the published one apart from its first line, which echoes the tag. Tables and figures are generated from these evaluation outputs (`paper/make_figs.py`), and every number in the revision's text comes from `paper/make_numbers.py`.

The audit found and fixed one artifact bug: the README said `sh` for a script that needs `bash`.

The second-host Conduit blocks (cdHT, cdHR) are scored from `results/server-cd/`, but the reproduction script doesn't re-score them yet. Their raw logs and evaluations are in the artifact.

## Known record-keeping issues

- The revision's prediction file `predictionsR.jsonl` shares its name with experiment R's (October 20). Revision lines were appended to it. Run ids are disjoint, and the earlier lines are unchanged.
- The rule that classifies an SSR view's serving layer was corrected on old data (W2/X, `b1_offline.py`) before protocol v1 was frozen. Every revision block was scored with the corrected rule, via the displayed response id.

## Timing semantics: model R2 against the testbed (code-level check, sixth review)

| Event | Testbed | Model R2 (`modelR2.py`) | Agreement |
|---|---|---|---|
| A write between the server's cache read and display | Served data were current at the read; the oracle compares at display, so the view is stale | τ = read − purge lag (lines 58, 28), so the staleness window covers read → display; the miss exposure ends at the read (line 46, the R2 correction), so this write cannot cause a miss | Yes |
| A write just before the read, purge pending | A stale entry can be served for at most the purge lag (p99 4–10 ms in every block) | `PUSH_LAG` = 2 ms subtracted from τ | Yes, within a few ms |
| Redis TTL fill with server work d | `pg_sleep(d)` precedes the query, so data are as of request + d | Fill time and τ = `t_req + d` (lines 33–34) | Yes |
| TanStack revisit of a stale entry | Shows the cached data; refetch on mount reaches the API half an RTT later | `bg = t_disp + crtt/2`; new τ from that read (lines 54–55) | Yes |
| Next.js stale-while-revalidate | Serves the old entry; the background refresh replaces it after the internal fetch (tens of ms) | Entry replaced at the request (line 65) | **Approximation**: wrong only for another request to the same page within that interval |
| Server receipt of the request | Action start + half the client RTT | Display − half RTT − 10 ms render (line 51) | **Approximation**: the response transfer is longer than half an RTT on SSR pages; a likely part of the ~0.02 residual excess of predicted DB reads (an alternative, action start + half RTT, changed the excess little: 0.388 vs 0.385 on revT) |

Empirical check of the push purge semantics (`diag_push.py`): in revT and revR, 100% of SSR push views that followed a write to their page since the entry's last fill were fetched again, and 97.7% / 99.3% of the others were served from the cache.

The Conduit blocks (cdT, cdR, cdHT, cdHR) used model RC, which has model R's exposure timing, not R2's.
