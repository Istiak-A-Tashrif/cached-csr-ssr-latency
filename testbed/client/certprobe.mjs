// v9 diagnosis: does certificate handling add round trips before a TLS connection?
// usage (client container): node certprobe.mjs <base https url> <root.crt path> <loads>
// Variant "ctx": Playwright context ignoreHTTPSErrors (as in v9 runs).
// Variant "spki": Chromium --ignore-certificate-errors-spki-list with the Caddy root key, so the
// chain is accepted during verification (no certificate-error path).
import { chromium } from "/opt/runner/node_modules/playwright/index.mjs";
import crypto from "node:crypto";
import fs from "node:fs";

const [base, rootPath, loadsArg] = process.argv.slice(2);
const loads = Number(loadsArg || 5);
import tls from "node:tls";
const hash = (der) => crypto.createHash("sha256")
  .update(new crypto.X509Certificate(der).publicKey.export({ type: "spki", format: "der" })).digest("base64");
// Keys of every certificate the edge serves (leaf + intermediate) plus the root.
const chain = await new Promise((res, rej) => {
  const u = new URL(base);
  const s = tls.connect({ host: u.hostname, port: +u.port, servername: u.hostname, rejectUnauthorized: false }, () => {
    const out = []; let c = s.getPeerCertificate(true); const seen = new Set();
    while (c && c.raw && !seen.has(c.fingerprint256)) { seen.add(c.fingerprint256); out.push(c.raw); c = c.issuerCertificate; }
    s.end(); res(out);
  });
  s.on("error", rej);
});
const spki = [...chain.map(hash), hash(fs.readFileSync(rootPath))].join(",");

async function variant(name) {
  const args = name === "spki" ? [`--ignore-certificate-errors-spki-list=${spki}`] : [];
  const browser = await chromium.launch({ args });
  const out = [];
  for (let i = 0; i < loads; i++) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: name === "ctx" });
    const page = await ctx.newPage();
    await page.goto(`${base}/csr?page=199&limit=25&a=certprobe-${name}-${i}`, { waitUntil: "load" });
    await page.waitForSelector("[data-vis]", { timeout: 60000 });
    out.push(await page.evaluate(() => {
      const n = performance.getEntriesByType("navigation")[0];
      const api = performance.getEntriesByType("resource").find((e) => e.name.includes("/api/products"));
      const ph = (e) => e && { preConnect: e.connectStart - e.startTime, handshake: e.connectEnd - e.connectStart, ttfb: e.responseStart - e.requestStart, proto: e.nextHopProtocol };
      return { doc: ph(n), api: ph(api), vis: (window.__vis[0] || {}).frame };
    }));
    await ctx.close();
  }
  await browser.close();
  const m = (f) => out.map(f).filter((x) => x != null).reduce((a, b) => a + b, 0) / out.length;
  console.log(JSON.stringify({ variant: name, loads, doc: { preConnect: m((o) => o.doc.preConnect), handshake: m((o) => o.doc.handshake), ttfb: m((o) => o.doc.ttfb), proto: out[0].doc.proto },
    api: { preConnect: m((o) => o.api?.preConnect), handshake: m((o) => o.api?.handshake) }, visible: m((o) => o.vis) }));
}
for (const v of ["ctx", "spki"]) await variant(v);
