"""Model v5 = model v4 structure (without its single-point kappa) + an empirical
correction r(mode, action, outcome; client RTT), piecewise-linear over the client
RTTs already used (60, 120, 170, 260, 350 ms; pooled over internal RTT, which
showed no systematic effect). Captures two measured effects the mechanistic part
does not: (a) the frame wait at RTT 0 (5-12 ms) shrinks to 1-3 ms once the page
idles on the network (headless Chromium produces a frame on demand), so T0
over-states it; (b) the round-trip cost grows ~2-3% faster than the TCP-probe RTT,
multiplied by the number of round trips on the path (largest for CSR initial).
Outside the calibrated range the correction is held at the nearest end (no extrapolation).
"""
from model4 import analytic_outcomes, predict as predict4  # noqa: F401 (re-exported)


def interp(points, x):
    pts = sorted(points)
    if x <= pts[0][0]: return pts[0][1]
    if x >= pts[-1][0]: return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def predict(mode, action, o, crtt, irtt, T0, B, bw_bps, corr):
    base = predict4(mode, action, o, crtt, irtt, T0, B, bw_bps)
    pts = corr.get(f"{mode}|{action}|{o}")
    return base + (interp(pts, crtt) if pts and crtt > 0 else 0.0)
