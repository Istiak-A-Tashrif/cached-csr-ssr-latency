// TCP RTT probe: median SYN->SYN-ACK time (connect duration) to host:port.
import net from "net";
const [host, port, n = 15] = process.argv.slice(2);
const one = () => new Promise((res, rej) => {
  const t = performance.now(); const s = net.connect(+port, host, () => { res(performance.now() - t); s.destroy(); });
  s.on("error", rej);
});
const xs = [];
for (let i = 0; i < +n; i++) { xs.push(await one()); await new Promise((r) => setTimeout(r, 30)); }
xs.sort((a, b) => a - b);
console.log(xs[Math.floor(xs.length / 2)].toFixed(2));
