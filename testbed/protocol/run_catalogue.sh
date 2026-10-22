#!/bin/sh
# Final catalogue blocks in the order fixed by protocol/PROTOCOL.md; RESUME by rerunning (completed runs are skipped).
set -e
cd "$(dirname "$0")/.."
for b in revPilotT revT revPilotR revR revB2T revB2R; do
  echo "== $b $(date -u +%FT%TZ)"
  node harness.mjs "$b" >> "results/$b.log" 2>&1
done
echo "== done $(date -u +%FT%TZ)"
