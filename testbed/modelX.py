"""Server-work regime model (experiment X): latency AND staleness per caching policy when each
database read costs an extra d seconds of server work.

Extends the staleness model (staleness.py, modelW) with the expected probability that a view
triggers a database read, P_db:
  Redis ttl T      entry younger than T: hit (no DB); otherwise refill (DB read).
  Redis push       the entry survives until the next write to its page; it exists after every
                   access, so P(entry present at t) = exp(-lam_p * (t - last access)).
  Next ttl R       stale-while-revalidate: after the first fill every request is served from
                   the cache (refreshes happen in the background, off the latency path).
  Next push        same survival law as Redis push; the write that drops the Next entry also
                   drops the Redis key behind it, so a Next miss is a DB read.
  TanStack         a revisit shows the cached entry (background refetch, off the path).
  no cache         every view reads the DB.
Latency of a view = L0(mode, action, outcome, RTT) + d * P_db, where L0 is the calibrated
no-write latency (calibW, d = 0); the display gap grows by the same d * P_db. Staleness windows
follow staleness.py (tau semantics), on the shifted timeline.
"""
import math
from staleness import RENDER_S, PUSH_LAG, layer_cfg, outcomes  # noqa: F401 (re-exported)


def simulate(sessions, gap, lat, cfg, crtt_s, d_s, lam_p):
    """Per view: (exposure window s, predicted latency s, P_db). gap/lat(mode, action, outcome) -> s."""
    redis, nxt = {}, {}             # redis: page -> (tau, fill, last access); nxt: page -> (tau, fill, last access)
    t = 0.0
    surv = lambda dt: math.exp(-lam_p * max(0.0, dt))

    def api_read(page, t_req):
        """(tau, P_db) of data the API returns at t_req."""
        # A DB read happens after the added work (pg_sleep precedes the query): its data is as of t_req + d.
        if cfg["redis"] == "push":
            ent = redis.get(page)
            p_db = 1.0 if ent is None else 1 - surv(t_req - ent[2])
            redis[page] = (t_req + d_s, t_req + d_s, t_req)
            return t_req + p_db * d_s - (1 - p_db) * PUSH_LAG, p_db
        if cfg["redis"] == "ttl":
            ent = redis.get(page)
            if ent and t_req - ent[1] < cfg["redis_t"]:
                return ent[0], 0.0
            redis[page] = (t_req + d_s, t_req + d_s, t_req)
        return t_req + d_s, 1.0

    views, oc = [], iter(outcomes(sessions, cfg))
    for seq in sessions:
        tq = {}
        for page in seq:
            action, o = next(oc)
            p_db = 0.0
            if o == "tq_hit":
                tau, fetched = tq[page]
            elif o == "next_hit" and cfg["next"] == "push":
                ent = nxt[page]
                p_db = 1 - surv(t + gap(cfg["mode"], action, o) - ent[2])   # dropped by a write -> DB
            elif o == "db":
                p_db = None                                                   # decided by the API below
            extra = d_s * (p_db or 0.0)
            t_disp = t + gap(cfg["mode"], action, o) + extra
            t_req = t_disp - crtt_s / 2 - RENDER_S - extra
            if o == "tq_hit":
                if t_disp - fetched >= cfg["tanstack_s"]:
                    bg = t_disp + crtt_s / 2
                    tq[page] = (api_read(page, bg)[0], bg)
            elif o == "next_hit":
                if cfg["next"] == "push":
                    tau = t_req + p_db * d_s - (1 - p_db) * PUSH_LAG
                    nxt[page] = (tau, nxt[page][1], t_req)
                    if cfg["redis"] == "push" and page in redis:          # a miss refilled Redis too
                        redis[page] = (redis[page][0], redis[page][1], t_req)
                else:
                    tau, fill, _ = nxt[page]
                    if t_req - fill >= cfg["next_r"]:
                        nxt[page] = (api_read(page, t_req)[0], t_req, t_req)
            else:
                tau, p_db = api_read(page, t_req)
                extra = d_s * p_db
                t_disp += extra
                if cfg["tanstack_s"] is not None: tq[page] = (tau, t_req)
                if cfg["next"]: nxt[page] = (tau, t_req, t_req)
            views.append((t_disp - tau, lat(cfg["mode"], action, o) + extra, p_db))
            t = t_disp
    return views


def stale_fraction(views, lam_p):
    return sum(1 - math.exp(-lam_p * max(0.0, w)) for w, _, _ in views) / len(views)
