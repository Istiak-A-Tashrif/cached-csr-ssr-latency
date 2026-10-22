// Instrumented product-analytics API.
// Every request is logged out-of-band (JSONL) with the Redis outcome measured
// where it happens. Responses carry only data + an opaque response id, which the
// web tier uses to detect replays from its own data cache.
const express = require("express");
const cors = require("cors");
const { Pool } = require("pg");
const { createClient } = require("redis");
const { randomUUID } = require("crypto");
const fs = require("fs");

const PORT = Number(process.env.PORT || 5001);
const LOG_FILE = process.env.LOG_FILE || "/results/api.jsonl";

// Runtime config (changed between runs via /__admin/config, never mid-run).
const config = {
  redis: process.env.REDIS_CACHE === "on",
  ttl: Number(process.env.REDIS_TTL || 3600),
  query: process.env.QUERY_VARIANT || "correct", // "correct" | "legacy"
  runId: "unset",
  inv: "ttl",            // item 8: Redis "ttl" (expiry only) | "push" (key deleted on every write)
  invNext: false,        // item 8: also revalidate the page's Next data-cache tag on every write
  dbDelayMs: 0,          // regime experiment: added DB time per DB read
  writes: null,          // item 8: { lam, pages, seed } while a writer runs
};

const pool = new Pool({
  host: process.env.DB_HOST || "db",
  user: process.env.DB_USER || "postgres",
  password: process.env.DB_PASSWORD || "postgres",
  database: process.env.DB_NAME || "caching_research",
  port: 5432,
  max: 10,
});

const redis = createClient({ url: process.env.REDIS_URL || "redis://redis:6379" });
redis.on("error", (e) => console.error("redis error", e.message));

// Append per line (reopened each time) so rotating/deleting the file between
// runs can never send records to an unlinked inode.
const emit = (rec) => fs.appendFileSync(LOG_FILE, JSON.stringify(rec) + "\n");

// Pre-aggregated per product so the joins cannot fan out.
// total_orders = distinct orders containing the product; avg_rating over its reviews.
const QUERIES = {
  correct: `
    SELECT p.id, p.name, c.name AS category,
           COALESCE(o.total_orders, 0) AS total_orders,
           COALESCE(r.avg_rating, 0)   AS avg_rating,
           COALESCE(i.stock, 0)        AS stock
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id
    LEFT JOIN (SELECT product_id, COUNT(DISTINCT order_id) AS total_orders
               FROM order_items GROUP BY product_id) o ON o.product_id = p.id
    LEFT JOIN (SELECT product_id, AVG(rating) AS avg_rating
               FROM reviews GROUP BY product_id) r ON r.product_id = p.id
    LEFT JOIN inventory i ON i.product_id = p.id
    ORDER BY p.id
    LIMIT $1 OFFSET $2`,
  // Query used in the rejected manuscript (kept only for reproducing old numbers).
  // order_items x reviews fan-out inflates COUNT and weights AVG.
  legacy: `
    SELECT p.id, p.name, c.name AS category,
           COUNT(oi.id) AS total_orders,
           COALESCE(AVG(r.rating), 0) AS avg_rating,
           COALESCE(i.stock, 0) AS stock
    FROM products p
    LEFT JOIN categories c ON p.category_id = c.id
    LEFT JOIN order_items oi ON oi.product_id = p.id
    LEFT JOIN reviews r ON r.product_id = p.id
    LEFT JOIN inventory i ON i.product_id = p.id
    GROUP BY p.id, c.name, i.stock
    ORDER BY p.id
    LIMIT $1 OFFSET $2`,
};

const app = express();
app.use(cors({ origin: "*" }));
app.use(express.json());

app.get("/api/products", async (req, res) => {
  const t0 = performance.now();
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit) || 25));
  const key = `products:${config.query}:p${page}:l${limit}`;
  let redisOutcome = config.redis ? "miss" : "off";
  let redisMs = null, dbMs = null, setMs = null, rows;

  try {
    if (config.redis) {
      const r0 = performance.now();
      const cached = await redis.get(key);
      redisMs = performance.now() - r0;
      if (cached) { rows = JSON.parse(cached); redisOutcome = "hit"; }
    }
    if (!rows) {
      const d0 = performance.now();
      // Server-work regime experiment: extra database time on every DB read (opt-in, default 0).
      if (config.dbDelayMs) await pool.query("SELECT pg_sleep($1)", [config.dbDelayMs / 1000]);
      rows = (await pool.query(QUERIES[config.query], [limit, (page - 1) * limit])).rows;
      dbMs = performance.now() - d0;
      if (config.redis) {
        const s0 = performance.now();
        await redis.set(key, JSON.stringify(rows), { EX: config.ttl });
        setMs = performance.now() - s0;
      }
    }
    const respId = randomUUID();
    res.set("cache-control", "no-store");
    res.set("timing-allow-origin", "*"); // expose Resource Timing to the cross-origin page
    res.json({ respId, page, limit, data: rows });
    emit({
      // Correlation tags travel in the query string: custom headers would add a
      // CORS preflight in the browser and change Next's data-cache key.
      ts: Date.now(), runId: config.runId, reqId: req.query.rid || null,
      caller: req.query.caller || "unknown", key, respId, redis: redisOutcome,
      redisMs, dbMs, setMs, totalMs: performance.now() - t0, rows: rows.length,
    });
  } catch (e) {
    emit({ ts: Date.now(), runId: config.runId, key, error: e.message });
    res.status(500).json({ error: e.message });
  }
});

