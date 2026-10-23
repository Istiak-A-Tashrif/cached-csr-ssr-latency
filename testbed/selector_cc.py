#!/usr/bin/env python3
"""Chance-constrained policy selector (protocol v4, PROTOCOL_CC.md).

The v3 selector added one fixed staleness margin (0.05) to every candidate. This selector instead asks
that the candidate's OBSERVED block stale share stay within the limit with probability 1 - a:

    choose argmin L^(x)  subject to  S^(x) + z_{1-a} * sqrt(sd_s(x)^2 + sd_m^2) <= eps

  S^(x)    the frozen model R2's distribution-only predicted stale share (mean over the block's runs)
  sd_s(x)  sampling sd of the block's observed stale share (the mean over its n runs) under the model:
           Monte Carlo of the frozen R2 timeline with sessions sampled from the access distribution and
           Poisson writes realized per page; a view is stale iff a write to its page falls in (tau, t_disp]
  sd_m     model-error sd beyond sampling, from development blocks only:
           sd_m^2 = max(0, mean_cells[(obs - pred)^2 - sd_s(cell)^2])
The display time of each view is rebuilt exactly from modelR2.simulate's outputs (t_disp = t_prev +
gap + extra, extra = predicted latency - no-write latency), so the frozen model code is used unchanged.
"""
import math, random
from modelR2 import layer_cfg, outcomes, simulate
from predict_runR2 import M, sample_sessions


def fit(tab, crtt):
    return lambda m, a, o: tab[f"{m}|{a}|{o}"]["a"] + tab[f"{m}|{a}|{o}"]["b"] * crtt


def timeline(run, sessions):
    """Per view: (page, tau, t_disp) in seconds, on R2's expected-outcome timeline."""
    crtt = run["tcpPre"]["client_web"]; gap, lat = fit(M["gap"], crtt), fit(M["lat"], crtt)
    cfg = layer_cfg(run); p0 = lambda w: math.exp(-run["proc"]["lam"] / run["pages"] * max(0.0, w))
    v = simulate(sessions, gap, lat, cfg, crtt / 1000, run["dbDelayMs"] / 1000, p0)
    oc = outcomes(sessions, cfg); pages = [p for seq in sessions for p in seq]
    out, t = [], 0.0
    for k, ((w, l, _), (a, o)) in enumerate(zip(v, oc)):
        t_disp = t + gap(cfg["mode"], a, o) + (l - lat(cfg["mode"], a, o))
        out.append((pages[k], t_disp - w, t_disp)); t = t_disp
    return out


def realized(tl, lam, pages, rng):
    """Realized stale share of one run: Poisson writes, rate lam spread uniformly over the pages."""
    lo = min(min(x[1] for x in tl), 0.0); hi = max(x[2] for x in tl)
    writes = {p: [] for p in range(1, pages + 1)}
    t = lo
    while True:
        t += rng.expovariate(lam)
        if t > hi: break
        writes[rng.randint(1, pages)].append(t)
    st = 0
    for page, tau, td in tl:
        st += any(tau < w <= td for w in writes[page])
    return st / len(tl)


def block_sd(run, n_runs, users, length, reps=300, seed=0):
    """(mean, sd) of the block mean of n_runs realized stale shares under the model."""
    rng = random.Random(seed); means = []
    for _ in range(reps):
        vals = []
        for _ in range(n_runs):
            sess = sample_sessions(users, length, run["pages"], run["alpha"], rng.randrange(1 << 30))
            vals.append(realized(timeline(run, sess), run["proc"]["lam"], run["pages"], rng))
        means.append(sum(vals) / n_runs)
    mu = sum(means) / reps
    return mu, math.sqrt(sum((x - mu) ** 2 for x in means) / (reps - 1))


def z_of(a):
    """One-sided standard normal quantile z_{1-a} (bisection on erf; no scipy)."""
    lo, hi = 0.0, 6.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < 1 - a: lo = mid
        else: hi = mid
    return (lo + hi) / 2


def select(cands, eps, a, sd_m):
    """cands: name -> (L^, S^, sd_s). Returns the chosen name or None (abstain)."""
    z = z_of(a)
    ok = [c for c, (l, s, sd) in cands.items() if s + z * math.sqrt(sd * sd + sd_m * sd_m) <= eps]
    return min(ok, key=lambda c: cands[c][0]) if ok else None
