"""Concurrency model, server redo (item 6): closed queueing network solved by exact MVA.

Each station is ONE dedicated core (cpuset): CLIENT (all browsers + harness), APP (Next.js +
Express + Redis), DB (Postgres). Network round trips are a pure delay. Per action a at N:
    R_a(N) = R_a(1) + sum_k D_k(a) * Q_k(N - 1)          (arrival theorem)
D_k(a): CPU seconds per action from cgroup accounting at N = 1 (idle rate removed), split
between initial loads and navigations with initial-only runs. Q_k(n) from single-class MVA on
the run's mix-weighted demands, with think time Z = C1 - sum_k Dbar_k, where C1 is the
measured wall time per action at N = 1 (so harness time between actions is in Z, not lost).
"""
from model5 import analytic_outcomes  # noqa: F401 (re-exported)
from lib import mean

STATIONS = ("client", "app", "db")


def mva(dbar, z, n):
    q = {k: 0.0 for k in STATIONS}
    for m in range(1, n + 1):
        r = {k: dbar[k] * (1 + q[k]) for k in STATIONS}
        x = m / (z + sum(r.values()))
        q = {k: x * r[k] for k in STATIONS}
    return q


def predict_run(actions, n, R1, D, C1):
    """actions: [(mode, action, outcome)] of one run (single mode). Latency per action, ms."""
    keys = [f"{m}|{a}" for m, a, _ in actions]
    dbar = {k: mean(D[x][k] for x in keys) for k in STATIONS}
    z = C1[actions[0][0]] - sum(dbar.values())
    q = mva(dbar, z, n - 1) if n > 1 else {k: 0.0 for k in STATIONS}
    return [R1[x] + sum(D[x][k] * q[k] for k in STATIONS) for x in keys]
