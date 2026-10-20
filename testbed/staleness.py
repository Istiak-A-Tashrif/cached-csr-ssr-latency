"""Staleness model (item 8): predicts the share of page views that DISPLAY stale data.

Writes are Poisson, LAM writes/s in total, uniform over the products on the workload's
pages, so each page receives writes at lam_p = LAM / pages. Every piece of data carries
tau, the instant at which it was guaranteed equal to the DB. A view displayed at t_disp
showing data with tau is stale iff a write to its page landed in (tau, t_disp]:
    P(stale) = 1 - exp(-lam_p * (t_disp - tau)).
Predicted stale fraction = mean P over the run's views.

The timeline replays the run's DECLARED sessions; the gap between consecutive displays is
calibrated without writes per (mode, action, outcome), action in {initial, nav1, nav} as a linear function of client RTT
(freezeW.py). A request reaches the server side about half a client RTT plus render
(RENDER_S) before display.
Layer semantics (tau of the data each layer returns):
  DB read                   tau = t_req.
  Redis ttl T               hit (age < T): tau of the fill; otherwise refill, tau = t_req.
  Redis push                an entry is deleted on every write to its page, so whatever is
                            returned (hit or refill) is fresh except for writes within the
                            purge lag: tau = t_req - PUSH_LAG.
  Next data cache ttl R     stale-while-revalidate: always serves the entry (its tau); when
                            older than R it is refreshed in the background via the API.
  Next data cache push      tag revalidated (hard expiry) on every write: tau = t_req - PUSH_LAG
                            (the cell uses Redis push behind it, so a refill is fresh too).
  TanStack (CSR) staleTime S, gcTime infinite, per browser session: a revisit SHOWS the
                            cached entry (its tau); if older than S it refetches in the
                            background (refetch reaches the API ~half an RTT after display).
"""
import math

RENDER_S = 0.010   # data arrival -> visible (render + frame), seconds
PUSH_LAG = 0.002   # write commit -> Redis key + Next tag purged (measured ~1 ms), seconds


def layer_cfg(run):
    """Model config from a harness run record (item 8 cells)."""
    fe, rp = run["fe"] or None, run["rp"] or None
    return {
        "mode": run["mode"],
        "tanstack_s": run["S"] if run["mode"] == "csr" and fe else None,
        "next": fe if run["mode"] == "ssr" else None, "next_r": run["S"],
        "redis": rp, "redis_t": run["T"],
    }


def outcomes(sessions, cfg):
    """Timing-independent outcome class per view: 'db' (fetched through the API),
    'tq_hit' (TanStack entry shown) or 'next_hit' (Next data cache entry served)."""
    out, nxt = [], set()
    for seq in sessions:
        tq = set()
        for step, page in enumerate(seq):
            if cfg["mode"] == "csr" and cfg["tanstack_s"] is not None and page in tq:
                o = "tq_hit"
            elif cfg["mode"] == "ssr" and cfg["next"] and page in nxt:
                o = "next_hit"
            else:
                o = "db"
            tq.add(page); nxt.add(page)
            # The first navigation of a session is its own gap class: after an SSR initial
            # display the harness waits for hydration (several RTTs) before navigating.
            out.append(("initial" if step == 0 else "nav1" if step == 1 else "nav", o))
    return out


def simulate(sessions, gap, cfg, crtt_s):
    """Exposure window (s) per view. gap(mode, action, outcome) -> seconds between
    the previous display and this one."""
    redis, nxt = {}, {}                  # page -> (tau, fill time)
    t = 0.0

    def api_read(page, t_req):
        if cfg["redis"] == "push":
            redis[page] = (t_req, t_req)
            return t_req - PUSH_LAG
        if cfg["redis"] == "ttl":
            ent = redis.get(page)
            if ent and t_req - ent[1] < cfg["redis_t"]:
                return ent[0]
            redis[page] = (t_req, t_req)
        return t_req

    views, oc = [], iter(outcomes(sessions, cfg))
    for seq in sessions:
        tq = {}                                          # page -> (tau, fetched at)
        for page in seq:
            action, o = next(oc)
            t_disp = t + gap(cfg["mode"], action, o)
            t_req = t_disp - crtt_s / 2 - RENDER_S
            if o == "tq_hit":
                tau, fetched = tq[page]
                if t_disp - fetched >= cfg["tanstack_s"]:     # stale: shown, then refetched
                    bg = t_disp + crtt_s / 2
                    tq[page] = (api_read(page, bg), bg)
            elif o == "next_hit":
                if cfg["next"] == "push":
                    tau = t_req - PUSH_LAG
                else:
                    tau, fill = nxt[page]
                    if t_req - fill >= cfg["next_r"]:          # SWR: serve old, refresh behind
                        nxt[page] = (api_read(page, t_req), t_req)
            else:
                tau = api_read(page, t_req)
                if cfg["tanstack_s"] is not None:
                    tq[page] = (tau, t_req)
                if cfg["next"]:
                    nxt[page] = (tau, t_req)
            views.append(t_disp - tau)
            t = t_disp
    return views


def predicted_stale_fraction(windows, lam_p):
    return sum(1 - math.exp(-lam_p * max(0.0, w)) for w in windows) / len(windows)
