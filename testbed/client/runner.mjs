// Browser runner (inside the client container).
// usage: node runner.mjs <config.json>
//   { mode: "csr"|"ssr", runId, out, limit, users: [[page, page, ...], ...] }
// Each user is a fresh browser context (empty TanStack and HTTP caches): a hard
// initial load of its first page, then same-route navigations through the rest.
// Primary endpoint per action: data-visible time = end of the first frame after
// the first data row enters the DOM (window.__vis, see web/src/app/layout.tsx).
// Also recorded: DOM-insertion time, Element Timing (secondary), and for the
// initial load TTFB, FCP and time to interactive (hydration).
// Installed in the image (ESM ignores NODE_PATH, so import by path).
import { chromium } from "/opt/runner/node_modules/playwright/index.mjs";
import fs from "fs";

const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const { mode, runId, out, users } = cfg;
const limit = cfg.limit || 25;
const base = cfg.base || "http://web:3000";
const timeoutMs = cfg.timeoutMs || 30000;

// Concurrency: several runner processes share one run; userOffset keeps user ids global.
const userOffset = cfg.userOffset || 0;
const write = (rec) => fs.appendFileSync(out, JSON.stringify({ runId, mode, ...rec, user: rec.user === undefined ? undefined : rec.user + userOffset }) + "\n");

// Wait until view `id` entered the DOM at/after `after` (ms since timeOrigin)
// and its next frame completed. Returns { dom, frame, et }.
async function visibleAfter(page, id, after) {
  if (cfg.evented) {
    // Item 6: one in-page wait (cheap 10 ms in-page check, no CDP round trip per poll), so
    // the harness adds almost no client CPU while N browsers share one pinned core.
    return page.evaluate(([id, after, timeoutMs]) => new Promise((resolve, reject) => {
      const t0 = Date.now();
      const check = () => {
        const v = (window.__vis || []).find((e) => e.id === id && e.dom >= after && e.frame !== null);
        if (v) { clearInterval(iv); resolve({ dom: v.dom, frame: v.frame, et: null }); }
        else if (Date.now() - t0 > timeoutMs) { clearInterval(iv); reject(new Error(`timeout waiting for ${id}`)); }
      };
      const iv = setInterval(check, 10); check();
    }), [id, after, timeoutMs]);
  }
  const handle = await page.waitForFunction(
    ([id, after, snap]) => {
      const v = (window.__vis || []).find((e) => e.id === id && e.dom >= after && e.frame !== null);
      if (!v) return null;
      const et = (window.__et || []).find((e) => e.id === id && e.t >= v.dom - 20);
      const r = { dom: v.dom, frame: v.frame, et: et ? et.t : null };
      // Item 8: rows shown at insertion (product id, stock) and the epoch display time.
      if (snap) Object.assign(r, { rows: v.rows, wall: performance.timeOrigin + v.dom, resp: v.resp });
      return r;
    },
    [id, after, !!cfg.snap],
    { timeout: timeoutMs, polling: 5 }
  );
  return handle.jsonValue();
}

// TanStack misses (queryFn calls) for `key` since `after`, with their request ids.
const tqSince = (page, key, after) =>
  page.evaluate(([key, after]) => (window.__tq || []).filter((e) => e.key === key && e.t >= after).map((e) => e.rid), [key, after]);

// Network resources fetched since `after` (Resource Timing; navigation entry for the document).
const resources = (page, after) =>
  page.evaluate((after) => {
    const pick = (e) => ({
      name: e.name.replace(location.origin, ""), type: e.initiatorType || "navigation",
      start: e.startTime, connectStart: e.connectStart, connectEnd: e.connectEnd,
      requestStart: e.requestStart, responseStart: e.responseStart, responseEnd: e.responseEnd,
      transfer: e.transferSize, body: e.encodedBodySize, proto: e.nextHopProtocol,
      newConn: e.connectEnd > e.connectStart,
    });
    const nav = performance.getEntriesByType("navigation").filter((e) => after === 0).map(pick);
    return nav.concat(performance.getEntriesByType("resource").filter((e) => e.startTime >= after).map(pick));
  }, after);

