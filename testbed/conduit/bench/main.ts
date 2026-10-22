// Bench entry for the Conduit (RealWorld) backend, TWEB revision B5.
// The application -- routes, services, Prisma schema and queries -- is the reference implementation,
// unmodified (Dockerfile pins the commit). This file adds only what the testbed needs, mirroring the
// catalogue API (api/server.js):
//   - request logging to /results/api.jsonl (run id, request id, caller, Redis outcome, timings) and a
//     response id on every article response (correlates browser views, web renders and API requests);
//   - a Redis read-through layer for GET /api/articles/:slug (TTL or push invalidation);
//   - a writer that favourites articles through the application's own favoriteArticle service, with
//     the same write processes as the catalogue (poisson, periodic, onoff, trace), targeting articles
//     with the workload's popularity, and purging Redis and the Next data-cache tag on push;
//   - admin endpoints (config, writes, favourite-count snapshot, reset) and deterministic seeding.
// Page n of the workload is article n (slug "a<n>"), so the harness and oracle work unchanged.
import express from 'express';
import cors from 'cors';
import * as bodyParser from 'body-parser';
import fs from 'fs';
import { randomUUID } from 'crypto';
import { createClient } from 'redis';
import routes from '../src/app/routes/routes';
import { favoriteArticle } from '../src/app/routes/article/article.service';
import prisma from '../src/prisma/prisma-client';

const LOG = process.env.LOG_FILE || '/results/api.jsonl';
const WRITES_LOG = process.env.WRITES_LOG || '/results/writes.jsonl';
const POP = JSON.parse(fs.readFileSync(__dirname + '/../bench/popularity.json', 'utf8')).articles as { title: string; views: number }[];
const N = POP.length;               // articles 1..N are the workload's pages
const WARMUP = 199;                 // never drawn by a workload
const FANS = 3000;
const baseline = (n: number) => Math.round(5 + (200 * POP[n - 1].views) / POP[0].views);   // seeded favourites of article n

const config: any = { runId: null, redis: false, ttl: 3600, inv: 'ttl', invNext: false, dbDelayMs: 0, writes: null };
const redis = createClient({ url: process.env.REDIS_URL || 'redis://redis:6379' });
const emit = (o: object) => fs.appendFileSync(LOG, JSON.stringify(o) + '\n');

async function seed() {
  if ((await prisma.article.count()) > 0) return;
  const authors = [];
  for (let i = 1; i <= 20; i++)
    authors.push(await prisma.user.create({ data: { email: `author${i}@bench.local`, username: `author${i}`, password: 'x', bio: `Author ${i}` } }));
  await prisma.user.createMany({ data: Array.from({ length: FANS }, (_, i) => ({ email: `fan${i + 1}@bench.local`, username: `fan${i + 1}`, password: 'x' })) });
  const tags = ['news', 'sport', 'film', 'music', 'politics', 'history', 'science', 'tv', 'games', 'travel'];
  const para = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. ';
  const make = async (n: number, title: string) =>
    prisma.article.create({
      data: {
        slug: `a${n}`, title, description: `About ${title}`, body: para.repeat(16),
        author: { connect: { id: authors[(n - 1) % authors.length].id } },
        tagList: { connectOrCreate: [0, 3, 7].map((k) => ({ create: { name: tags[(n + k) % tags.length] }, where: { name: tags[(n + k) % tags.length] } })) },
      },
    });
  for (let n = 1; n <= N; n++) await make(n, POP[n - 1].title);
  await make(WARMUP, 'Warm-up article');
  await reset();
}

// Favourites back to the seeded baseline (before every run): the reference getArticle query loads every
// favouriting user, so its cost grows with favourites; resetting keeps runs comparable.
let fanNext: number[] = [];
async function reset() {
  await prisma.$executeRawUnsafe('DELETE FROM "_UserFavorites"');
  const arts = await prisma.article.findMany({ select: { id: true, slug: true } });
  const fans = await prisma.user.findMany({ where: { username: { startsWith: 'fan' } }, select: { id: true, username: true } });
  const fanId = new Map(fans.map((f) => [Number(f.username.slice(3)), f.id]));
  const rows: string[] = [];
  for (const a of arts) {
    const n = Number(a.slug.slice(1));
    if (n > N) continue;
    for (let k = 1; k <= baseline(n); k++) rows.push(`(${a.id}, ${fanId.get(k)})`);
  }
  if (rows.length) await prisma.$executeRawUnsafe(`INSERT INTO "_UserFavorites" ("A", "B") VALUES ${rows.join(',')}`);
  fanNext = Array.from({ length: N + 1 }, (_, n) => (n ? baseline(n) + 1 : 0));
  fanIds = fanId;
}
let fanIds = new Map<number, number>();

async function counts() {
  const r: any[] = await prisma.$queryRawUnsafe(
    `SELECT a.slug, COUNT(f."B")::int AS c FROM "Article" a LEFT JOIN "_UserFavorites" f ON f."A" = a.id GROUP BY a.slug`);
  const out: Record<string, number> = {};
  for (const x of r) { const n = Number(x.slug.slice(1)); if (n <= N) out[String(n)] = x.c; }
  return out;
}

