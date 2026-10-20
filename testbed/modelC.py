"""Concurrency model (item 6): closed queueing network solved by Mean Value Analysis.

N users run sessions concurrently (closed loop, no think time). Stations: WEB (Next.js
server CPU), API (Express CPU), DB (Postgres) are FCFS queues; network round trips and
client-side work are a pure delay. Per action a at N users (arrival theorem):
    R_a(N) = R_a(1) + sum_k D_k(a) * Q_k(N - 1)
where R_a(1) is the measured single-user latency and D_k(a) the measured service demand
of action a at station k (N = 1 calibration). Q_k(n) comes from exact single-class MVA
on the workload's mix-weighted demands:
    R_k(n) = Dbar_k (1 + Q_k(n-1)),  X(n) = n / (Z + sum_k R_k(n)),  Q_k(n) = X(n) R_k(n),
with Z = mean R(1) - sum_k Dbar_k (the non-queueing part of a cycle).
"""
from model5 import analytic_outcomes  # noqa: F401 (re-exported)
from lib import mean

STATIONS = ("web", "api", "db")


def mva(dbar, z, n):
    q = {k: 0.0 for k in STATIONS}
    for m in range(1, n + 1):
        r = {k: dbar[k] * (1 + q[k]) for k in STATIONS}
        x = m / (z + sum(r.values()))
        q = {k: x * r[k] for k in STATIONS}
    return q


def predict_run(actions, n, R1, D):
    """actions: [(mode, action, outcome)] of one run. Returns predicted latency per action."""
    keys = [f"{m}|{a}|{o}" for m, a, o in actions]
    dbar = {k: mean(D[x][k] for x in keys) for k in STATIONS}
    z = mean(R1[x] for x in keys) - sum(dbar.values())
    q = mva(dbar, z, n - 1) if n > 1 else {k: 0.0 for k in STATIONS}
    return [R1[x] + sum(D[x][k] * q[k] for k in STATIONS) for x in keys]
