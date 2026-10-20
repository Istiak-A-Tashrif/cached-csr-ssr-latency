// Host-side harness. Runs configurations against the docker testbed.
//   node harness.mjs smoke            quick end-to-end check, all 8 cache configs, RTT 0
//   node harness.mjs calibrate <rtt>  apply RTT on client links and measure it
import { execSync, spawn } from "child_process";
import fs from "fs";

const sh = (cmd, opts = {}) =>
  execSync(cmd, { cwd: import.meta.dirname, stdio: ["ignore", "pipe", "pipe"], encoding: "utf8", ...opts }).trim();
const dc = (args, env = {}) => sh(`docker compose ${args}`, { env: { ...process.env, ...env } });
const exec = (svc, cmd) =>
  REMOTE && SERVER_SIDE.has(svc) ? remote(`docker compose exec -T ${svc} ${cmd}`) : dc(`exec -T ${svc} ${cmd}`);

// HTTP/2 mode (item 4): the browser talks only to the Caddy edge (TLS + h2).
const H2 = process.env.PROTO === "h2";
// HOME mode (item 5): browser on this Mac, server stack on a remote host (REMOTE_SERVER,
// e.g. "server") reached over the home internet on its published ports 13000/15001.
const REMOTE = process.env.REMOTE_SERVER || "";
const REMOTE_IP = process.env.REMOTE_IP || "";
const HOME_IP = process.env.HOME_IP || "";
const FRONT = H2 ? "edge" : "web";            // host the browser connects to for pages
const WEB_PORT = REMOTE ? 13000 : 3000, API_PORT = REMOTE ? 15001 : 5001;
const BASE_WEB = H2 ? "https://edge:3000" : `http://web:${WEB_PORT}`;
const BASE_API = H2 ? "https://edge:5001" : `http://api:${API_PORT}`;
const SERVER_SIDE = new Set(["web", "api", "db", "redis", "edge"]);
const RCF = process.env.REMOTE_COMPOSE || "docker-compose.yml:docker-compose.server.yml:docker-compose.server-home.yml";
// Remote docker: sudo password is passed on stdin (never on a command line or in a file).
const shq = (x) => `'${String(x).replace(/'/g, `'\\''`)}'`;
function remote(inner, env = "") {
  const cmd = `cd /srv/cachebed && export COMPOSE_FILE=${RCF} ${env} && ${inner}`;
  return execSync(`ssh -o BatchMode=yes ${REMOTE} ${shq(`sudo -S -p '' sh -c ${shq(cmd)}`)}`,
    { input: `${process.env.REMOTE_SUDO}\n`, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }).trim();
}
const NODE_TLS = H2 ? "NODE_TLS_REJECT_UNAUTHORIZED=0 " : "";

// One-way delay = RTT/2 on each end of a link, so added RTT is not double-counted.
function shapeLink(a, b, rttMs, rate = "") {
  exec(a, `netem.sh set ${b} ${rttMs / 2} ${rate}`);
  exec(b, `netem.sh set ${a} ${rttMs / 2} ${rate}`);
}
export function setNetwork({ clientRtt = 0, internalRtt = 0, rate = "" }) {
  const relay = process.env.RELAY_IP;
  if (REMOTE) {
    // Home path: real latency; 10 Mbit/s cap on the client's and each server's egress
    // toward the other side; optional emulated extra delay split across both ends.
    exec("client", `netem.sh set ${REMOTE_IP} ${clientRtt / 2} ${rate}`);
    for (const svc of ["web", "api"]) exec(svc, `netem.sh set ${HOME_IP} ${clientRtt / 2} ${rate}`);
  } else if (relay) {
    // Real-network mode: client<->server traffic goes via the relay's IP; latency is
    // real (no added delay), only the 10 Mbit/s bottleneck is kept on each sender.
    // Optional emulated delay ON TOP of the real path (v7 fresh conditions): RTT/2 on the
    // client's egress and RTT/2 on each server's egress toward the relay.
    for (const svc of H2 ? ["client", "edge"] : ["client", "web", "api"]) exec(svc, `netem.sh set ${relay} ${clientRtt / 2} ${rate}`);
  } else if (H2) {
    shapeLink("client", "edge", clientRtt, rate);   // only client<->edge is shaped
  } else {
    shapeLink("client", "web", clientRtt, rate);
    shapeLink("client", "api", clientRtt, rate);
  }
  shapeLink("web", "api", internalRtt);
}

function ping(from, to) {
  const out = exec(from, `ping -c 5 -i 0.2 -q ${to}`);
  const m = out.match(/= [\d.]+\/([\d.]+)\//);
  return m ? Number(m[1]) : null;
}
// TCP RTT (median connect time) per link: the instrument closest to app traffic.
const tcp = (from, host, port) => Number(exec(from, `node /usr/local/lib/tcprtt.mjs ${host} ${port} 11`));
export const tcpRtt = () => ({
  client_web: tcp("client", FRONT, H2 ? 3000 : WEB_PORT),
  client_api: tcp("client", H2 ? "edge" : "api", H2 ? 5001 : API_PORT),
  web_api: tcp("web", "api", 5001),
});
export const measuredRtt = () => ({
  client_web: ping("client", FRONT),
  client_api: ping("client", H2 ? "edge" : "api"),
  web_api: ping("web", "api"),
});

// Body is base64-encoded to avoid shell quoting; the applied config is read back
// and verified so a failed toggle can never silently mislabel a run.
function apiConfig(body) {
  if (REMOTE) {
    const out = sh(`curl -s -m 15 -X POST -H 'content-type: application/json' --data ${shq(JSON.stringify(body))} http://${REMOTE_IP}:${API_PORT}/__admin/config`);
    const applied = JSON.parse(out);
    for (const [k, v] of Object.entries(body))
      if (k !== "flushRedis" && applied[k] !== v) throw new Error(`api config ${k}=${applied[k]}, wanted ${v}`);
    return applied;
  }
  const b64 = Buffer.from(JSON.stringify(body)).toString("base64");
  const js =
    `fetch("http://localhost:5001/__admin/config",{method:"POST",headers:{"content-type":"application/json"},` +
    `body:Buffer.from("${b64}","base64").toString()}).then(r=>r.text()).then(t=>console.log(t))`;
  const applied = JSON.parse(exec("api", `node -e '${js}'`));
  for (const [k, v] of Object.entries(body))
    if (k !== "flushRedis" && applied[k] !== v) throw new Error(`api config ${k}=${applied[k]}, wanted ${v}`);
  return applied;
}

// Item 8: other admin endpoints (local stack only), JSON in/out.
function apiCall(path, body) {
  const b64 = Buffer.from(JSON.stringify(body ?? null)).toString("base64");
  const init = body === undefined ? "" : `,{method:"POST",headers:{"content-type":"application/json"},body:Buffer.from("${b64}","base64").toString()}`;
  return JSON.parse(exec("api", `node -e 'fetch("http://localhost:5001${path}"${init}).then(r=>r.text()).then(t=>console.log(t))'`));
}

function waitForWeb() {
  for (let i = 0; i < 60; i++) {
    try {
      exec("client", `sh -c "${NODE_TLS}node -e \\"fetch('${BASE_WEB}/csr').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\\""`);
      return;
    } catch { sh("sleep 1"); }
  }
  throw new Error("web did not become ready");
}

