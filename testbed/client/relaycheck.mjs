// Relay connectivity check (v9b rerun): both edge origins through relay VPS must answer.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
const urls = ["https://edge:3000/csr?page=199&limit=25", "https://edge:5001/health"];
try { console.log("relay", await Promise.all(urls.map((u) => fetch(u).then((r) => r.status)))); }
catch (e) { console.log("relay fail", e.cause?.code || e.message); process.exit(1); }