async function purge(n: number) {
  if (config.inv === 'push') await redis.del(`article:a${n}`);
  if (config.invNext) await fetch(`${process.env.WEB_URL || 'http://web:3000'}/api/revalidate?tag=p${n}-l1`).catch(() => {});
}

// ---- writer: same processes as the catalogue (api/server.js) ----
function rng(seed: number) { return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function* schedule(s: any, rand: () => number) {
  const exp = (rate: number) => (-Math.log(1 - rand()) / rate) * 1000;
  if (!s.kind || s.kind === 'poisson') { let t = 0; for (;;) { t += exp(s.lam); yield t; } }
  if (s.kind === 'periodic') { const d = 1000 / s.lam; let t = rand() * d; for (;;) { yield t; t += d; } }
  if (s.kind === 'onoff') {
    let on = rand() < s.onMean / (s.onMean + s.offMean), t = 0, end = exp(1 / (on ? s.onMean : s.offMean));
    for (;;) {
      if (on) { const a = t + exp(s.onRate); if (a < end) { t = a; yield t; continue; } }
      t = end; on = !on; end = t + exp(1 / (on ? s.onMean : s.offMean));
    }
  }
  if (s.kind === 'trace') { for (const t of s.times) yield t; return; }
}
const cum = (() => { const w = POP.map((p) => p.views); const tot = w.reduce((a, b) => a + b, 0); let c = 0; return w.map((x) => (c += x / tot)); })();
let writer: NodeJS.Timeout | null = null;
function startWriter(spec: any) {
  const rand = rng(spec.seed); const draws = schedule(spec, rand); const t0 = Date.now(); let seq = 0;
  const next = () => {
    const it = draws.next(); if (it.done) { writer = null; return; }
    const wait = Math.max(0, (it.value as number) - (Date.now() - t0));
    const u = rand(); const n = 1 + cum.findIndex((c) => u < c);          // article by popularity
    writer = setTimeout(async () => {
      const fan = fanIds.get(fanNext[n]++);
      const art = await favoriteArticle(`a${n}`, fan as number);       // the application's own write path
      const committed = Date.now(); let purgedAt = null;
      if (config.inv === 'push' || config.invNext) { await purge(n); purgedAt = Date.now(); }
      fs.appendFileSync(WRITES_LOG, JSON.stringify({ runId: config.runId, seq: seq++, productId: n, page: n, stock: art.favoritesCount, committed, purgedAt }) + '\n');
      if (writer) next();
    }, wait);
  };
  next();
}

const app = express();
app.use(cors());
app.use(bodyParser.json({ limit: '5mb' }));

// Redis read-through and logging for article reads (the only path the workload measures).
app.get('/api/articles/:slug', async (req, res, next) => {
  if (req.params.slug === 'feed') return next();
  const t0 = performance.now(); const key = `article:${req.params.slug}`;
  let outcome = config.redis ? 'miss' : 'off';
  const done = (body: any, dbMs: number | null) => {
    const respId = randomUUID();
    res.set('cache-control', 'no-store'); res.set('timing-allow-origin', '*');
    res.json({ respId, ...body });
    emit({ ts: Date.now(), runId: config.runId, reqId: req.query.rid || null, caller: req.query.caller || 'unknown', key, respId,
      redis: outcome, dbMs, totalMs: performance.now() - t0, rows: 1 });
  };
  if (config.redis) {
    const cached = await redis.get(key);
    if (cached) { outcome = 'hit'; return done(JSON.parse(cached), null); }
  }
  const d0 = performance.now(); const json = res.json.bind(res);
  (res as any).json = (body: any) => {
    (res as any).json = json;
    if (res.statusCode !== 200) return json(body);
    const dbMs = performance.now() - d0;
    const fin = () => done(body, dbMs);
    if (config.redis) redis.set(key, JSON.stringify(body), { EX: config.ttl }).then(fin, fin); else fin();
    return res;
  };
  next();
});

app.get('/__admin/config', (_req, res) => res.json(config));
app.post('/__admin/config', async (req, res) => {
  Object.assign(config, req.body || {});
  if (req.body?.flushRedis) await redis.flushAll();
  delete config.flushRedis;
  res.json(config);
});
app.post('/__admin/writes', (req, res) => {
  if (writer) { clearTimeout(writer); writer = null; }
  if (req.body?.lam || req.body?.kind === 'trace') startWriter(req.body);
  config.writes = req.body?.lam || req.body?.kind === 'trace' ? { ...req.body, times: req.body.times ? req.body.times.length : undefined } : null;
  res.json({ writes: config.writes });
});
app.get('/__admin/stock', async (_req, res) => res.json({ at: Date.now(), stock: await counts() }));
app.post('/__admin/reset', async (_req, res) => { await reset(); res.json({ at: Date.now(), stock: await counts() }); });

app.use(routes);
// The reference implementation's error handler (src/main.ts), unchanged in behaviour.
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  if (err && err.name === 'UnauthorizedError') return res.status(401).json({ status: 'error', message: 'missing authorization credentials' });
  if (err && err.errorCode) return res.status(err.errorCode).json(err.message);
  if (err) return res.status(500).json(err.message);
});

(async () => {
  await redis.connect();
  await seed();
  if (!fanIds.size) await reset();
  app.listen(Number(process.env.PORT || 5001), () => console.info('conduit bench up'));
})();
