// Bandwidth probe (v8): time downloads of 8 MB and 32 MB from the API through the same
// path the browser uses; the difference removes connection setup and most of the
// slow-start ramp:  bw = (32-8) MB / (t32 - t8).  Median of 3 pairs. Prints {bwBps}.
const base = process.argv[2] || "http://api:5001";
// Sizes in MB (small, large); home runs use 1/4 MB to limit data use on the author's connection.
const [S, L] = [Number(process.argv[3] || 8) * 1e6, Number(process.argv[4] || 32) * 1e6];
const get = async (n) => { const t = performance.now(); const r = await fetch(`${base}/__blob?n=${n}`); await r.arrayBuffer(); return performance.now() - t; };
const est = [];
for (let i = 0; i < 3; i++) {
  const a = await get(S), b = await get(L);
  if (b > a) est.push(((L - S) * 8) / ((b - a) / 1000));
}
est.sort((x, y) => x - y);
console.log(JSON.stringify({ bwBps: est.length ? est[Math.floor(est.length / 2)] : null, samples: est.map(Math.round) }));
