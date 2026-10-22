"""Write processes for the staleness and outcome models (TWEB revision, B2).

P0(w): probability that no write reaches a given page in a window of length w seconds, from the
DECLARED process (or, for the trace, from its training window only). A write updates a product
drawn uniformly over the workload's pages, so it reaches a given page with probability 1/pages
(thinning). Every write increments a value (api/server.js), so a page whose data is older than a
write to it is stale: P(stale | window w) = 1 - P0(w), and an entry purged on every write survives
an interval of w with probability P0(w). For non-Poisson processes these are marginal (stationary)
probabilities; consecutive windows are not independent, which leaves expected stale shares exact
but not their variance.
  poisson   rate lam                      P0 = exp(-lam w / pages)
  periodic  every 1/lam s, uniform phase  N(w) in {k, k+1}, P(k+1) = w lam - k;  P0 = E[q^N]
  onoff     Poisson(onRate) during ON (exp mean onMean s), silent during OFF (exp mean offMean s),
            stationary start             P0 = pi exp((Q - L) w) 1, a 2-state MMPP, L = diag(onRate/pages, 0)
  trace     compressed trace timestamps   P0 = mean over start times s of the training window of
                                          q^N(s, s+w)   (empirical, no parametric form)
with q = 1 - 1/pages.
"""
import bisect, datetime, json, math, os

TRACE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces", "dewiki-rc-20261014.json")
TRACE_START = datetime.datetime(2026, 10, 14, 8, tzinfo=datetime.timezone.utc).timestamp()
SPLIT_S = 3 * 3600   # hours 1-3 training, hours 4-6 test


def expm2(a, t):
    """exp(A t) for a real 2x2 matrix A with real eigenvalues (true for Q - L here)."""
    (p, q), (r, s) = a
    m = (p + s) / 2; d2 = m * m - (p * s - q * r); d = math.sqrt(max(d2, 0.0))
    e = math.exp(m * t)
    if d < 1e-12:
        c, k = 1.0, t
    else:
        c, k = math.cosh(d * t), math.sinh(d * t) / d
    return [[e * (c + k * (p - m)), e * k * q], [e * k * r, e * (c + k * (s - m))]]


def trace_times(window, compress):
    """Event times (s, from the window start) of the training or test window, compressed by
    `compress`; events sharing a 1 s timestamp are spread evenly over that second."""
    ev = json.load(open(TRACE))["events"]
    secs = sorted(datetime.datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).timestamp() - TRACE_START for e in ev)
    lo, hi = (0, SPLIT_S) if window == "train" else (SPLIT_S, 2 * SPLIT_S)
    secs = [s - lo for s in secs if lo <= s < hi]
    out, i = [], 0
    while i < len(secs):
        j = i
        while j < len(secs) and secs[j] == secs[i]: j += 1
        k = j - i
        out += [(secs[i] + (n + 0.5) / k) / compress for n in range(k)]
        i = j
    return out, (hi - lo) / compress


def trace_rate(window="train"):
    t, span = trace_times(window, 1.0)
    return len(t) / span


def p0_factory(proc, pages):
    """proc: {"kind": ..., params}; returns P0(w) for w in seconds."""
    q = 1 - 1 / pages
    kind = proc.get("kind", "poisson")
    if kind == "poisson":
        lp = proc["lam"] / pages
        return lambda w: math.exp(-lp * max(0.0, w))
    if kind == "periodic":
        lam = proc["lam"]

        def f(w):
            x = max(0.0, w) * lam; k = math.floor(x); fr = x - k
            return (1 - fr) * q ** k + fr * q ** (k + 1)
        return f
    if kind == "onoff":
        a, b, lr = 1 / proc["onMean"], 1 / proc["offMean"], proc["onRate"] / pages
        pi_on = proc["onMean"] / (proc["onMean"] + proc["offMean"])
        A = [[-a - lr, a], [b, -b]]

        def f(w):
            E = expm2(A, max(0.0, w))
            return pi_on * (E[0][0] + E[0][1]) + (1 - pi_on) * (E[1][0] + E[1][1])
        return f
    if kind == "trace":
        t, span = trace_times("train", proc["compress"])
        grid_w = [i * 0.05 for i in range(0, 2401)]                 # 0..120 s
        starts = [span * (i + 0.5) / 4000 for i in range(4000)]     # deterministic start grid
        table = []
        for w in grid_w:
            acc = 0.0
            for s in starts:
                if s + w > span: continue
                n = bisect.bisect_left(t, s + w) - bisect.bisect_left(t, s)
                acc += q ** n
            table.append(acc / sum(1 for s in starts if s + w <= span))

        def f(w):
            w = max(0.0, w); i = min(len(grid_w) - 2, int(w / 0.05))
            if w >= grid_w[-1]: return table[-1]
            return table[i] + (table[i + 1] - table[i]) * (w - grid_w[i]) / 0.05
        return f
    raise ValueError(kind)
