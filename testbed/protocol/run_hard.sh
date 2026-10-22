#!/bin/sh
# Protocol v3 blocks in order (PROTOCOL_HARD.md).
set -e
cd "$(dirname "$0")/.."
unset COMPOSE_FILE APP
for b in revHT revHR; do echo "== $b $(date -u +%FT%TZ)"; node harness.mjs "$b" >> "results/$b.log" 2>&1; done
echo "== done $(date -u +%FT%TZ)"