// Cold start for a configuration: fresh web container (empty Next data cache),
// Redis flushed, then network shaping re-applied (recreating web drops its qdisc).
// Warm-up uses page 199, which no workload draws (revisit: 1-8, reuse: 1-50),
// so JIT/cold-start cost is paid without touching any cache entry under test.
const WARMUP_PAGE = 199;
function warmup() {
  exec("client", `sh -c "${NODE_TLS}node -e \\"Promise.all([fetch('${BASE_WEB}/ssr?page=${WARMUP_PAGE}&limit=25&a=warmup'),fetch('${BASE_WEB}/csr?page=${WARMUP_PAGE}&limit=25'),fetch('${BASE_API}/api/products?page=${WARMUP_PAGE}&limit=25&caller=warmup'),fetch('${BASE_WEB}/ssrh?page=49&limit=100&a=warmup'),fetch('${BASE_WEB}/csrh?page=49&limit=100')]).then(rs=>Promise.all(rs.map(r=>r.text())))\\""`);
}
// fe: boolean (off/on) or an item-8 mode string ("ttl" | "push"); webEnv/apiExtra: item-8 knobs.
export function configure({ fe, be, net, runId, warm = false, webEnv = {}, apiExtra = {} }) {
  const FE_CACHE = typeof fe === "string" ? fe : fe ? "on" : "off";
  if (REMOTE) remote("docker compose up -d --force-recreate --no-deps web", `FE_CACHE=${FE_CACHE}`);
  else dc(`up -d --force-recreate --no-deps web`, { FE_CACHE, ...webEnv });
  // Defaults reset on every configuration (experiment X's dbDelayMs once leaked into Q and R).
  apiConfig({ redis: be, flushRedis: true, runId: warm ? "warmup" : runId, dbDelayMs: 0, inv: "ttl", invNext: false, ...apiExtra });
  waitForWeb();
  if (warm) {
    // Warm-up is not measured; retry so a transient connect timeout on a real path cannot
    // abort a whole pipeline (v9b relay, 20 Oct 2026).
    for (let k = 0; k < 2; k++) for (let a = 1; ; a++) { try { warmup(); break; } catch (e) { if (a >= 3) throw e; sh("sleep 5"); } }
    apiConfig({ runId });
  }
  setNetwork(net);
}

export function runBrowser(opts) {
  opts = { base: BASE_WEB, ...opts };
  const name = `cfg-${opts.runId}.json`;
  fs.writeFileSync(`${import.meta.dirname}/client/${name}`, JSON.stringify(opts));
  try {
    return exec("client", `node runner.mjs /runner/${name}`);
  } finally {
    fs.rmSync(`${import.meta.dirname}/client/${name}`, { force: true });
  }
}

// Concurrency: N runner processes in parallel (closed loop, no think time), users split
// round-robin; each process keeps global user ids via userOffset (contiguous blocks).
export function runBrowserParallel(opts, n) {
  const groups = Array.from({ length: n }, () => []);
  const blocks = [];
  const per = Math.ceil(opts.users.length / n);
  for (let g = 0; g < n; g++) blocks.push(opts.users.slice(g * per, (g + 1) * per));
  const names = blocks.map((users, g) => {
    const name = `cfg-${opts.runId}-g${g}.json`;
    const bar = opts.barrier ? { startAt: opts.startAt + g * (opts.stagger || 0), cpuMark: g === 0 } : {};
    fs.writeFileSync(`${import.meta.dirname}/client/${name}`, JSON.stringify({ base: BASE_WEB, ...opts, users, userOffset: g * per, ...bar }));
    return name;
  });
  try {
    // opts.stagger (ms): process g starts g * stagger later, so sessions do not begin as one burst.
    // opts.barrier (modelP2): all processes launch at once and start sessions at a common time.
    const st = opts.stagger || 0;
    if (opts.barrier) return exec("client", `sh -c "${names.map((nm) => `node runner.mjs /runner/${nm} &`).join(" ")} wait"`);
    return exec("client", `sh -c "${names.map((nm, g) => `(sleep ${(g * st / 1000).toFixed(3)}; node runner.mjs /runner/${nm}) &`).join(" ")} wait"`);
  } finally {
    for (const nm of names) fs.rmSync(`${import.meta.dirname}/client/${nm}`, { force: true });
  }
}

