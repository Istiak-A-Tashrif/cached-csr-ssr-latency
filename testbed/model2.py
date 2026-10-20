"""Path model v2 (stdlib only).

T(mode, action, outcome; crtt, irtt) = T0(mode, action, outcome)
                                       + net(path; crtt, irtt) - net(path; 0, 0)

- T0: mean data-visible latency of that (mode, action, outcome) measured at RTT 0
  on the same workload (calibration). Covers CPU, rendering and server time.
- net: critical-path network time. Each request costs a handshake RTT on a new
  connection plus TCP slow-start rounds (initcwnd 10 x 1448 B, doubling per
  round), each round lasting max(RTT, bytes_in_round / bandwidth) (cf. Cardwell,
  Savage & Anderson, "Modeling TCP latency", INFOCOM 2000). Idle connections
  restart slow start (tcp_slow_start_after_idle=1); every payload except the JS
  bundle fits in one round anyway.
  The JS bundle is scheduled over Chromium's 6 connections per origin (the
  document's connection is reused; others pay a handshake) and is bounded below
  by total bytes / bottleneck bandwidth.
- outcome: computed analytically from the request sequence (sequential users,
  cold caches, no expiry/eviction within a run), see `analytic_outcomes`.

Critical paths (visible endpoint):
  CSR initial : document (new conn) -> JS bundle -> API request (new conn, other origin)
  CSR nav     : API request (warm) unless TanStack hit (no network)
  SSR initial : document (new conn); + internal API request if Next data-cache miss
  SSR nav     : RSC request (warm); + internal API request if Next data-cache miss
"""
from lib import mean

MSS, ICW, MAX_CONN = 1448, 10, 6


def rounds(nbytes, rtt, bw_bps=None, cwnd=ICW):
    """Slow-start transfer time of nbytes (at least one round: request + response)."""
    t, rem, first = 0.0, nbytes, True
    while rem > 0 or first:
        send = min(cwnd * MSS, rem)
        t += max(rtt, send * 8 / bw_bps * 1000 if bw_bps else 0.0)
        rem -= send; cwnd *= 2; first = False
    return t


def request(nbytes, rtt, bw_bps=None, new=False):
    return (rtt if new else 0.0) + rounds(nbytes, rtt, bw_bps)


def bundle(script_bytes, rtt, bw_bps):
    """JS chunks in request order over up to MAX_CONN connections to one origin.
    Chromium opens the extra connections concurrently: the document's connection
    is usable at once, the others after one handshake RTT. Each request takes the
    connection that becomes free first (observed in Resource Timing at 170 ms)."""
    free = [0.0] + [rtt] * (MAX_CONN - 1)
    end = 0.0
    for b in script_bytes:
        idx = min(range(len(free)), key=free.__getitem__)
        free[idx] += rounds(b, rtt)          # bandwidth handled by the aggregate bound
        end = max(end, free[idx])
    return max(end, sum(script_bytes) * 8 / bw_bps * 1000)


def net(mode, action, o, crtt, irtt, B, bw_bps):
    """Critical-path network time (ms) for one action. B = calibrated byte sizes."""
    internal = request(B["api"], irtt) if o not in ("next_hit", "tq_hit") else 0.0
    if mode == "csr":
        if action == "initial":
            return (request(B["doc_csr"], crtt, bw_bps, new=True) + bundle(B["scripts"], crtt, bw_bps)
                    + request(B["api"], crtt, bw_bps, new=True))
        return 0.0 if o == "tq_hit" else request(B["api"], crtt, bw_bps)
    if action == "initial":
        return request(B["doc_ssr"], crtt, bw_bps, new=True) + internal
    return request(B["rsc"], crtt, bw_bps) + internal


def predict(mode, action, o, crtt, irtt, T0, B, bw_bps):
    return T0[(mode, action, o)] + net(mode, action, o, crtt, irtt, B, bw_bps) - net(mode, action, o, 0.0, 0.0, B, bw_bps)


def analytic_outcomes(mode, fe, be, users):
    """Exact cache outcomes for sequential users with cold, non-expiring caches.
    Returns [(user, step, page, outcome)]."""
    out, server_seen, redis_seen = [], set(), set()
    for u, seq in enumerate(users):
        session = set()
        for step, page in enumerate(seq):
            if mode == "csr" and fe and step > 0 and page in session:
                o = "tq_hit"
            elif mode == "ssr" and fe and page in server_seen:
                o = "next_hit"
            else:
                o = "redis_hit" if be and page in redis_seen else "db"
                redis_seen.add(page)
            server_seen.add(page); session.add(page)
            out.append((u, step, page, o))
    return out


def calibrate_bytes(acts):
    """Median byte sizes per critical-path element, from Resource Timing."""
    med = lambda xs: sorted(xs)[len(xs) // 2]
    doc = {"csr": [], "ssr": []}; api, rsc, scripts = [], [], []
    for a in acts:
        for r in a.get("res") or []:
            if r["type"] == "navigation": doc[a["mode"]].append(r["transfer"])
            elif r["type"] == "fetch" and "/api/products" in r["name"] and r["transfer"]: api.append(r["transfer"])
            elif r["type"] == "fetch" and "_rsc=" in r["name"] and r["transfer"]: rsc.append(r["transfer"])
        if a["mode"] == "csr" and a["action"] == "initial" and not scripts:
            scripts = [r["transfer"] for r in a["res"] if r["type"] in ("script", "link")]
    return {"doc_csr": med(doc["csr"]), "doc_ssr": med(doc["ssr"]), "api": med(api), "rsc": med(rsc), "scripts": scripts}


def calibrate_T0(acts):
    by = {}
    for a in acts:
        by.setdefault((a["mode"], a["action"], a["o"]), []).append(a["latencyMs"])
    return {k: mean(v) for k, v in by.items()}
