"""Concurrency model P3 (item 6): modelP2 with LOAD-DEPENDENT demands, calibrated at other N.
Per station k, total and on-path demand scale with the population N:
    D_k(N) = D_k(1) * (alpha_k + beta_k * (N - 1))
(fitted from per-action cgroup CPU at N = 1, 2, 6; contention on a shared core and Postgres
concurrency make work per action grow with load). Queue lengths from exact MVA on D_k(N) with
the N = 1 think time Z = C1 - sum_k Dbar_k(1). Latency of class a:
    R_a(N) = R_a(1) + sum_k P_k(a) * s_k(N) * Q_k(N - 1),
with P_app, P_db from server logs (modelP2) and the client on-path demand P_client(a) fitted per
class at N = 2 and 6 (initial loads' client work is not measurable directly).
"""
from modelP2 import analytic_outcomes, STATIONS  # noqa: F401 (re-exported)
from lib import mean


def scale(F, k, n):
    return F["alpha"][k] + F["beta"][k] * (n - 1) if n > 1 else 1.0


def queues(keys, n, F):
    d1 = {k: mean(F["D"][x][k] for x in keys) for k in STATIONS}
    z = F["C1"][keys[0].split("|")[0]] - sum(d1.values())
    dn = {k: d1[k] * scale(F, k, n) for k in STATIONS}
    q = {k: 0.0 for k in STATIONS}
    for m in range(1, n):                                  # MVA up to N - 1 at the N-level demand
        r = {k: dn[k] * (1 + q[k]) for k in STATIONS}
        x = m / (z + sum(r.values()))
        q = {k: x * r[k] for k in STATIONS}
    return q


def predict_run(actions, n, F):
    keys = [f"{m}|{a}" for m, a, _ in actions]
    q = queues(keys, n, F)
    return [F["R1"][x] + sum(F["P"][x][k] * scale(F, k, n) * q[k] for k in STATIONS) for x in keys]