// ---- workloads (seeded, reproducible) ----
function rng(seed) { // mulberry32
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function zipfSampler(n, alpha, rand) {
  const w = Array.from({ length: n }, (_, i) => 1 / Math.pow(i + 1, alpha));
  const cdf = []; let acc = 0;
  for (const x of w) cdf.push((acc += x));
  return () => { const r = rand() * acc; return cdf.findIndex((c) => c >= r) + 1; };
}
// Pages are drawn per step; consecutive duplicates are redrawn (a navigation
// to the page already shown is not an action).
export function makeWorkload({ users, sessionLen, pages, alpha, seed }) {
  const rand = rng(seed);
  const draw = zipfSampler(pages, alpha, rand);
  return Array.from({ length: users }, () => {
    const seq = [];
    while (seq.length < sessionLen) { const p = draw(); if (p !== seq.at(-1)) seq.push(p); }
    return seq;
  });
}
export const WORKLOADS = {
  // High reuse: skewed popularity over 50 pages.
  reuse: { users: 12, sessionLen: 6, pages: 50, alpha: 1.0 },
  // Low reuse: uniform over all 200 pages (5,000 products / 25).
  spread: { users: 12, sessionLen: 6, pages: 200, alpha: 0 },
  // Item 6 (concurrency): DB-bound sessions over deep pages (OFFSET 2,000-4,000 at 50 rows),
  // uniform popularity; page numbers are offset into 40-80 by the harness (pageBase).
  deep: { users: 12, sessionLen: 8, pages: 40, alpha: 0 },
  // Week 3 prospective test: long sessions over few pages -> frequent revisits.
  revisit: { users: 12, sessionLen: 12, pages: 8, alpha: 0.6 },
};

// Item 6: cumulative CPU time (s) per container from its cgroup (cpu.stat usage_usec).
function cpuUsage() {
  const u = (svc) => Number(exec(svc, "cat /sys/fs/cgroup/cpu.stat").match(/usage_usec (\d+)/)[1]) / 1e6;
  return Object.fromEntries(["client", "web", "api", "redis", "db"].map((k) => [k, u(k)]));
}

// Run an explicit list of configs (cold start each), logging measured RTT.
let currentRunId = null;
export function runConfigs(list, { out, runsFile, tag, predictHook = null }) {
  // RESUME=1: skip runs already in the runs file; first drop browser records of runs that never
  // completed (an aborted run has actions but no runs-file line).
  let done = null;
  if (process.env.RESUME === "1") {
    const rf = `${import.meta.dirname}/results/${runsFile}`, af = `${import.meta.dirname}/results/${out.split("/").pop()}`;
    done = new Set(fs.existsSync(rf) ? fs.readFileSync(rf, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).runId) : []);
    if (fs.existsSync(af)) fs.writeFileSync(af, fs.readFileSync(af, "utf8").split("\n").filter((l) => l && done.has(JSON.parse(l).runId)).join("\n") + "\n");
    console.log(`resume: ${done.size} runs already done`);
  }
  list.forEach((c, i) => {
    // RETRY_RUNS=1 (real paths): a run that throws (e.g. a connect timeout on a lossy path) is
    // logged to discarded-runs.jsonl and repeated once from configuration; its prediction is
    // rewritten before the repeat, and evaluators ignore log entries before the discard time.
    const attempt = () => {
      c.irtt ??= 0;
      const runId = currentRunId = `${tag}-s${c.seed}-${c.mode}-fe${+c.fe}-be${+c.be}-r${c.rtt}-i${c.irtt}-${c.wl}${c.initOnly ? "-init" : ""}${c.n > 1 ? `-n${c.n}` : ""}${c.levelTag ? `-${c.levelTag}` : ""}`;
      if (done && done.has(runId)) return;
      configure({ fe: c.fe, be: c.be, net: { clientRtt: c.rtt, internalRtt: c.irtt, rate: c.rate ?? "10mbit" }, runId, warm: !!c.warm });
      const rtt = measuredRtt();
      const tcpPre = c.warm ? tcpRtt() : null;
      // modelH2: request-level RTT (mean of keep-alive HTTP requests) before and after the run.
      const httpRtt = () => JSON.parse(exec("client", `node /runner/httprtt.mjs ${BASE_API} 30`).split("\n").at(-1));
      const httpPre = c.httpRtt ? httpRtt() : undefined;
      const users = makeWorkload({ ...WORKLOADS[c.wl], ...(c.nUsers ? { users: c.nUsers } : {}), ...(c.sessionLen ? { sessionLen: c.sessionLen } : {}), seed: c.seed * 1000 + c.wl.length })
        .map((seq) => seq.map((p) => p + (c.pageBase || 0)));
      // v7: measure the connection-race probability on this path before the run (CSR only),
      // under a separate runId so probe requests are never taken for the run's start.
      let raceP = null;
      if (c.probe && (c.mode === "csr" || c.probeLog)) {
        apiConfig({ runId: `${runId}-probe` });
        const name = `cfg-${runId}-probe.json`;
        fs.writeFileSync(`${import.meta.dirname}/client/${name}`, JSON.stringify({ mode: "csr", base: BASE_WEB, runId: `${runId}-probe`, out: "/results/probes.jsonl", users: [], limit: 25, probe: c.probe, ...(c.pinTls ? { pinTls: true, pinOrigins: [BASE_WEB, BASE_API] } : {}), ...(c.probeLog ? { probeLog: "/results/probeloads.jsonl" } : {}),
        ...(c.route ? { route: c.route, probePage: c.warmPage, limit: c.limit } : {}), ...(c.cpuRate ? { cpuRate: c.cpuRate } : {}), ...(c.timeoutMs ? { timeoutMs: c.timeoutMs } : {}) }));
        try { raceP = JSON.parse(exec("client", `node runner.mjs /runner/${name}`).split("\n").at(-1)).raceP; }
        finally { fs.rmSync(`${import.meta.dirname}/client/${name}`, { force: true }); }
        apiConfig({ runId });
      }
      // v8: measure path bandwidth before the run (same path as the browser's API calls).
      let bwBps = null;
      if (c.bwProbe) bwBps = JSON.parse(exec("client", `sh -c "${NODE_TLS}node /runner/bwprobe.mjs ${BASE_API} ${c.bwSizes || "8 32"}"`).split("\n").at(-1)).bwBps;
      // Prospective: the prediction for this run is written before the run starts.
      if (predictHook) predictHook({ runId, ...c, tcpPre, httpPre, users, raceP, bwBps });
      const t0 = Date.now();
      const pin = c.pinTls ? { pinTls: true, pinOrigins: [BASE_WEB, BASE_API] } : {};
      const bopts = { mode: c.mode, runId, out, users, limit: c.limit || 25, resources: !!c.resources, warm: !!c.warm, warmPage: c.warmPage, evented: !!c.evented, stagger: c.stagger, ...pin,
      ...(c.route ? { route: c.route } : {}), ...(c.cpuRate ? { cpuRate: c.cpuRate } : {}), ...(c.timeoutMs ? { timeoutMs: c.timeoutMs } : {}) };
      // calibP: idle CPU rate per container over 10 s, subtracted when demands are derived.
      let idleCpu;
      if (c.idle) { const a = cpuUsage(); sh("sleep 10"); const b = cpuUsage(); idleCpu = Object.fromEntries(Object.keys(a).map((k) => [k, (b[k] - a[k]) / 10])); }
      const cpu0 = c.cpu ? cpuUsage() : null;
      if (c.barrier) {
        // Launch time grows with the number of browsers sharing the client core.
        bopts.barrier = true; bopts.startAt = Date.now() + 5000 + 2500 * (c.n || 1);
        if (!(c.n > 1)) Object.assign(bopts, { startAt: bopts.startAt, cpuMark: true });
      }
      if (c.n && c.n > 1) runBrowserParallel(bopts, c.n); else runBrowser(bopts);
      const tEnd = Date.now();
      let cpu = c.cpu ? Object.fromEntries(Object.entries(cpuUsage()).map(([k, v]) => [k, v - cpu0[k]])) : undefined;
      let steadyMs;
      if (c.barrier) {
        // Client CPU counted from the barrier (launches and warm-ups excluded); servers whole run.
        const mark = fs.readFileSync(`${import.meta.dirname}/results/cpumarks.jsonl`, "utf8").trim().split("\n").map(JSON.parse).filter((m) => m.runId === runId).at(-1);
        steadyMs = tEnd - mark.at;
        const clientEnd = cpu0.client + cpu.client;
        cpu = { ...cpu, client: clientEnd - mark.usageUsec / 1e6, barrierLateMs: mark.late };
      }
      const tcpPost = c.warm ? tcpRtt() : null;
      const httpPost = c.httpRtt ? httpRtt() : undefined;
      fs.appendFileSync(`${import.meta.dirname}/results/${runsFile}`,
        JSON.stringify({ runId, ...c, rate: c.rate ?? "10mbit", measuredRtt: rtt, tcpPre, tcpPost, httpPre, httpPost, raceP, bwBps, users, wallMs: Date.now() - t0, steadyMs, cpu, idleCpu, order: i }) + "\n");
      console.log(`[${i + 1}/${list.length}] ${runId} ${((Date.now() - t0) / 1000).toFixed(0)}s rtt=${JSON.stringify(rtt)}`);
    };
    try { attempt(); }
    catch (e) {
      if (process.env.RETRY_RUNS !== "1") throw e;
      fs.appendFileSync(`${import.meta.dirname}/results/discarded-runs.jsonl`, JSON.stringify({ runId: currentRunId, at: new Date().toISOString(), reason: String(e.message || e).split("\n")[0].slice(0, 200) }) + "\n");
      console.log(`[${i + 1}/${list.length}] ${currentRunId} failed, repeating once: ${String(e.message || e).split("\n")[0].slice(0, 120)}`);
      // Remove the failed attempt's browser records (as the rerun command does); the repeat's
      // prediction line is appended later and supersedes the old one (last line per runId wins).
      const af = `${import.meta.dirname}/results/${out.split("/").pop()}`;
      if (fs.existsSync(af)) fs.writeFileSync(af, fs.readFileSync(af, "utf8").split("\n").filter((l) => l && JSON.parse(l).runId !== currentRunId).join("\n") + "\n");
      sh("sleep 60"); attempt();
    }
  });
}

const combos = (seeds, rtts, irtts = [0], extra = {}) => {
  const l = [];
  for (const seed of seeds) for (const rtt of rtts) for (const irtt of irtts) for (const mode of ["csr", "ssr"])
    for (const [fe, be] of [[false, false], [true, true]]) l.push({ seed, rtt, irtt, mode, fe, be, wl: "revisit", ...extra });
  return l;
};

function shuffle(arr, rand) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

