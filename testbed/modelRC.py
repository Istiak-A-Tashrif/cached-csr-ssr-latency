"""Model RC (TWEB revision B5, Conduit): model R with a per-page write probability. Conduit's writes
(favourites) target articles with the workload's popularity, so the no-write probability depends on
the page: p0(dt, page). Every other equation is model R's. Original model R description:

Revision model R (TWEB revision): experiment X's frozen timeline model with
(1) a general write process: every exp(-lam_p * dt) survival / staleness term of modelX is
    replaced by P0(dt), the declared process's probability of no write to the page in dt
    (writeproc.py); with Poisson writes P0 = exp(-lam_p dt) and R reproduces modelX exactly;
(2) an explicit per-view outcome distribution over {tq_hit, next_hit, redis_hit, db}
    (B1), the probabilities modelX already uses for its latency term d * P_db.
Calibration is modelX's (results/modelX.frozen.json: display gaps and no-write latency per
outcome from calibW); nothing is refitted.
"""
from staleness import RENDER_S, PUSH_LAG, layer_cfg, outcomes  # noqa: F401 (re-exported)


def simulate(sessions, gap, lat, cfg, crtt_s, d_s, p0):
    """Per view: (exposure window s, predicted latency s, outcome distribution dict)."""
    redis, nxt = {}, {}
    t = 0.0

    def api_read(page, t_req):
        if cfg["redis"] == "push":
            ent = redis.get(page)
            p_db = 1.0 if ent is None else 1 - p0(t_req - ent[2], page)
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
                p_db = 1 - p0(t + gap(cfg["mode"], action, o) - ent[2], page)
            elif o == "db":
                p_db = None
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
                    if cfg["redis"] == "push" and page in redis:
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
            dist = dict.fromkeys(("tq_hit", "next_hit", "redis_hit", "db"), 0.0)
            if o == "tq_hit": dist["tq_hit"] = 1.0
            elif o == "next_hit": dist["next_hit"] = 1 - p_db; dist["db"] = p_db
            elif cfg["redis"]: dist["db"] = p_db; dist["redis_hit"] = 1 - p_db
            else: dist["db"] = 1.0
            views.append((t_disp - tau, lat(cfg["mode"], action, o) + extra, dist, page))
            t = t_disp
    return views


def stale_fraction(views, p0):
    return sum(1 - p0(w, page) for w, _, _, page in views) / len(views)


def page_p0(proc, probs):
    """p0(dt, page) from writeproc's formulas: a write reaching page n with probability probs[n] is the
    uniform-thinning case with an effective page count of 1 / probs[n] (exact for every process)."""
    from writeproc import p0_factory
    f = {n: p0_factory(proc, 1.0 / p) for n, p in probs.items()}
    return lambda dt, page: f[page](dt)
