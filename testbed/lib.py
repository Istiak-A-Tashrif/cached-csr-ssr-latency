"""Shared loading/classification for analysis scripts (stdlib only).

Outcome classes per action:
  CSR: tq_hit (TanStack) | redis_hit | db
  SSR: next_hit (Next data cache) | redis_hit | db
"""
import json, os

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def jl(name):
    p = os.path.join(R, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def load(actions_file, runs_file):
    """Return (actions, runs, errors, unclassified); actions carry config + outcome `o`
    and `crtt` = measured client RTT of their run (mean of client->web and client->api)."""
    runs = {r["runId"]: r for r in jl(runs_file)}
    acts = [a for a in jl(actions_file) if a["runId"] in runs]
    # Server logs may live elsewhere (home path: server on server) -> SERVER_LOGS=<subdir of results>.
    srv = os.environ.get("SERVER_LOGS", "")
    api = jl(os.path.join(srv, "api.jsonl"))
    api_by_rid = {x["reqId"]: x for x in api if x.get("reqId")}
    api_by_resp = {x["respId"]: x for x in api if x.get("respId")}
    web_by_aid = {}
    for w in jl(os.path.join(srv, "web.jsonl")):
        if w.get("aid"):
            web_by_aid.setdefault(w["aid"], w)

    def outcome(a):
        if a["mode"] == "csr":
            if not a["tqRids"]:
                return "tq_hit"
            x = api_by_rid.get(a["tqRids"][-1])
        else:
            w = web_by_aid.get(a["aid"])
            if w is None:
                return None
            if w["nextCache"] == "hit":
                return "next_hit"
            x = api_by_resp.get(w["respId"])
        if x is None:
            return None
        return "redis_hit" if x["redis"] == "hit" else "db"

    errors = [a for a in acts if "error" in a]
    acts = [a for a in acts if "error" not in a]
    unclassified = []
    for a in acts:
        c = runs[a["runId"]]
        m = c["measuredRtt"]
        a.update(fe=c["fe"], be=c["be"], rtt=c["rtt"], irtt=c.get("irtt", 0), wl=c["wl"], seed=c["seed"],
                 crtt=(m["client_web"] + m["client_api"]) / 2, irtt_m=m["web_api"])
        a["o"] = outcome(a)
        if a["o"] is None:
            unclassified.append(a)
    return [a for a in acts if a["o"] is not None], runs, errors, unclassified


def linfit(xs, ys):
    """Least-squares y = a + b x."""
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b
