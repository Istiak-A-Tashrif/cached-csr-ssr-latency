"""Model v8b = model v8 + an emulation-to-real transfer offset for SSR navigation.

On every completed real-path test (real6, rep6, real7, rep7, real8, rep8; used conditions)
the netem-calibrated model over-predicted SSR navigation by 5-11 ms (pooled 8.0 ms) while
all other action types were unbiased. The mechanism is not isolated (an SSR-navigation-
specific behaviour of the emulated links that the real path lacks), so v8b adds the pooled
offset as an explicit empirical term for real-path predictions. Everything else is v8.
"""
from model8 import analytic_outcomes, predict as predict8, x_of  # noqa: F401 (re-exported)


def predict(mode, action, o, crtt, irtt, P, bw, p, transfer):
    return predict8(mode, action, o, crtt, irtt, P, bw, p) + transfer.get(f"{mode}|{action}", 0.0)