// ---- Item 8: seeded Poisson writer (stock updates) with optional push invalidation ----
const WRITES_LOG = process.env.WRITES_LOG || "/results/writes.jsonl";
let writer = null;
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
async function purge(page) {
  // Push invalidation for the (default) 25-row pages, per layer: Redis key, Next data-cache tag.
  if (config.inv === "push") await redis.del(`products:${config.query}:p${page}:l25`);
  if (config.invNext) await fetch(`${process.env.WEB_URL || "http://web:3000"}/api/revalidate?tag=p${page}-l25`).catch(() => {});
}
// Write processes (TWEB revision, B2). "poisson" (default) is unchanged from item 8 / experiment X:
// the same random stream, so earlier runs replay identically. Others: "periodic" (every 1/lam s,
// random phase), "onoff" (Poisson at onRate during exponential ON periods of mean onMean s, none
// during OFF periods of mean offMean s; starts in the stationary state), "trace" (commit offsets
// in ms from writer start, supplied by the harness). The written product is uniform over the
// workload's pages in every process.
function* schedule({ kind = "poisson", lam, onRate, onMean, offMean, times }, rand) {
  const exp = (rate) => -Math.log(1 - rand()) / rate * 1000;
  if (kind === "poisson") { let t = 0; for (;;) { t += exp(lam); yield t; } }
  if (kind === "periodic") { const d = 1000 / lam; let t = rand() * d; for (;;) { yield t; t += d; } }
  if (kind === "onoff") {
    let on = rand() < onMean / (onMean + offMean), t = 0, end = exp(1 / (on ? onMean : offMean));
    for (;;) {
      if (on) { const a = t + exp(onRate); if (a < end) { t = a; yield t; continue; } }
      t = end; on = !on; end = t + exp(1 / (on ? onMean : offMean));
    }
  }
  if (kind === "trace") { for (const t of times) yield t; return; }
  throw new Error(`unknown write process ${kind}`);
}
function startWriter(spec) {
  const { pages, seed } = spec;
  const rand = rng(seed); let seq = 0;
  // Poisson keeps its original draw order (wait, then product) so earlier runs replay identically.
  const draws = spec.kind && spec.kind !== "poisson" ? schedule(spec, rand) : null;
  const t0 = Date.now();
  const next = () => {
    let wait;
    if (draws) { const it = draws.next(); if (it.done) { writer = null; return; } wait = Math.max(0, it.value - (Date.now() - t0)); }
    else wait = -Math.log(1 - rand()) / spec.lam * 1000;     // exponential inter-arrival (ms)
    const productId = 1 + Math.floor(rand() * pages * 25);     // uniform over the workload's pages
    writer = setTimeout(async () => {
      const r = await pool.query("UPDATE inventory SET stock = stock + 1, last_updated = now() WHERE product_id = $1 RETURNING stock", [productId]);
      const committed = Date.now(); const page = Math.ceil(productId / 25);
      let purgedAt = null;
      if (config.inv === "push" || config.invNext) { await purge(page); purgedAt = Date.now(); }
      fs.appendFileSync(WRITES_LOG, JSON.stringify({ runId: config.runId, seq: seq++, productId, page, stock: r.rows[0]?.stock, committed, purgedAt }) + "\n");
      if (writer) next();
    }, wait);
  };
  next();
}
app.get("/__admin/stock", async (req, res) => {
  const pages = Number(req.query.pages || 8);
  const r = await pool.query("SELECT product_id, stock FROM inventory WHERE product_id <= $1 ORDER BY product_id", [pages * 25]);
  res.json({ at: Date.now(), stock: Object.fromEntries(r.rows.map((x) => [x.product_id, x.stock])) });
});
app.post("/__admin/writes", (req, res) => {
  if (writer) { clearTimeout(writer); writer = null; }
  if (req.body?.lam || req.body?.kind === "trace") startWriter(req.body);
  config.writes = req.body?.lam || req.body?.kind === "trace" ? { ...req.body, times: req.body.times ? req.body.times.length : undefined } : null;
  res.json({ writes: config.writes });
});

// Throughput probe (harness only, not logged): n bytes of incompressible data.
const BLOB = require("crypto").randomBytes(32 * 1024 * 1024);
app.get("/__blob", (req, res) => {
  const n = Math.min(BLOB.length, Math.max(1, parseInt(req.query.n) || 1));
  res.set({ "cache-control": "no-store", "content-type": "application/octet-stream", "timing-allow-origin": "*" });
  res.end(BLOB.subarray(0, n));
});

// Harness-only control plane (excluded from measurements).
app.get("/__admin/config", (_req, res) => res.json(config));
app.post("/__admin/config", async (req, res) => {
  Object.assign(config, req.body || {});
  if (req.body?.flushRedis) await redis.flushAll();
  delete config.flushRedis;
  res.json(config);
});
app.get("/health", (_req, res) => res.json({ ok: true }));

(async () => {
  await redis.connect();
  app.listen(PORT, "0.0.0.0", () => console.log(`api on ${PORT}`, config));
})();
