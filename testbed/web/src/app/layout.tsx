import Providers from "./providers";

// Data-visibility instrumentation, registered before any body content.
// - __vis: when the first data row ([data-vis]) enters the DOM (HTML parser for
//   SSR, React for CSR/navigation) and when the next frame after it completes.
//   Same mechanism for every mode, so endpoints are comparable.
// - __et: Element Timing (secondary; frame-quantized in headless Chromium).
const instrumentation = `
window.__vis = [];
var seenVis = new WeakSet();
new MutationObserver(function (ms) {
  var t = performance.now();
  ms.forEach(function (m) {
    m.addedNodes.forEach(function (n) {
      if (n.nodeType !== 1) return;
      var el = n.matches('[data-vis]') ? n : n.querySelector('[data-vis]');
      if (!el || seenVis.has(el)) return; // ancestors of one insertion all match
      seenVis.add(el);
      var tb = el.closest('table');
      // Item 8: what the user sees at this instant (a background refetch may replace it later).
      var rows = tb ? Array.prototype.map.call(tb.querySelectorAll('tbody tr'), function (tr) {
        return [Number(tr.getAttribute('data-pid')), Number(tr.cells[4].textContent)];
      }) : null;
      var rec = { id: el.getAttribute('data-vis'), dom: t, frame: null, rows: rows, resp: tb ? tb.getAttribute('data-resp-id') : null };
      window.__vis.push(rec);
      requestAnimationFrame(function () {
        var ch = new MessageChannel();
        ch.port1.onmessage = function () { rec.frame = performance.now(); };
        ch.port2.postMessage(0);
      });
    });
  });
}).observe(document.documentElement, { childList: true, subtree: true });
window.__et = [];
try {
  new PerformanceObserver(function (l) {
    l.getEntries().forEach(function (e) {
      window.__et.push({ id: e.identifier, t: e.renderTime || e.loadTime });
    });
  }).observe({ type: "element", buffered: true });
} catch (e) { window.__etError = String(e); }
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: instrumentation }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
