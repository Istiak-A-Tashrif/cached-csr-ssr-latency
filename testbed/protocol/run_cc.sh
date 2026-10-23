#!/bin/sh
# Protocol v4 blocks in order (PROTOCOL_CC.md).
set -e
cd "$(dirname "$0")/.."
unset COMPOSE_FILE APP
for b in revCCdev revCCT revCCR; do echo "== $b $(date -u +%FT%TZ)"; node harness.mjs "$b" >> "results/$b.log" 2>&1; done
echo "== done $(date -u +%FT%TZ)"
