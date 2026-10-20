# Testbed

Docker testbed for the CSR/SSR × cache-layer study. See [../RESEARCH_PLAN.md](../RESEARCH_PLAN.md).

```
client (Playwright) ──n_cw── web (Next.js 16) ──n_wa── api (Express) ──n_data── redis, postgres
        └───────────────────────n_ca──────────────────────┘
```

Each link is its own Docker network, so `netem` can shape it independently (RTT/2 at each end).

## Cache layers

| Path | Browser | Server | Backend |
|---|---|---|---|
| CSR `/csr` | TanStack Query (`FE_CACHE`) | — | Redis (admin config) |
| SSR `/ssr` | — | Next data cache, `force-cache` (`FE_CACHE`) | Redis |

## Use

```bash
docker compose up -d --build
node harness.mjs calibrate 170   # apply +170 ms client RTT and measure it
node harness.mjs smoke           # all 8 configs, cold start each, RTT 0
```

## Logs (`results/`)

- `api.jsonl`: one line per API request: Redis hit/miss/off, DB time, caller, run ID.
- `web.jsonl`: one line per SSR render: Next data cache hit/miss/off (detected by response-ID replay).
- `*.jsonl` from the runner: per repetition: initial load (visible, DOM, interactive, TTFB, FCP), first visit to p2, revisit p1, TanStack misses.

## Checks

- `db/check_query.sql`: the analytics query vs an independent per-product reference.
