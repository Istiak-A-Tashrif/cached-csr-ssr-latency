// Request-level RTT probe (modelH2): sequential small HTTP requests on one keep-alive
// connection; the mean includes the path's jitter tail, which a median of idle TCP
// connects hides. usage: node httprtt.mjs <base url> [n]   -> {"mean":..,"median":..,"n":..}
const [base, nArg = 30] = process.argv.slice(2);
const one = async () => { const t = performance.now(); await (await fetch(`${base}/health`)).text(); return performance.now() - t; };
await one(); await one();                       // connection setup + warm
const xs = [];
for (let i = 0; i < +nArg; i++) { xs.push(await one()); await new Promise((r) => setTimeout(r, 30)); }
const s = [...xs].sort((a, b) => a - b);
console.log(JSON.stringify({ mean: xs.reduce((a, b) => a + b, 0) / xs.length, median: s[Math.floor(s.length / 2)], n: xs.length }));
