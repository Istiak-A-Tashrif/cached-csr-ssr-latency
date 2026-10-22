#!/bin/sh
# Local Conduit blocks in protocol order (PROTOCOL_CONDUIT.md with amendment A2: calibrate, freeze, dev check, tests).
set -e
cd "$(dirname "$0")/.."
export COMPOSE_FILE=docker-compose.yml:docker-compose.conduit.yml APP=conduit
echo "== cdCal $(date -u +%FT%TZ)"; node harness.mjs cdCal >> results/cdCal.log 2>&1
python3 freezeRC.py cdCal >> results/cdCal.log 2>&1
for b in cdDev cdPilotT cdT cdPilotR cdR; do
  echo "== $b $(date -u +%FT%TZ)"
  node harness.mjs "$b" >> "results/$b.log" 2>&1
done
echo "== done $(date -u +%FT%TZ)"
