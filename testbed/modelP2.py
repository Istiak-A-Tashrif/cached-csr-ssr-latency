"""Concurrency model P2 (item 6, server): exact MVA over three single-core stations (CLIENT,
APP = Next.js + Express + Redis, DB = Postgres), separating TOTAL from ON-PATH demand.
  Queue lengths Q_k(n): MVA on the run's mix-weighted TOTAL demands Dbar_k (all CPU a session
  puts on station k per action, including work outside the action's latency window such as
  creating the next browser context), think time Z = C1 - sum_k Dbar_k.
  Latency of action a at N:  R_a(N) = R_a(1) + sum_k P_k(a) * Q_k(N - 1),
  where P_k(a) is the ON-PATH demand of a at station k: DB and API time from the server logs,
  Next.js time from time-to-first-byte at RTT 0, client time = RTT-0 latency - server time.
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


def predict_run(actions, n, R1, D, P, C1):
    keys = [f"{m}|{a}" for m, a, _ in actions]
    dbar = {k: mean(D[x][k] for x in keys) for k in STATIONS}
    z = C1[actions[0][0]] - sum(dbar.values())
    q = mva(dbar, z, n - 1) if n > 1 else {k: 0.0 for k in STATIONS}
    return [R1[x] + sum(P[x][k] * q[k] for k in STATIONS) for x in keys]
