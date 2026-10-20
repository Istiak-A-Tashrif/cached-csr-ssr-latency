"""Model v8 = model v7 at two calibrated bandwidth levels, interpolated in 1/bandwidth.

Serialization time scales with 1/bandwidth, so with x = min(1, 10 Mbit/s / bw):
    T(bw) = (1 - x) * T_uncapped + x * T_10Mbit,
where each level is a full v7 calibration under netem (T0, byte sizes, race-split bundle
curves, correction): "cap" = 10 Mbit/s (calib6 + grid6), "inf" = uncapped (calib8 + grid8).
bw and the race probability p are measured on the path before each run.
"""
from model7 import analytic_outcomes, predict as predict7  # noqa: F401 (re-exported)

CAP = 10e6
INF = 1e12


def x_of(bw):
    return 1.0 if not bw else min(1.0, max(0.0, CAP / bw))


def level_predict(L, bw_level, mode, action, o, crtt, irtt, p):
    T0 = {tuple(k.split("|")): v for k, v in L["T0"].items()}
    return predict7(mode, action, o, crtt, irtt, T0, L["bytes"], bw_level, L["curves"], L["correction"], p)


def predict(mode, action, o, crtt, irtt, P, bw, p):
    x = x_of(bw)
    return (1 - x) * level_predict(P["inf"], INF, mode, action, o, crtt, irtt, p) + \
        x * level_predict(P["cap"], CAP, mode, action, o, crtt, irtt, p)
