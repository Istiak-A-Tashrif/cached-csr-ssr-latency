"""Model v9: v7's equations for HTTPS + HTTP/2 (item 4).

Changes from v7, both protocol mechanisms:
1. A new connection costs TCP (1 RTT) plus a TLS 1.3 handshake (1 RTT) before the request.
2. HTTP/2 multiplexes all JS chunks of an origin on ONE connection, so there is no
   connection race: the bundle phase is a single empirical curve over calibration loads
   (netem), interpolated over client RTT.
Navigation and internal (web->api, plain HTTP) requests reuse warm connections, as before.
"""
from model4 import MSS, ICW, transfer
import model4
from model5 import analytic_outcomes, interp  # noqa: F401 (re-exported)

SETUP_RTTS = 2  # TCP + TLS 1.3


def request(nbytes, rtt, bw_bps=None, new=False):
    t, _ = transfer(nbytes, rtt, ICW, bw_bps or float("inf"))
    return (SETUP_RTTS * rtt if new else 0.0) + t


def net(mode, action, o, crtt, irtt, B, bw_bps, curve):
    internal = model4.request(B["api"], irtt) if o not in ("next_hit", "tq_hit") else 0.0
    if mode == "csr":
        if action == "initial":
            return request(B["doc_csr"], crtt, bw_bps, new=True) + interp(curve, crtt) + request(B["api"], crtt, bw_bps, new=True)
        return 0.0 if o == "tq_hit" else request(B["api"], crtt, bw_bps)
    if action == "initial":
        return request(B["doc_ssr"], crtt, bw_bps, new=True) + internal
    return request(B["rsc"], crtt, bw_bps) + internal


def base(mode, action, o, crtt, irtt, T0, B, bw_bps, curve):
    return T0[(mode, action, o)] + net(mode, action, o, crtt, irtt, B, bw_bps, curve) - net(mode, action, o, 0.0, 0.0, B, bw_bps, curve)


def predict(mode, action, o, crtt, irtt, T0, B, bw_bps, curve, corr):
    pts = corr.get(f"{mode}|{action}|{o}")
    return base(mode, action, o, crtt, irtt, T0, B, bw_bps, curve) + (interp(pts, crtt) if pts and crtt > 0 else 0.0)
