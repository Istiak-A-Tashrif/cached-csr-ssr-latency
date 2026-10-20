"""Home-path model H2 = modelH (v7 equations, hardware-split calibration) at four bandwidth
levels, piecewise linear in x = 10 Mbit/s / bw (serialization time is linear in 1/bw):
    inf (x = 0), 10 Mbit/s (x = 1), 5 Mbit/s (x = 2), 3 Mbit/s (x = 3.33);
beyond the last level the final segment is extended. bw, the race probability p and the
request-level RTT are measured on the path before each run.
"""
from model7 import analytic_outcomes, predict as predict7  # noqa: F401 (re-exported)

LEVELS = (("inf", 1e12, 0.0), ("10mbit", 10e6, 1.0), ("5mbit", 5e6, 2.0), ("3mbit", 3e6, 10 / 3))


def x_of(bw):
    return 1.0 if not bw else max(0.0, 10e6 / bw)


def predict(mode, action, o, crtt, irtt, P, bw, p):
    x = x_of(bw)
    ys = []
    for name, bwl, xl in LEVELS:
        L = P[name]
        T0 = {tuple(k.split("|")): v for k, v in L["T0"].items()}
        ys.append((xl, predict7(mode, action, o, crtt, irtt, T0, L["bytes"], bwl, L["curves"], L["correction"], p)))
    i = next((k for k in range(1, len(ys)) if x <= ys[k][0]), len(ys) - 1)
    (x0, y0), (x1, y1) = ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
