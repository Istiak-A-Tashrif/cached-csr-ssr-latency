#!/usr/bin/env bash
# Re-score every prospective test behind the paper's Tables 1 and 2 from the raw logs and
# compare with the stored *-evaluation.txt (first line skipped: it echoes the tag as typed).
# Also checks the raw-data checksums in tools/raw-data.sha256.
# usage: tools/reproduce_evaluations.sh        (from the repository root; exit 1 on any mismatch)
set -u
cd "$(dirname "$0")/../testbed"
out=$(mktemp -d)
fail=0

check() {  # <stored evaluation> <fresh output> <label>
  if diff -q <(tail -n +2 "$1") <(tail -n +2 "$2") >/dev/null; then echo "ok    $3"
  else echo "DIFF  $3"; fail=1; fi
}

# tag:predictions-suffix:server-log subdirectory (empty = results/)
for spec in prosp5:5: rep5:5: testS:S: repS:S: testQ:Q: repQ:Q: \
            realH3:H3:server-final repH3:H3:server-final; do
  IFS=: read -r t v sl <<<"$spec"
  SERVER_LOGS=$sl python3 evaluate_n.py "$t" "predictions$v.jsonl" >"$out/$t" 2>&1
  check "results/$t-evaluation.txt" "$out/$t" "$t"
done
for spec in real7:7 rep7:7 real8b:8b rep8b:8b real9:9 rep9:9 test9b:9b reptest9b:9b \
            concP:P repP:P concP2:P2 repP2:P2 concP3:P3 repP3:P3 concP4:P4 repP4:P4; do
  IFS=: read -r t v <<<"$spec"
  SERVER_LOGS=server-final python3 evaluate_n.py "server-final/$t" "server-final/predictions$v.jsonl" >"$out/$t" 2>&1
  check "results/server-final/$t-evaluation.txt" "$out/$t" "$t"
done
for t in testR2 repR2; do
  SERVER_LOGS=server-R2 python3 evaluate_n.py "server-R2/$t" server-R2/predictionsR2.jsonl >"$out/$t" 2>&1
  check "results/server-R2/$t-evaluation.txt" "$out/$t" "$t"
done
for t in testW2 repW2; do python3 evaluateW.py "$t" >"$out/$t" 2>&1; check "results/$t-evaluation.txt" "$out/$t" "$t"; done
for t in testX repX; do python3 evaluateX.py "$t" >"$out/$t" 2>&1; check "results/$t-evaluation.txt" "$out/$t" "$t"; done

for t in revT:revPilotT revR:revPilotR revB2T: revB2R:; do
  b=${t%%:*}; p=${t##*:}
  python3 evaluateR.py "$b" ${p:+--pilot $p} >"$out/$b" 2>&1
  check "results/$b-evaluation.txt" "$out/$b" "$b"
done
for t in cdT:cdPilotT cdR:cdPilotR; do
  b=${t%%:*}; p=${t##*:}
  python3 evaluateRC.py "$b" --pilot "$p" >"$out/$b" 2>&1
  check "results/$b-evaluation.txt" "$out/$b" "$b"
done
for b in revHT revHR; do
  python3 evaluateR2.py "$b" >"$out/$b" 2>&1
  check "results/$b-evaluation.txt" "$out/$b" "$b"
done
for b in revCCT revCCR; do   # protocol v4 (chance-constrained selector)
  python3 evaluateCC.py "$b" >"$out/$b" 2>&1
  check "results/$b-evaluation.txt" "$out/$b" "$b"
done
# Second-host Conduit blocks: the unmodified evaluator, run from a copy whose results/ links to the second host's
# archive file by file, with its own revision/ so the evaluator's JSON output never overwrites the archived one.
mkdir -p "$out/h2/results/revision" && cp evaluateRC.py "$out/h2/"
for f in results/server-cd/*; do [ "$(basename "$f")" = revision ] || ln -s "$PWD/$f" "$out/h2/results/"; done
for b in cdHT cdHR; do
  (cd "$out/h2" && python3 evaluateRC.py "$b") >"$out/$b" 2>&1
  check "results/server-cd/$b-evaluation.txt" "$out/$b" "$b (second host)"
  (cd "$out/h2" && python3 evaluateRC.py "$b" --zero) >"$out/$b-zero" 2>&1
  check "results/server-cd/$b-zero-evaluation.txt" "$out/$b-zero" "$b zero recalibration (second host)"
done
# Retrospective decision-quality comparison (final revision); it also asserts the frozen model's stored regrets.
python3 decision_baselines.py >"$out/decision" 2>&1
if diff -q results/revision/decision-baselines.txt "$out/decision" >/dev/null; then echo "ok    decision baselines"
else echo "DIFF  decision baselines"; fail=1; fi

if (cd results && shasum -a 256 -c --quiet ../../tools/raw-data.sha256); then echo "ok    raw-data checksums"
else echo "DIFF  raw-data checksums"; fail=1; fi
rm -rf "$out"
exit $fail
