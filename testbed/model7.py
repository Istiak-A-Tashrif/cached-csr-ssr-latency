"""Model v7 = model v5/v6 equations, with the CSR JS-bundle phase split by the connection
race and the race probability measured on the path (PILOT_REPORT.md §9).
Calibrated from netem data only (calib6 + grid6).

Diagnosis: on the real internet path the only CSR-initial phase that differed from netem
was the JS bundle (+0.53 RTT). The 70 KB chunk runs either on a reused connection (grown
window, one slow-start round fewer) or on a new one; which is free first depends on path
micro-timing (netem: new in 11% of loads; real path: 75%). v6 inherited netem's odds, and
its simulator also mis-modelled the reused case on this host (two warm connections, not
one), an error the netem-fitted correction absorbed only at netem's odds.

v7:  E[bundle](rtt) = p * Bnew(rtt) + (1 - p) * Breused(rtt)
  Bnew, Breused: observed bundle time per group in the netem calibration loads,
                 interpolated over measured client RTT (point at RTT 0 from calib6);
  p:             share of probe loads (page 199, used by no workload) whose big chunk
                 ran on a new connection, measured on the path BEFORE each run.
Correction grid: re-fitted on grid6 residuals using each calibration action's ACTUAL
group, so it carries no race odds. Other actions: model5/model4 unchanged.
"""
import model4
from model4 import request
from model5 import analytic_outcomes, interp  # noqa: F401 (re-exported)


def expected_bundle(curves, crtt, p):
    return p * interp(curves["new"], crtt) + (1 - p) * interp(curves["reused"], crtt)


def net(mode, action, o, crtt, irtt, B, bw_bps, curves, p):
    if mode == "csr" and action == "initial":
        return (request(B["doc_csr"], crtt, bw_bps, new=True) + expected_bundle(curves, crtt, p)
                + request(B["api"], crtt, bw_bps, new=True))
    return model4.net(mode, action, o, crtt, irtt, B, bw_bps)


def base(mode, action, o, crtt, irtt, T0, B, bw_bps, curves, p):
    return (T0[(mode, action, o)] + net(mode, action, o, crtt, irtt, B, bw_bps, curves, p)
            - net(mode, action, o, 0.0, 0.0, B, bw_bps, curves, p))


def predict(mode, action, o, crtt, irtt, T0, B, bw_bps, curves, corr, p):
    pts = corr.get(f"{mode}|{action}|{o}")
    return base(mode, action, o, crtt, irtt, T0, B, bw_bps, curves, p) + (interp(pts, crtt) if pts and crtt > 0 else 0.0)


def bundle_obs(a):
    """(observed bundle ms, big chunk on new connection?) for a CSR initial action with Resource Timing."""
    res = a["res"]; d = res[0]["responseEnd"]
    sc = [r for r in res if r["type"] in ("script", "link")]
    big = max(sc, key=lambda r: r["transfer"])
    return max(r["responseEnd"] for r in sc) - d, bool(big["newConn"])