// Stage A pilot: modes x cache combos x client RTT x workload, randomized order per seed.
export function pilot(seed, { rtts = [0, 170], rate = "10mbit", out = "/results/pilot.jsonl" } = {}) {
  const configs = [];
  for (const mode of ["csr", "ssr"])
    for (const fe of [false, true])
      for (const be of [false, true])
        for (const rtt of rtts)
          for (const wl of Object.keys(WORKLOADS)) configs.push({ mode, fe, be, rtt, wl });
  const order = shuffle(configs, rng(seed * 7919));
  order.forEach((c, i) => {
    const runId = `s${seed}-${c.mode}-fe${+c.fe}-be${+c.be}-r${c.rtt}-${c.wl}`;
    const net = { clientRtt: c.rtt, internalRtt: 0, rate };
    configure({ fe: c.fe, be: c.be, net, runId });
    const rtt = measuredRtt();
    // The same seed gives the same user sessions for every config (paired design).
    const users = makeWorkload({ ...WORKLOADS[c.wl], seed: seed * 1000 + c.wl.length });
    const t0 = Date.now();
    runBrowser({ mode: c.mode, runId, out, users, limit: 25 });
    fs.appendFileSync(
      `${import.meta.dirname}/results/pilot-runs.jsonl`,
      JSON.stringify({ runId, seed, ...c, rate, measuredRtt: rtt, users, wallMs: Date.now() - t0, order: i }) + "\n"
    );
    console.log(`[${i + 1}/${order.length}] ${runId} ${((Date.now() - t0) / 1000).toFixed(0)}s rtt=${JSON.stringify(rtt)}`);
  });
}

const [, , cmd, arg, arg2] = process.argv;
// Keep the Mac awake while the harness runs: a sleep mid-run contaminated one run (v5).
if (cmd && process.platform === "darwin")
  spawn("caffeinate", ["-i", "-s", "-w", String(process.pid)], { detached: true, stdio: "ignore" }).unref();
