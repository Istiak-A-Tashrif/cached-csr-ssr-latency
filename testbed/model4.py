"""Model v4 = model v2/v3 equations with a calibrated, connection-aware JS bundle phase
and a per-(mode, action) constant for "latency present".

Changes from v2/v3, each traced to a measured mechanism (see PILOT_REPORT.md §8):
1. Bundle dispatch is taken from calibration loads at RTT > 0. At RTT 0 all chunks
   start within microseconds, so Resource Timing order there is arbitrary (the
   "70 KB chunk last" order appeared 4/24 times at RTT 0 and 0/24 at 170 ms).
2. Transfers cost rounds x RTT + bytes/bandwidth (serialization adds to latency
   while the window is below the bandwidth-delay product; the 70 KB chunk's
   56 ms serialization was the measured shortfall).
3. Connections keep their congestion window. Whether each chunk used a new
   connection is recorded by Resource Timing; a chunk on the reused document
   connection needs one slow-start round less than on a fresh one (observed:
   bundle ends at ~960 ms vs ~1,110 ms at 170 ms). Expected bundle time is the
   mean over calibration loads.
4. kappa(mode, action): constant residual measured at the second calibration
   point (170 ms), present whenever client latency > 0 (TCP timer effects in the
   emulated stack; constant, not RTT-proportional).
"""
import math
import model2
from model2 import MSS, ICW, analytic_outcomes, calibrate_T0  # noqa: F401 (re-exported)
from lib import mean


def transfer(nbytes, rtt, cwnd, bw_bps):
    """Slow start on a connection with congestion window `cwnd` (segments):
    time = rounds x RTT + bytes / bandwidth (latency + serialization; the window
    stays below the bandwidth-delay product here, so they do not overlap).
    Returns (time, cwnd_after). At least one round (request + response)."""
    segs, rounds, first = math.ceil(nbytes / MSS), 0, True
    while segs > 0 or first:
        send = min(cwnd, segs)
        rounds += 1
        segs -= send; cwnd += send; first = False   # slow start: +1 per acked segment
    return rounds * rtt + nbytes * 8 / bw_bps * 1000, cwnd


def request(nbytes, rtt, bw_bps=None, new=False):
    """One request/response; bw_bps=None means an unshaped link (no serialization term)."""
    t, _ = transfer(nbytes, rtt, ICW, bw_bps) if bw_bps else transfer(nbytes, rtt, ICW, float("inf"))
    return (rtt if new else 0.0) + t


def bundle_load(load, rtt, bw_bps, doc_bytes):
    """One calibration load's chunks: [(bytes, newConn)] in request order.
    New-connection chunks open their own connection (handshake, ICW); reused
    chunks take the earliest-free existing connection, keeping its window."""
    conns = [[0.0, ICW + math.ceil(doc_bytes / MSS)]]   # document connection: [free_at, cwnd]
    end = 0.0
    for nbytes, new in load:
        if new:
            t, cw = transfer(nbytes, rtt, ICW, bw_bps)
            conns.append([rtt + t, cw])
            end = max(end, rtt + t)
        else:
            c = min(conns, key=lambda c: c[0])
            t, c[1] = transfer(nbytes, rtt, c[1], bw_bps)
            c[0] += t
            end = max(end, c[0])
    total = sum(b for b, _ in load)
    return max(end, total * 8 / bw_bps * 1000)


def calibrate_bytes(acts_rtt0, acts_rtt_pos):
    """Byte sizes from RTT-0 calibration; bundle dispatch from RTT>0 calibration."""
    B = model2.calibrate_bytes(acts_rtt0)
    B["bundle_loads"] = [
        [[r["transfer"], bool(r["newConn"])] for r in sorted(a["res"], key=lambda r: r["requestStart"])
         if r["type"] in ("script", "link")]
        for a in acts_rtt_pos if a["mode"] == "csr" and a["action"] == "initial" and a.get("res")
    ]
    return B


def expected_bundle(B, rtt, bw_bps):
    return mean(bundle_load(l, rtt, bw_bps, B["doc_csr"]) for l in B["bundle_loads"])


def net(mode, action, o, crtt, irtt, B, bw_bps):
    """Critical paths as in model2.net, with v4 transfers (latency + serialization)."""
    internal = request(B["api"], irtt) if o not in ("next_hit", "tq_hit") else 0.0
    if mode == "csr":
        if action == "initial":
            return (request(B["doc_csr"], crtt, bw_bps, new=True) + expected_bundle(B, crtt, bw_bps)
                    + request(B["api"], crtt, bw_bps, new=True))
        return 0.0 if o == "tq_hit" else request(B["api"], crtt, bw_bps)
    if action == "initial":
        return request(B["doc_ssr"], crtt, bw_bps, new=True) + internal
    return request(B["rsc"], crtt, bw_bps) + internal


def predict(mode, action, o, crtt, irtt, T0, B, bw_bps, kappa=None):
    k = (kappa or {}).get(f"{mode}|{action}", 0.0) if crtt > 0 else 0.0
    return T0[(mode, action, o)] + net(mode, action, o, crtt, irtt, B, bw_bps) - net(mode, action, o, 0.0, 0.0, B, bw_bps) + k