// v9b: trust the edge's certificate chain by key (--ignore-certificate-errors-spki-list)
// instead of Playwright's ignoreHTTPSErrors, which costs 2 RTT before every new TLS
// connection (certprobe.mjs). cfg.pinOrigins: https origins whose served chains are pinned.
async function chainSpki(origin) {
  const { default: tls } = await import("node:tls");
  const { default: crypto } = await import("node:crypto");
  const u = new URL(origin);
  const raws = await new Promise((res, rej) => {
    const s = tls.connect({ host: u.hostname, port: +u.port, servername: u.hostname, rejectUnauthorized: false }, () => {
      const out = []; const seen = new Set(); let c = s.getPeerCertificate(true);
      while (c && c.raw && !seen.has(c.fingerprint256)) { seen.add(c.fingerprint256); out.push(c.raw); c = c.issuerCertificate; }
      s.end(); res(out);
    });
    s.on("error", rej);
  });
  return raws.map((der) => crypto.createHash("sha256")
    .update(new crypto.X509Certificate(der).publicKey.export({ type: "spki", format: "der" })).digest("base64"));
}
const pins = cfg.pinTls ? [...new Set((await Promise.all(cfg.pinOrigins.map(chainSpki))).flat())] : [];
const browser = await chromium.launch(pins.length ? { args: [`--ignore-certificate-errors-spki-list=${pins.join(",")}`] } : {});
const ctxOpts = { ignoreHTTPSErrors: !cfg.pinTls };
// Experiment Q: route variant (e.g. "h" -> /csrh, /ssrh). Experiment R: CPU throttling (slow
// devices) on every page via Emulation.setCPUThrottlingRate.
const route = cfg.route || "";
const probePage = cfg.probePage || 199;
async function newPage(ctx) {
  const page = await ctx.newPage();
  if (cfg.cpuRate && cfg.cpuRate !== 1) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: cfg.cpuRate });
  }
  return page;
}
// Browser warm-up on a page no workload uses (199): pays process/JIT cold start
// without touching any cache entry under test. Not recorded.
if (cfg.warm) {
  // Warm-up page: valid for this page size and drawn by no workload (199 at 25 rows; 95 at 50 rows).
  // Not measured; retried with a fresh context (a throttled first load can stall, experiment R2).
  const wp = cfg.warmPage || 199;
  for (let a = 1; ; a++) {
    const ctx = await browser.newContext(ctxOpts); const page = await newPage(ctx);
    try {
      await page.goto(`${base}/${mode}${route}?page=${wp}&limit=${limit}&a=warmup`, { waitUntil: "commit" });
      await visibleAfter(page, `data-p${wp}-l${limit}`, 0);
      await ctx.close(); break;
    } catch (e) { await ctx.close().catch(() => {}); if (a >= 3) throw e; }
  }
}
// Race probe (v7): K fresh CSR initial loads of page 199 (used by no workload); report the
// share whose largest JS chunk ran on a NEW connection. Printed as the last stdout line.
if (cfg.probe) {
  let onNew = 0, n = 0;
  for (let k = 0; k < cfg.probe; k++) {
    const ctx = await browser.newContext(ctxOpts); const page = await newPage(ctx);
    try {
      await page.goto(`${base}/csr${route}?page=${probePage}&limit=${limit}&a=probe`, { waitUntil: "commit" });
      await visibleAfter(page, `data-p${probePage}-l${limit}`, 0);
      const res = await resources(page, 0);
      const sc = res.filter((r) => r.type === "script" || r.type === "link");
      const big = sc.reduce((a, b) => (b.transfer > a.transfer ? b : a));
      onNew += big.newConn ? 1 : 0; n++;
      // modelH3: keep the probe loads' resource timings (bundle time on this path).
      if (cfg.probeLog) fs.appendFileSync(cfg.probeLog, JSON.stringify({ runId, k, res }) + "\n");
    } catch (e) { /* a failed probe load is skipped */ }
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify({ raceP: n ? onNew / n : null, probes: n }));
  process.exit(0);
}
// Item 6 (modelP2): launch barrier. Every process launches and warms its browser first, then
// starts its sessions at cfg.startAt (process g at startAt + g * stagger). Process 0 records
// the client cgroup's CPU at the barrier, so launches are excluded from measured demand.
if (cfg.startAt) {
  const wait = cfg.startAt - Date.now();
  if (wait < 0) console.error(`barrier missed by ${-wait} ms`);
  else await new Promise((r) => setTimeout(r, wait));
  if (cfg.cpuMark) {
    const usec = Number(fs.readFileSync("/sys/fs/cgroup/cpu.stat", "utf8").match(/usage_usec (\d+)/)[1]);
    fs.appendFileSync("/results/cpumarks.jsonl", JSON.stringify({ runId, at: Date.now(), usageUsec: usec, late: Math.max(0, -wait) }) + "\n");
  }
}
try {
  for (let u = 0; u < users.length; u++) {
    const seq = users[u];
    const ctx = await browser.newContext(ctxOpts);
    const page = await newPage(ctx);
    const seen = new Set();
    let step = 0;
    try {
      // Initial load (hard navigation).
      const p0 = seq[0];
      const aid0 = `${runId}.u${u + userOffset}.s0`;
      await page.goto(`${base}/${mode}${route}?page=${p0}&limit=${limit}&a=${aid0}`, { waitUntil: "commit" });
      const v = await visibleAfter(page, `data-p${p0}-l${limit}`, 0);
      await page.waitForFunction(() => typeof window.__nav === "function", null, { timeout: timeoutMs });
      const init = await page.evaluate(([id]) => {
        const n = performance.getEntriesByType("navigation")[0];
        const fcp = performance.getEntriesByName("first-contentful-paint")[0];
        const c = (window.__commits || []).find((c) => c.id === id);
        return { ttfb: n.responseStart, fcp: fcp?.startTime ?? null, interactiveMs: c ? c.t : null };
      }, [`data-p${p0}-l${limit}`]);
      write({
        user: u, step: 0, aid: aid0, action: "initial", page: p0, revisit: false,
        latencyMs: v.frame, domMs: v.dom, etMs: v.et, ...init, ...(cfg.snap ? { rows: v.rows, wall: v.wall, resp: v.resp } : {}),
        tqRids: await tqSince(page, `p${p0}-l${limit}`, 0),
        res: cfg.resources ? await resources(page, 0) : undefined,
      });
      seen.add(p0);

      // Same-route navigations.
      for (step = 1; step < seq.length; step++) {
        const p = seq[step];
        const aid = `${runId}.u${u + userOffset}.s${step}`;
        const markT = await page.evaluate(([p, l, aid]) => {
          window.__nav(p, l, aid);
          return performance.getEntriesByName(`nav-p${p}-l${l}`).at(-1).startTime;
        }, [p, limit, aid]);
        const nv = await visibleAfter(page, `data-p${p}-l${limit}`, markT);
        write({
          user: u, step, aid, action: "nav", page: p, revisit: seen.has(p),
          latencyMs: nv.frame - markT, domMs: nv.dom - markT, etMs: nv.et === null ? null : nv.et - markT,
          ...(cfg.snap ? { rows: nv.rows, wall: nv.wall, resp: nv.resp } : {}),
          tqRids: await tqSince(page, `p${p}-l${limit}`, markT),
          res: cfg.resources ? await resources(page, markT) : undefined,
        });
        seen.add(p);
      }
    } catch (e) {
      write({
        user: u, step, error: String(e.message || e).split("\n")[0],
        debug: await page.evaluate(() => ({ vis: window.__vis, url: location.href })).catch(() => null),
      });
    }
    await ctx.close();
  }
} finally {
  await browser.close();
}