if (cmd === "real8b" || cmd === "rep8b") {
  // v8b fresh tests (HTTP/1.1 relay): real + 10 ms uncapped; real + 40 ms capped at 15 Mbit/s.
  if (!process.env.RELAY_IP) throw new Error(`${cmd} needs RELAY_IP and the relay compose override`);
  if (!fs.existsSync(`${import.meta.dirname}/results/model8b.frozen.json`)) throw new Error("freeze model8b first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, add, rate] = cmd === "real8b" ? [[261, 262, 263, 264], 10, ""] : [[271, 272, 273, 274], 40, "15mbit"];
  const predictHook = (run) => sh(`python3 predict_run8b.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, [add], [0], { warm: true, rate, probe: 8, bwProbe: true }), rng(cmd.length * 67867967)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibQ", "gridQ", "testQ", "repQ"].includes(cmd)) {
  // Experiment Q (second, heavier page): /csrh and /ssrh, ~300 kB extra client bundle, 100 rows
  // per page (4x payload). v7 equations recalibrated under netem on the Mac, 10 Mbit/s.
  const h = { route: "h", limit: 100, warmPage: 49, warm: true };
  const spec = {
    calibQ: { seeds: [11], rtts: [0], extra: { ...h, resources: true } },
    gridQ: { seeds: [631, 632], rtts: [60, 150, 250, 400], extra: { ...h, resources: true } },
    testQ: { seeds: [641, 642], rtts: [90, 300], extra: { ...h, probe: 8 } },
    repQ: { seeds: [651, 652], rtts: [200, 350], extra: { ...h, probe: 8 } },
  }[cmd];
  const fresh = cmd === "testQ" || cmd === "repQ";
  if (fresh && !fs.existsSync(`${import.meta.dirname}/results/modelLQ.frozen.json`)) throw new Error("freeze modelLQ first");
  const predictHook = fresh ? (run) => sh(`MODEL_TAG=Q python3 predict_runL.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 67867979)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibR2", "gridR2", "testR2", "repR2"].includes(cmd)) {
  // Experiment R2 = R redone on server (Linux x86, pinned cores; docker-compose.server-conc.yml):
  // the Mac run hit the Apple Silicon load-dependent core speed. Same design, new seeds.
  const spec = {
    calibR2: { seeds: [11], rtts: [0], rates: [1, 6], extra: { resources: true, warm: true, timeoutMs: 120000 } },
    gridR2: { seeds: [691, 692], rtts: [40, 120, 250], rates: [1, 6], extra: { resources: true, warm: true, timeoutMs: 120000 } },
    testR2: { seeds: [701, 702], rtts: [80, 200], rates: [4], extra: { warm: true, probe: 8, timeoutMs: 120000 } },
    repR2: { seeds: [711, 712], rtts: [60, 180], rates: [2], extra: { warm: true, probe: 8, timeoutMs: 120000 } },
  }[cmd];
  const fresh = cmd === "testR2" || cmd === "repR2";
  if (fresh && !fs.existsSync(`${import.meta.dirname}/results/modelLR2.frozen.json`)) throw new Error("freeze modelLR2 first");
  const list = [];
  for (const cpuRate of spec.rates) list.push(...combos(spec.seeds, spec.rtts, [0], { ...spec.extra, cpuRate, levelTag: `cpu${cpuRate}` }));
  const predictHook = fresh ? (run) => sh(`MODEL_TAG=R2 python3 predict_runL.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(list, rng(cmd.length * 86028181)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibR", "gridR", "testR", "repR"].includes(cmd)) {
  // Experiment R (slow devices): Chromium CPU throttling. Calibrated at 1x and 6x (netem, Mac,
  // 10 Mbit/s); model levels interpolated linearly in the rate; fresh tests at 4x and 2x.
  const spec = {
    calibR: { seeds: [11], rtts: [0], rates: [1, 6], extra: { resources: true, warm: true } },
    gridR: { seeds: [661, 662], rtts: [40, 120, 250], rates: [1, 6], extra: { resources: true, warm: true } },
    testR: { seeds: [671, 672], rtts: [80, 200], rates: [4], extra: { warm: true, probe: 8 } },
    repR: { seeds: [681, 682], rtts: [60, 180], rates: [2], extra: { warm: true, probe: 8 } },
  }[cmd];
  const fresh = cmd === "testR" || cmd === "repR";
  if (fresh && !fs.existsSync(`${import.meta.dirname}/results/modelLR.frozen.json`)) throw new Error("freeze modelLR first");
  const list = [];
  for (const cpuRate of spec.rates) list.push(...combos(spec.seeds, spec.rtts, [0], { ...spec.extra, cpuRate, levelTag: `cpu${cpuRate}` }));
  const predictHook = fresh ? (run) => sh(`MODEL_TAG=R python3 predict_runL.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(list, rng(cmd.length * 86028173)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibS", "gridS", "testS", "repS"].includes(cmd)) {
  // Item 7: second framework (SvelteKit, docker-compose.svelte.yml), Mac local, netem, 10 Mbit/s,
  // sequential users. v7 equations recalibrated; race probed before each fresh-test run.
  const relayless = { warm: true };
  const spec = {
    calibS: { seeds: [11], rtts: [0], extra: { ...relayless, resources: true } },
    gridS: { seeds: [231, 232], rtts: [60, 150, 250, 400], extra: { ...relayless, resources: true } },
    testS: { seeds: [241, 242], rtts: [90, 300], extra: { ...relayless, probe: 8 } },
    repS: { seeds: [251, 252], rtts: [200, 350], extra: { ...relayless, probe: 8 } },
  }[cmd];
  const fresh = cmd === "testS" || cmd === "repS";
  if (fresh && !fs.existsSync(`${import.meta.dirname}/results/modelS.frozen.json`)) throw new Error("freeze modelS first");
  const predictHook = fresh ? (run) => sh(`python3 predict_runS.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 179424673)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibP", "concP", "repP"].includes(cmd)) {
  // Item 6 redo on server (docker-compose.server-conc.yml): one pinned core per station
  // (client | web+api+redis | postgres), DB-bound deep pages, netem 100 ms, uncapped.
  // Configs with interleaving-independent outcomes: CSR none, SSR none. calibP (N = 1): full
  // sessions plus initial-only sessions, so per-action CPU demand per station is identified
  // (cgroup CPU before/after each run). concP N = 4, repP N = 8; staggered starts, evented waits.
  const cfgs = [["csr", false, false], ["ssr", false, false]];
  const base = { rtt: 100, irtt: 0, fe: false, be: false, wl: "deep", pageBase: 40, limit: 50, warmPage: 95, warm: true, rate: "", evented: true, cpu: true, idle: cmd === "calibP" };
  const list = [];
  if (cmd === "calibP") {
    for (const seed of [401, 402, 403]) for (const [mode] of cfgs) {
      list.push({ ...base, seed, mode, n: 1, nUsers: 12, resources: true });
      list.push({ ...base, seed, mode, n: 1, nUsers: 24, sessionLen: 1, initOnly: true });
    }
  } else {
    if (!fs.existsSync(`${import.meta.dirname}/results/modelP.frozen.json`)) throw new Error("freeze modelP first");
    const [seeds, n] = cmd === "concP" ? [[411, 412, 413, 414], 4] : [[421, 422, 423, 424], 8];
    for (const seed of seeds) for (const [mode] of cfgs) list.push({ ...base, seed, mode, n, nUsers: 16, stagger: 150 });
  }
  const predictHook = cmd === "calibP" ? null : (run) => sh(`python3 predict_runP.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(list, rng(cmd.length * 32452843)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["smokeP2", "calibP2", "concP2", "repP2", "calibP3", "concP3", "repP3", "concP4", "repP4"].includes(cmd)) {
  // modelP2 (item 6, server pinned cores): launch barrier, 32 users per run, on-path vs total
  // demand. calibP2 (N = 1): RTT 100 full + initial-only sessions (total demand, R1, C1) and RTT 0
  // full sessions with resource timings (on-path demand). concP2 N = 4, repP2 N = 8.
  const cfgs = ["csr", "ssr"];
  const base = { irtt: 0, fe: false, be: false, wl: "deep", pageBase: 40, limit: 50, warmPage: 95, warm: true, rate: "", evented: true, cpu: true, barrier: true, stagger: 150 };
  const list = [];
  if (cmd === "smokeP2") {
    list.push({ ...base, rtt: 100, seed: 499, mode: "csr", n: 8, nUsers: 32 });
  } else if (cmd === "calibP2") {
    for (const seed of [431, 432, 433]) for (const mode of cfgs) {
      list.push({ ...base, rtt: 100, seed, mode, n: 1, nUsers: 32, idle: true });
      list.push({ ...base, rtt: 100, seed, mode, n: 1, nUsers: 32, sessionLen: 1, initOnly: true, idle: true });
      list.push({ ...base, rtt: 0, seed, mode, n: 1, nUsers: 32, resources: true });
    }
  } else if (cmd === "calibP3") {
    // modelP3: load-dependent demands and client on-path demand calibrated at N = 2 and 6.
    for (const seed of [481, 482, 483]) for (const mode of cfgs) for (const n of [2, 6]) list.push({ ...base, rtt: 100, seed, mode, n, nUsers: n === 6 ? 36 : 32 });
  } else if (cmd === "concP4" || cmd === "repP4") {
    if (!fs.existsSync(`${import.meta.dirname}/results/modelP4.frozen.json`)) throw new Error("freeze modelP4 first");
    const [seeds, n, users] = cmd === "concP4" ? [[511, 512, 513, 514], 3, 30] : [[521, 522, 523, 524], 7, 35];
    for (const seed of seeds) for (const mode of cfgs) list.push({ ...base, rtt: 100, seed, mode, n, nUsers: users });
  } else if (cmd === "concP3" || cmd === "repP3") {
    if (!fs.existsSync(`${import.meta.dirname}/results/modelP3.frozen.json`)) throw new Error("freeze modelP3 first");
    const [seeds, n] = cmd === "concP3" ? [[491, 492, 493, 494], 4] : [[501, 502, 503, 504], 8];
    for (const seed of seeds) for (const mode of cfgs) list.push({ ...base, rtt: 100, seed, mode, n, nUsers: 32 });
  } else {
    if (!fs.existsSync(`${import.meta.dirname}/results/modelP2.frozen.json`)) throw new Error("freeze modelP2 first");
    const [seeds, n] = cmd === "concP2" ? [[461, 462, 463, 464], 4] : [[471, 472, 473, 474], 8];
    for (const seed of seeds) for (const mode of cfgs) list.push({ ...base, rtt: 100, seed, mode, n, nUsers: 32 });
  }
  const predictHook = ["calibP2", "smokeP2", "calibP3"].includes(cmd) ? null
    : (run) => sh(`python3 predict_run${cmd.slice(-2)}.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(list, rng(cmd.length * 49979693)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibC", "concC", "repC"].includes(cmd)) {
  // Item 6 (concurrency), Mac local stack with capped server CPUs (docker-compose.mac-caps.yml),
  // netem 100 ms client RTT, uncapped bandwidth. Only configurations whose cache outcomes do
  // not depend on user interleaving: CSR none / TanStack-only, SSR none.
  // calibC: N = 1 (demands + baseline); concC: N = 4; repC: N = 8. New seeds per command.
  const cfgs = [["csr", false, false], ["csr", true, false], ["ssr", false, false]];
  const spec = { calibC: { seeds: [201, 202], n: 1 }, concC: { seeds: [211, 212, 213, 214], n: 4 }, repC: { seeds: [221, 222, 223, 224], n: 8 } }[cmd];
  if (cmd !== "calibC" && !fs.existsSync(`${import.meta.dirname}/results/modelC.frozen.json`)) throw new Error("freeze modelC first");
  const list = [];
  for (const seed of spec.seeds) for (const [mode, fe, be] of cfgs)
    // Users divisible by N so every parallel process has the same session count.
    list.push({ seed, rtt: 100, irtt: 0, mode, fe, be, wl: "deep", pageBase: 40, limit: 50, warmPage: 95, warm: true, rate: "", n: spec.n, nUsers: spec.n === 8 ? 16 : 12, resources: cmd === "calibC" });
  const predictHook = cmd === "calibC" ? null : (run) => sh(`python3 predict_runC.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(list, rng(cmd.length * 122949829)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calibW", "testW", "repW", "testW2", "repW2", "testX", "repX"].includes(cmd)) {
  // Item 8 (writes + invalidation), Mac local stack, netem, 10 Mbit/s. Cells cross rendering
  // mode with the browser/Next layer policy (ttl = TanStack staleTime S or Next revalidate R,
  // push = Next tag revalidated on every write, off) and the Redis policy (ttl T, push).
  // calibW: no writes (timeline only); testW/repW: seeded Poisson writes at LAM writes/s over
  // the workload's products. Rows shown at each display are compared with the write log.
  const spec = {
    calibW: { seeds: [301, 302], rtts: [50, 250], lam: 0, S: 3, T: 6 },
    testW: { seeds: [311, 312, 313, 314], rtts: [100], lam: 2, S: 3, T: 6 },
    repW: { seeds: [321, 322, 323, 324], rtts: [200], lam: 4, S: 2, T: 4 },
    // After the testW fix (API purged the Next tag in every Redis-push cell): fresh conditions,
    // 8 seeds per cell, an independent write stream per run.
    testW2: { seeds: [331, 332, 333, 334, 335, 336, 337, 338], rtts: [150], lam: 3, S: 3, T: 5 },
    repW2: { seeds: [341, 342, 343, 344, 345, 346, 347, 348], rtts: [60], lam: 1.5, S: 2, T: 8 },
    // Experiment X (server-work regime): added DB work per DB read; latency AND staleness predicted.
    testX: { seeds: [611, 612, 613, 614, 615, 616, 617, 618], rtts: [100], lam: 2, S: 3, T: 6, d: 25 },
    repX: { seeds: [621, 622, 623, 624, 625, 626, 627, 628], rtts: [200], lam: 1.5, S: 2, T: 8, d: 100 },
  }[cmd];
  const cells = [
    ["csr", "ttl", "ttl"], ["csr", "ttl", "push"], ["csr", false, "ttl"],
    ["ssr", "ttl", "ttl"], ["ssr", "ttl", "push"], ["ssr", "push", "push"], ["ssr", false, "ttl"], ["ssr", false, false],
  ];
  const X = cmd.endsWith("X");
  if (X) cells.push(["csr", false, false]);                       // CSR baseline for savings
  if (cmd !== "calibW" && !fs.existsSync(`${import.meta.dirname}/results/model${X ? "X" : "W"}.frozen.json`)) throw new Error("freeze the model first");
  const pages = WORKLOADS.revisit.pages;
  const list = [];
  for (const seed of spec.seeds) for (const rtt of spec.rtts) for (const [mode, fe, rp] of cells) list.push({ seed, rtt, mode, fe, rp });
  shuffle(list, rng(cmd.length * 15485863)).forEach((c, i) => {
    const runId = `${cmd}-s${c.seed}-r${c.rtt}-${c.mode}-fe${c.fe || "off"}-rd${c.rp || "off"}`;
    const apiExtra = { ttl: c.rp === "ttl" ? spec.T : 3600, inv: c.rp === "push" ? "push" : "ttl", invNext: c.mode === "ssr" && c.fe === "push", dbDelayMs: spec.d || 0 };
    const webEnv = { NEXT_REVALIDATE: String(spec.S), TANSTACK_S: String(spec.S) };
    configure({ fe: c.fe, be: !!c.rp, net: { clientRtt: c.rtt, internalRtt: 0, rate: "10mbit" }, runId, warm: true, webEnv, apiExtra });
    const tcpPre = tcpRtt();
    const users = makeWorkload({ ...WORKLOADS.revisit, users: 16, seed: c.seed * 1000 + 7 });
    const run = { runId, cmd, ...c, lam: spec.lam, S: spec.S, T: spec.T, pages, users, tcpPre, invNext: apiExtra.invNext, dbDelayMs: spec.d || 0 };
    if (cmd !== "calibW") sh(`python3 predict_run${X ? "X" : "W"}.py '${JSON.stringify(run)}'`);
    const stock0 = apiCall(`/__admin/stock?pages=${pages}`);
    const wseed = cmd.endsWith("2") || X ? c.seed * 101 + i : c.seed * 7 + 1;   // W2/X: independent stream per run
    if (spec.lam) apiCall("/__admin/writes", { lam: spec.lam, pages, seed: wseed });
    const t0 = Date.now();
    try { runBrowser({ mode: c.mode, runId, out: `/results/${cmd}.jsonl`, users, limit: 25, warm: true, snap: true }); }
    finally { apiCall("/__admin/writes", {}); }
    fs.appendFileSync(`${import.meta.dirname}/results/${cmd}-runs.jsonl`,
      JSON.stringify({ ...run, stock0: stock0.stock, stock0At: stock0.at, t0, wallMs: Date.now() - t0, tcpPost: tcpRtt(), order: i }) + "\n");
    console.log(`[${i + 1}/${list.length}] ${runId} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  });
} else if (cmd === "calibH2" || cmd === "gridH2") {
  // modelH2 (home path): extra bandwidth levels for the client-side calibration on this Mac's
  // local stack (netem): uncapped, 5 Mbit/s, 3 Mbit/s (10 Mbit/s = calibH/gridH). The home
  // link measured 3-12 Mbit/s, below the 10 Mbit/s modelH assumed.
  const levels = ["", "5mbit", "3mbit"];
  const list = [];
  for (const rate of levels) {
    const spec = cmd === "calibH2" ? { seeds: [11], rtts: [0] } : { seeds: [273, 274], rtts: [30, 60, 100, 150] };
    list.push(...combos(spec.seeds, spec.rtts, [0], { resources: true, warm: true, rate, httpRtt: true, levelTag: `bw${rate || "inf"}` }));
  }
  runConfigs(shuffle(list, rng(cmd.length * 15485867)), { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd });
} else if (cmd === "calibHP") {
  // modelH3 server side: server in pinned home mode, local client, RTT 0, resource timings
  // (run in server's controller with COMPOSE_FILE = conc + pin overrides).
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  runConfigs(shuffle(combos([11], [0], [0], { resources: true, warm: true }), rng(cmd.length * 7919)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd });
} else if (cmd === "realH3" || cmd === "repH3") {
  // modelH3 fresh tests on the home path: server pinned (REMOTE_COMPOSE), request-level RTT,
  // race probe whose page loads also give the bandwidth-equivalent input; no download probe.
  if (!REMOTE || !REMOTE_IP || !HOME_IP || !process.env.REMOTE_SUDO || !process.env.REMOTE_COMPOSE) throw new Error(`${cmd} needs REMOTE_SERVER, REMOTE_IP, HOME_IP, REMOTE_SUDO, REMOTE_COMPOSE`);
  if (!fs.existsSync(`${import.meta.dirname}/results/modelH3.frozen.json`)) throw new Error("freeze modelH3 first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, add] = cmd === "realH3" ? [[381, 382, 383, 384], 5] : [[391, 392, 393, 394], 25];
  const predictHook = (run) => sh(`python3 predict_runH3.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, [add], [0], { warm: true, probe: 8, probeLog: true, httpRtt: true }), rng(cmd.length * 86028161)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "realH2" || cmd === "repH2") {
  // modelH2 fresh tests on the home path: request-level RTT, measured bandwidth, race probe.
  if (!REMOTE || !REMOTE_IP || !HOME_IP || !process.env.REMOTE_SUDO) throw new Error(`${cmd} needs REMOTE_SERVER, REMOTE_IP, HOME_IP, REMOTE_SUDO`);
  if (!fs.existsSync(`${import.meta.dirname}/results/modelH2.frozen.json`)) throw new Error("freeze modelH2 first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, add] = cmd === "realH2" ? [[281, 282, 283, 284], 10] : [[291, 292, 293, 294], 30];
  const predictHook = (run) => sh(`python3 predict_runH2.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, [add], [0], { warm: true, probe: 8, bwProbe: true, bwSizes: "1 4", httpRtt: true }), rng(cmd.length * 86028157)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "diagH") {
  // Item 5 diagnosis (not a test): home path, resource timings on, to compare the RTT that
  // requests experience with the idle TCP-connect probe.
  if (!REMOTE || !REMOTE_IP || !HOME_IP || !process.env.REMOTE_SUDO) throw new Error(`${cmd} needs REMOTE_SERVER, REMOTE_IP, HOME_IP, REMOTE_SUDO`);
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  runConfigs(shuffle(combos([199], [0], [0], { warm: true, resources: true }), rng(57)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd });
} else if (cmd === "realH" || cmd === "repH") {
  // Item 5: home internet path (this Mac's browser -> server), 10 Mbit/s cap; race and
  // bandwidth probed before each run; predictions from the hardware-split calibration.
  if (!REMOTE || !REMOTE_IP || !HOME_IP || !process.env.REMOTE_SUDO) throw new Error(`${cmd} needs REMOTE_SERVER, REMOTE_IP, HOME_IP, REMOTE_SUDO`);
  if (!fs.existsSync(`${import.meta.dirname}/results/modelH.frozen.json`)) throw new Error("freeze modelH first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, add] = cmd === "realH" ? [[181, 182, 183, 184], 0] : [[191, 192, 193, 194], 20];
  const predictHook = (run) => sh(`python3 predict_runH.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, [add], [0], { warm: true, probe: 8, bwProbe: true }), rng(cmd.length * 86028121)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "calibH" || cmd === "gridH") {
  // Item 5 (home path), client-side calibration on the Mac's LOCAL stack (netem, 10 Mbit/s):
  // RTT 0, then a grid bracketing the home RTT (~62 ms). Server-side costs come from server.
  const spec = {
    calibH: { seeds: [11], rtts: [0], extra: { resources: true, warm: true } },
    gridH: { seeds: [171, 172], rtts: [30, 60, 100, 150], extra: { resources: true, warm: true } },
  }[cmd];
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 49979687)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd });
} else if (cmd === "test9b" || cmd === "reptest9b") {
  // v9b fresh tests under netem on server (the real relay path was unusable on 20 Oct):
  // RTTs never used for calibration (grid9b: 120/250/400/550).
  if (!H2) throw new Error(`${cmd} needs PROTO=h2 and the h2 compose overrides`);
  if (!fs.existsSync(`${import.meta.dirname}/results/model9b.frozen.json`)) throw new Error("freeze model9b first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, rtts] = cmd === "test9b" ? [[175, 176], [80, 330]] : [[185, 186], [200, 450]];
  const predictHook = (run) => sh(`MODEL_TAG=9b python3 predict_run9.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, rtts, [0], { warm: true, pinTls: true }), rng(cmd.length * 15485863)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calib9b", "grid9b", "real9b", "rep9b"].includes(cmd)) {
  // v9b: v9 with the edge certificate trusted by key (no Playwright certificate override,
  // which added 2 RTT per new TLS connection). Same structure; recalibrated; fresh tests:
  // real9b real path + 25 ms, rep9b real path + 5 ms, new seeds.
  if (!H2) throw new Error(`${cmd} needs PROTO=h2 and the h2 compose overrides`);
  const relay = cmd === "real9b" || cmd === "rep9b";
  if (relay && !process.env.RELAY_IP) throw new Error(`${cmd} needs RELAY_IP and the relay-h2 override`);
  if (relay && !fs.existsSync(`${import.meta.dirname}/results/model9b.frozen.json`)) throw new Error("freeze model9b first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const pin = { pinTls: true };
  const spec = {
    calib9b: { seeds: [11], rtts: [0], extra: { resources: true, warm: true, ...pin } },
    grid9b: { seeds: [117, 118], rtts: [120, 250, 400, 550], extra: { resources: true, warm: true, ...pin } },
    real9b: { seeds: [155, 156, 157, 158], rtts: [25], extra: { warm: true, ...pin } },
    rep9b: { seeds: [165, 166, 167, 168], rtts: [5], extra: { warm: true, ...pin } },
  }[cmd];
  const predictHook = relay ? (run) => sh(`MODEL_TAG=9b python3 predict_run9.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 32452843)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calib9", "grid9", "real9", "rep9"].includes(cmd)) {
  // v9 (item 4): HTTPS + HTTP/2 via the Caddy edge, 10 Mbit/s. calib9/grid9: netem;
  // real9: real path + 35 ms; rep9: real path + 15 ms. Model frozen from netem data only.
  if (!H2) throw new Error(`${cmd} needs PROTO=h2 and the h2 compose overrides`);
  const relay = cmd === "real9" || cmd === "rep9";
  if (relay && !process.env.RELAY_IP) throw new Error(`${cmd} needs RELAY_IP and the relay-h2 override`);
  if (relay && !fs.existsSync(`${import.meta.dirname}/results/model9.frozen.json`)) throw new Error("freeze model9 first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const spec = {
    calib9: { seeds: [11], rtts: [0], extra: { resources: true, warm: true } },
    grid9: { seeds: [115, 116], rtts: [120, 250, 400, 550], extra: { resources: true, warm: true } },
    real9: { seeds: [151, 152, 153, 154], rtts: [35], extra: { warm: true } },
    rep9: { seeds: [161, 162, 163, 164], rtts: [15], extra: { warm: true } },
  }[cmd];
  const predictHook = relay ? (run) => sh(`python3 predict_run9.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 32452843)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (["calib8", "grid8", "real8", "rep8"].includes(cmd)) {
  // v8 (bandwidth as input). calib8/grid8: netem, UNCAPPED (second bandwidth level).
  // real8: real path + 30 ms, uncapped; rep8: real path + 50 ms, capped at 25 Mbit/s.
  // Race and bandwidth probed before each run. Model frozen from netem data only.
  const relay = cmd === "real8" || cmd === "rep8";
  if (relay && !process.env.RELAY_IP) throw new Error(`${cmd} needs RELAY_IP and the relay compose override`);
  if (relay && !fs.existsSync(`${import.meta.dirname}/results/model8.frozen.json`)) throw new Error("freeze model8 first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const spec = {
    calib8: { seeds: [11], rtts: [0], extra: { resources: true, warm: true, rate: "" } },
    grid8: { seeds: [113, 114], rtts: [120, 250, 400, 550], extra: { resources: true, warm: true, rate: "" } },
    real8: { seeds: [131, 132, 133, 134], rtts: [30], extra: { warm: true, rate: "", probe: 8, bwProbe: true } },
    rep8: { seeds: [141, 142, 143, 144], rtts: [50], extra: { warm: true, rate: "25mbit", probe: 8, bwProbe: true } },
  }[cmd];
  const predictHook = relay ? (run) => sh(`python3 predict_run8.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 15485863)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "real7" || cmd === "rep7") {
  // v7 fresh tests: real path + emulated delay never used before (+40 / +20 ms), new seeds,
  // race probability probed before each CSR run. Model frozen from netem data only.
  if (!process.env.RELAY_IP) throw new Error(`${cmd} needs RELAY_IP and the relay compose override`);
  if (!fs.existsSync(`${import.meta.dirname}/results/model7.frozen.json`)) throw new Error("freeze model7 first");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const [seeds, add] = cmd === "real7" ? [[101, 102, 103, 104], 40] : [[121, 122, 123, 124], 20];
  const predictHook = (run) => sh(`python3 predict_run7.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos(seeds, [add], [0], { warm: true, probe: 8 }), rng(cmd.length * 104729)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "diag6") {
  // Diagnostic over the (now used) real path: CSR with Resource Timing, to locate
  // the CSR-initial gap between netem calibration and the real internet path.
  if (!process.env.RELAY_IP) throw new Error("diag6 needs RELAY_IP and the relay compose override");
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  const list = [false, true].map((on) => ({ seed: 99, rtt: 0, irtt: 0, mode: "csr", fe: on, be: on, wl: "revisit", warm: true, resources: true }));
  runConfigs(list, { out: "/results/diag6.jsonl", runsFile: "diag6-runs.jsonl", tag: "diag6" });
} else if (["calib6", "grid6", "real6", "rep6"].includes(cmd)) {
  // v6 on server: v5 equations recalibrated on this hardware with netem only
  // (calib6: RTT 0; grid6: netem 120-550 ms), then validated over the REAL
  // internet path server -> relay VPS -> server (real6, rep6). Internal RTT 0 throughout.
  const R = `${import.meta.dirname}/results`;
  const relay = cmd === "real6" || cmd === "rep6";
  if (relay && !process.env.RELAY_IP) throw new Error("real6/rep6 need RELAY_IP and the relay compose override");
  // Browser resolves web/api to the relay in real6/rep6, to the local containers otherwise.
  dc("up -d --no-deps --force-recreate client"); sh("sleep 3");
  if (relay && !fs.existsSync(`${R}/model6.frozen.json`)) throw new Error("freeze model6 first (python3 freeze6.py)");
  const spec = {
    calib6: { seeds: [11], rtts: [0], extra: { resources: true, warm: true } },
    grid6: { seeds: [111, 112], rtts: [120, 250, 400, 550], extra: { resources: true, warm: true } },
    real6: { seeds: [81, 82, 83, 84], rtts: [0], extra: { warm: true } },
    rep6: { seeds: [91, 92, 93, 94], rtts: [0], extra: { warm: true } },
  }[cmd];
  const predictHook = relay ? (run) => sh(`python3 predict_run6.py '${JSON.stringify(run)}'`) : null;
  runConfigs(shuffle(combos(spec.seeds, spec.rtts, [0], spec.extra), rng(cmd.length * 7919 + 6)),
    { out: `/results/${cmd}.jsonl`, runsFile: `${cmd}-runs.jsonl`, tag: cmd, predictHook });
} else if (cmd === "replicate5") {
  // Replication of the accepted v5 (unchanged, same frozen file): new RTTs and seeds.
  const predictHook = (run) => sh(`python3 predict_run5.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos([71, 72, 73, 74], [150, 320], [35, 100], { warm: true }), rng(271828)),
    { out: "/results/rep5.jsonl", runsFile: "rep5-runs.jsonl", tag: "rep5", predictHook });
} else if (cmd === "rerun") {
  // Discard one contaminated run (data + prediction) and re-execute the same config,
  // with its prediction re-written before it starts.  usage: rerun <tag> <runId>
  const tag = arg, runId = arg2, n = tag.replace(/\D/g, "");
  const R = `${import.meta.dirname}/results`;
  const runLine = fs.readFileSync(`${R}/${tag}-runs.jsonl`, "utf8").split("\n").find((l) => l.includes(`"runId":"${runId}"`));
  if (!runLine) throw new Error(`no run ${runId}`);
  const c = JSON.parse(runLine);
  for (const f of [`${tag}.jsonl`, `${tag}-runs.jsonl`, `predictions${n}.jsonl`]) {
    // Parse each line (Python and Node write JSON with different spacing).
    const keep = fs.readFileSync(`${R}/${f}`, "utf8").split("\n").filter((l) => l && JSON.parse(l).runId !== runId);
    fs.writeFileSync(`${R}/${f}`, keep.join("\n") + "\n");
  }
  fs.appendFileSync(`${R}/discarded-runs.jsonl`, JSON.stringify({ runId, tag, at: new Date().toISOString(), reason: arg2 && process.env.REASON || "host sleep during run" }) + "\n");
  const predictHook = (run) => sh(`python3 predict_run${n}.py '${JSON.stringify(run)}'`);
  const cfg = { seed: c.seed, rtt: c.rtt, irtt: c.irtt, mode: c.mode, fe: c.fe, be: c.be, wl: c.wl, warm: c.warm };
  runConfigs([cfg], { out: `/results/${tag}.jsonl`, runsFile: `${tag}-runs.jsonl`, tag, predictHook });
} else if (cmd === "prospective5") {
  // Fresh test for model v5: interpolation RTTs never used before, new seeds.
  if (!fs.existsSync(`${import.meta.dirname}/results/model5.frozen.json`)) throw new Error("freeze model5 first (python3 freeze5.py)");
  const predictHook = (run) => sh(`python3 predict_run5.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos([61, 62, 63, 64], [90, 210], [20, 75], { warm: true }), rng(4711)),
    { out: "/results/prosp5.jsonl", runsFile: "prosp5-runs.jsonl", tag: "prosp5", predictHook });
} else if (cmd === "prospective4") {
  // Final fresh test for model v4: client/internal RTTs and seeds never used before.
  if (!fs.existsSync(`${import.meta.dirname}/results/model4.frozen.json`)) throw new Error("freeze model4 first (python3 freeze4.py)");
  const predictHook = (run) => sh(`python3 predict_run4.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos([51, 52, 53, 54], [60, 260], [45, 120], { warm: true }), rng(31337)),
    { out: "/results/prosp4.jsonl", runsFile: "prosp4-runs.jsonl", tag: "prosp4", predictHook });
} else if (cmd === "calib3") {
  // Model v3 calibration: RTT 0, warm-up, TCP RTT, Resource Timing.
  runConfigs(combos([11], [0], [0], { resources: true, warm: true }), { out: "/results/calib3.jsonl", runsFile: "calib3-runs.jsonl", tag: "calib3" });
} else if (cmd === "prospective3") {
  // Fresh test: unseen client/internal RTTs, new seeds; per-run prediction frozen before each run.
  const frozen = `${import.meta.dirname}/results/model3.frozen.json`;
  if (!fs.existsSync(frozen)) throw new Error("freeze model3 first (python3 freeze3.py)");
  const predictHook = (run) => sh(`python3 predict_run3.py '${JSON.stringify(run)}'`);
  runConfigs(shuffle(combos([41, 42, 43, 44], [120, 350], [30, 90], { warm: true }), rng(9001)),
    { out: "/results/prosp3.jsonl", runsFile: "prosp3-runs.jsonl", tag: "prosp3", predictHook });
} else if (cmd === "calib2") {
  // Model v2 calibration: RTT 0 everywhere, with Resource Timing (bytes, connections).
  runConfigs(combos([11], [0], [0], { resources: true }), { out: "/results/calib2.jsonl", runsFile: "calib2-runs.jsonl", tag: "calib2" });
} else if (cmd === "prospective2") {
  // Fresh evaluation for model v2: unseen client RTTs, internal-link delay, new seeds.
  if (!fs.existsSync(`${import.meta.dirname}/results/predictions2.frozen.json`)) throw new Error("freeze predictions2 first");
  runConfigs(shuffle(combos([31, 32, 33, 34], [80, 230], [0, 60]), rng(777)),
    { out: "/results/prosp2.jsonl", runsFile: "prosp2-runs.jsonl", tag: "prosp2" });
} else if (cmd === "calib") {
  // Calibration of outcome mixes only (RTT 0): separate seed from evaluation.
  runConfigs(combos([11], [0]), { out: "/results/calib.jsonl", runsFile: "calib-runs.jsonl", tag: "calib" });
} else if (cmd === "prospective") {
  // Evaluation at RTTs never used for fitting; run only after predictions are frozen.
  if (!fs.existsSync(`${import.meta.dirname}/results/predictions.json`)) throw new Error("freeze predictions first");
  const rand = rng(4242);
  runConfigs(shuffle(combos([21, 22, 23], [40, 300]), rand), { out: "/results/prosp.jsonl", runsFile: "prosp-runs.jsonl", tag: "prosp" });
} else if (cmd === "pilot") {
  for (const s of (arg || "1").split(",").map(Number)) pilot(s);
} else if (cmd === "calibrate") {
  setNetwork({ clientRtt: Number(arg || 0), internalRtt: 0 });
  console.log(measuredRtt());
} else if (cmd === "smoke") {
  const out = "/results/smoke.jsonl";
  fs.rmSync(`${import.meta.dirname}/results/smoke.jsonl`, { force: true });
  for (const mode of ["csr", "ssr"])
    for (const fe of [false, true])
      for (const be of [false, true]) {
        const label = `${mode}-fe${fe ? 1 : 0}-be${be ? 1 : 0}`;
        configure({ fe, be, net: { clientRtt: 0 }, runId: `smoke-${label}` });
        runBrowser({ mode, runId: `smoke-${label}`, out, users: [[1, 2, 1], [1, 2, 1], [1, 2, 1]] });
        console.log("done", label);
      }
}
