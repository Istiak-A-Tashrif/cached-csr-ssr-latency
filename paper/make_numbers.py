#!/usr/bin/env python3
"""Every number the manuscript states about the TWEB-revision analyses, as LaTeX macros, generated from
the analysis outputs (testbed/results/revision/*.json) -- no result is typed by hand. A missing input
defines its macros as "??" so a draft still compiles; the submitted paper has none.
usage: python3 paper/make_numbers.py   -> paper/numbers.tex"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
REV = os.path.join(HERE, "..", "testbed", "results", "revision")
M = {}


def load(name):
    p = os.path.join(REV, name)
    return json.load(open(p)) if os.path.exists(p) else None


def put(name, value, fmt="{:.2f}"):
    assert re.fullmatch(r"[A-Za-z]+", name), name
    M[name] = value if isinstance(value, str) else fmt.format(value)


def rng(vals, fmt="{:.2f}"):
    lo, hi = fmt.format(min(vals)), fmt.format(max(vals))
    return lo if lo == hi else f"{lo}--{hi}"


# ---- A1 ablation ----
a1 = load("A1-ablation.json")
if a1:
    by = {r["tag"]: r for r in a1}
    h1 = ["prosp5", "rep5", "real7", "rep7", "real8b", "rep8b", "testS", "repS", "testQ", "repQ"]
    put("AoneFullHone", rng([by[t]["full"]["mean"] for t in h1]))
    put("AoneNoRhoHone", rng([by[t]["no_rho"]["mean"] for t in h1]))
    put("AoneServiceAll", rng([by[t]["service"]["mean"] for t in by if t not in ("realH3", "repH3")], "{:.0f}"))
    put("AoneNoRhoVnine", rng([by[t]["no_rho"]["mean"] for t in ("real9", "rep9")], "{:.1f}"))
    put("AoneNoRhoVnineb", rng([by[t]["no_rho"]["mean"] for t in ("test9b", "reptest9b")], "{:.1f}"))
    put("AoneFullHome", rng([by[t]["full"]["mean"] for t in ("realH3", "repH3")], "{:.1f}"))
    put("AoneNoRhoHome", rng([by[t]["no_rho"]["mean"] for t in ("realH3", "repH3")], "{:.1f}"))
    put("AonePooledQ", rng([by[t]["pooled_T0"]["mean"] for t in ("testQ", "repQ")], "{:.1f}"))
    put("AoneNoRhoQ", rng([by[t]["no_rho"]["mean"] for t in ("testQ", "repQ")], "{:.1f}"))
    put("AoneNoRhoRtwo", rng([by[t]["no_rho"]["mean"] for t in ("testR2", "repR2")], "{:.1f}"))
    abun = [by[t]["no_rho_abun"]["mean"] for t in ("real7", "rep7", "real8b", "rep8b") if "no_rho_abun" in by[t]]
    if abun: put("AoneAbunReal", rng(abun, "{:.1f}"))
# ---- A2 baselines / A4 paired uncertainty ----
a2 = load("A2-baselines.json")
if a2:
    put("AtwoTests", str(len(a2)))
    put("AtwoRidge", rng([r["all:ridge"][0] for r in a2]))
    put("AtwoTrees", rng([min(r["all:rf"][0], r["all:gbt"][0]) for r in a2], "{:.1f}"))
    put("AtwoModelWins", str(sum(r["all:model"][0] < r["all:ridge"][0] for r in a2)))
    put("AtwoOutCells", str(sum((r["out:model"] or [0, 0, 0])[2] for r in a2)))
a4 = load("A4-uncertainty.json")
if a4:
    L = a4["latency"]
    put("AfourSig", str(sum(r["diff"][2] < 0 for r in L)))
    put("AfourTie", str(sum(r["diff"][1] <= 0 <= r["diff"][2] for r in L)))
    put("AfourRidgeSig", str(sum(r["diff"][1] > 0 for r in L)))
    put("AfourTests", str(len(L)))
    put("AfourTwoSeed", str(sum(r["seeds_per_cell"] == 2 for r in L)))
    L4 = [r for r in L if r["seeds_per_cell"] >= 4]
    put("AfourFourSeed", str(len(L4))); put("AfourSigFour", str(sum(r["diff"][2] < 0 for r in L4)))
    put("AfourTieFour", str(sum(r["diff"][1] <= 0 <= r["diff"][2] for r in L4)))
    S = a4["staleness"]
    put("AfourStaleIn", str(sum(s["pred_in_ci"] for s in S)))
    put("AfourStaleCells", str(len(S)))
    nav = [t["p99"] for t in a4["tails"] if t["path"].endswith("nav") and t["tag"] in ("real7", "rep7", "real8b", "rep8b", "real9", "rep9")]
    put("AfourNavPninetyNine", rng(nav, "{:.1f}"))
# ---- A5 oracle checks ----
a5 = load("A5-staleness-checks.json")
if a5:
    put("AfiveViews", f"{sum(v['views'] for v in a5.values()):,}".replace(",", "{,}"))
    put("AfiveShift", "{:.3f}".format(max(abs(v["stale@+20ms"] - v["stale@+0ms"]) for v in a5.values()) + 0.0))
    put("AfiveShiftMax", "{:.3f}".format(max(max(abs(v["stale@+20ms"] - v["stale@+0ms"]), abs(v["stale@-20ms"] - v["stale@+0ms"])) for v in a5.values())))
# ---- B1 offline ----
b1 = load("B1-offline.json")
if b1:
    ks = [k for k in b1 if k in ("testW2", "repW2", "testX", "repX")]
    put("BoneOffBrier", rng([b1[k]["brier"] for k in ks], "{:.3f}"))
    put("BoneOffSkill", rng([b1[k]["skill"] for k in ks], "{:.2f}"))
    put("BoneOffTop", rng([100 * b1[k]["top1"] for k in ks], "{:.0f}"))
# ---- B4 offline ----
b4 = load("B4-offline.json")
if b4:
    regs, nocache = [], []
    for t in ("testX", "repX"):
        for row in b4[t]["selection"].values():
            if row["selector"].get("regret") is not None: regs.append(row["selector"]["regret"])
            if row["nocache"].get("regret") is not None: nocache.append(row["nocache"]["regret"])
    put("BfourOffMaxRegret", "{:.1f}".format(100 * max(regs)))
    put("BfourOffNocache", rng([100 * x for x in nocache], "{:.0f}"))
    put("BfourCalibRuns", str(b4["cost"]["model_calibration_runs"]))
# ---- fresh revision blocks ----
def crit_nums(prefix, ev):
    cr = ev["criteria"]
    num = lambda k, pat: float(re.search(pat, cr[k][1]).group(1))
    put(f"{prefix}Wone", "{:.3f}".format(num("W1 pooled MAE <= 0.03", r"([\d.]+)")))
    put(f"{prefix}Wtwo", "{:.3f}".format(num("W2 every cell within 0.05", r"max ([\d.]+)")))
    put(f"{prefix}Wthree", re.search(r"(\d+/\d+)", cr["W3 orderings"][1]).group(1).replace("/", " of "))
    put(f"{prefix}Lone", "{:.2f}".format(num("L1 mean latency error <= 3%", r"([\d.]+)%")))
    put(f"{prefix}Ltwo", "{:.2f}".format(num("L2 every (cell, action) within max(5%, 10 ms)", r"max ([\d.]+)%")))
    put(f"{prefix}Brier", "{:.3f}".format(num("O2 Brier skill > 0", r"Brier ([\d.]+)")))
    if "O1' noise-aware calibration" in cr: put(f"{prefix}OonePrime", "passed" if cr["O1' noise-aware calibration"][0] else "failed")
    put(f"{prefix}Skill", "{:.2f}".format(num("O2 Brier skill > 0", r"skill ([+-][\d.]+)")))
    put(f"{prefix}Top", "{:.1f}".format(100 * num("O2 Brier skill > 0", r"top-1 ([\d.]+)")))
    put(f"{prefix}Excess", "{:.3f}".format(num("O3 Brier - expected Brier <= 0.03", r"([+-][\d.]+)")))
    put(f"{prefix}Verdict", "passed" if all(v[0] for v in cr.values()) else "failed")
    put(f"{prefix}Fails", ", ".join(k.split()[0] for k, v in cr.items() if not v[0]) or "none")
    if "B4a mean selector regret <= 5%" in cr:
        put(f"{prefix}Regret", "{:.2f}".format(num("B4a mean selector regret <= 5%", r"mean ([\d.]+)%")))
        put(f"{prefix}RegretWorst", "{:.2f}".format(num("B4a mean selector regret <= 5%", r"worst ([\d.]+)%")))
        put(f"{prefix}Decisions", re.search(r"over (\d+) feasible", cr["B4a mean selector regret <= 5%"][1]).group(1))
        put(f"{prefix}Viol", re.search(r"(\d+) confirmed", cr["B4b no confirmed constraint violation"][1]).group(1))
        sel = ev.get("selection", {})
        for m in ("tuning", "fixed", "default", "nocache"):
            regs = [r[m]["regret"] for r in sel.values() if not r[m].get("abstain") and r[m].get("regret") is not None]
            viol = sum(1 for r in sel.values() if not r[m].get("abstain") and r[m].get("violation"))
            put(f"{prefix}{m.capitalize()}Regret", "{:.1f}".format(100 * sum(regs) / len(regs)) if regs else "--")
            put(f"{prefix}{m.capitalize()}Viol", str(viol))


for file, prefix in (("revT", "revT"), ("revR", "revR"), ("revB2T", "revBTwoT"), ("revB2R", "revBTwoR"), ("cdT", "cdT"), ("cdR", "cdR"),
                     ("cdHT", "cdHT"), ("cdHR", "cdHR"), ("cdT-zero", "cdTZero"), ("cdR-zero", "cdRZero"), ("cdHT-zero", "cdHTZero"), ("cdHR-zero", "cdHRZero")):
    ev = load(f"{file}-evaluation.json")
    if ev: crit_nums(prefix, ev)
dg = load("diag-stale.json")
if dg:
    for t, p in (("revT", "revT"), ("revR", "revR"), ("revB2T", "revBTwoT"), ("revB2R", "revBTwoR")):
        if t in dg: put(f"{p}Inside", f"{dg[t]['inside']} of {dg[t]['cells']}")


# ---- post-hoc diagnoses (second review) ----
dp = load("diag-push.json")
if dp:
    for t in ("revT", "revR"):
        tr = dp[t]["transitions"]; P = t[3:]
        wf = tr.get("True|fetched", 0); wc = tr.get("True|cache", 0); nf = tr.get("False|fetched", 0); nc = tr.get("False|cache", 0)
        put(f"diagPush{P}WriteFetched", "{:.0f}".format(100 * wf / (wf + wc)))
        put(f"diagPush{P}NoWriteCache", "{:.1f}".format(100 * nc / (nc + nf)))
        la = dp[t]["last_access"]
        for k, n in (("pred_R", "PredR"), ("pred_R2", "PredRtwo"), ("formula_observed_gap", "Formula"), ("observed_fetched", "Obs")):
            put(f"diagPush{P}{n}", "{:.3f}".format(la[k]))
for t in ("revT", "revR"):
    on = load(f"diag-o1-noise-{t}.json")
    if on:
        half = [(x["hi"] - x["lo"]) / 2 for x in on]
        put(f"diagNoise{t[3:]}Half", rng(half, "{:.3f}"))
        put(f"diagNoise{t[3:]}Excl", str(sum(1 for x in on if x["lo"] > 0 or x["hi"] < 0)))
        put(f"diagNoise{t[3:]}Deciles", str(len(on)))
        put(f"diagNoise{t[3:]}MaxExcl", "{:.3f}".format(max([abs(x["dev"]) for x in on if x["lo"] > 0 or x["hi"] < 0] or [0])))
dc = load("diag-decomp.json")
if dc:
    for t, P in (("revT", "revT"), ("revR", "revR"), ("revB2T", "revBTwoT")):
        put(f"diagDec{P}Declared", "{:.3f}".format(dc[t]["mae_declared"])); put(f"diagDec{P}Realized", "{:.3f}".format(dc[t]["mae_realized"]))
    w = max(dc["revB2T"]["cells"].items(), key=lambda kv: abs(kv[1]["total"]))[1]
    put("diagDecTraceTotal", "{:.3f}".format(abs(w["total"]))); put("diagDecTraceRate", "{:.3f}".format(abs(w["rate"])))
ds = load("diag-stale.json")
if ds and ds["revB2T"]["trace_rate_min"]:
    put("diagTraceRate", rng([ds["revB2T"]["trace_rate_min"], ds["revB2T"]["trace_rate_max"]], "{:.1f}"))
    put("diagTraceDeclared", "{:.1f}".format(ds["revB2T"]["declared"]))
for t, P in (("revT", "revT"), ("revR", "revR"), ("cdT", "cdT"), ("cdR", "cdR")):
    d = load(f"distonly-{t}.json")
    if d:
        put(f"dist{P}WoneDec", "{:.3f}".format(d["dec"]["W1"])); put(f"dist{P}WoneDist", "{:.3f}".format(d["dist"]["W1"]))
        put(f"dist{P}LoneDec", "{:.2f}".format(d["dec"]["L1"])); put(f"dist{P}LoneDist", "{:.2f}".format(d["dist"]["L1"]))
for file, prefix in (("revHT", "revHT"), ("revHR", "revHR")):
    ev = load(f"{file}-evaluation.json")
    if ev:
        crit_nums(prefix, ev)
        for sname, s_ in ev.get("selectors", {}).items():
            P = prefix + sname.capitalize()
            put(f"{P}Dec", str(s_["decisions"])); put(f"{P}Viol", str(s_["violations"])); put(f"{P}Conf", str(s_["confirmed"]))
            put(f"{P}Right", str(s_["oracle_choices"])); put(f"{P}Regret", "{:.1f}".format(s_["mean_regret"])); put(f"{P}Worst", "{:.1f}".format(s_["worst_regret"]))

for file, P in (("revB2T", "revBTwoT"), ("revB2R", "revBTwoR")):
    ev = load(f"{file}-evaluation.json")
    if ev:
        for proc in ("periodic", "onoff", "trace"):
            e = [abs(o - p) for c, (o, p) in ev["stale"].items() if c.endswith(proc)]
            put(f"{P}{proc.capitalize()}Mae", "{:.3f}".format(sum(e) / len(e))); put(f"{P}{proc.capitalize()}Max", "{:.3f}".format(max(e)))

dm = load("diag-margin.json")
if dm:
    for k, P in (("0.0", "Zero"), ("0.02", "Two"), ("0.03", "Three"), ("0.05", "Five"), ("0.07", "Seven")):
        d = dm[k]; put(f"margin{P}Viol", str(d.get("viol", 0))); put(f"margin{P}Abst", str(d.get("abstain", 0)))
        put(f"margin{P}Right", str(d.get("right", 0))); put(f"margin{P}Regret", "{:.1f}".format(d["mean_regret"])); put(f"margin{P}Dec", str(d["decisions"]))
    import math
    n = dm["0.05"]["decisions"]; put("marginUpper", "{:.0f}".format(100 * (1 - 0.05 ** (1 / n))))

db = load("decision-baselines.json")
if db:
    PRED = (("model", "Model"), ("ridge/model", "Ridge"), ("calfreq/model", "Calfreq"), ("blind/model", "Blind"),
            ("model/single", "Single"), ("calfreq/single", "Simple"), ("tuning", "Tuning"), ("fixed", "Fixed"),
            ("default", "Default"), ("nocache", "Nocache"))
    num = lambda x: "{:.0f}".format(x) if abs(x - round(x)) < 1e-9 else "{:.1f}".format(x)
    for grp, kind, flt in (("Cat", "b4", lambda i: True), ("Hard", "hard", lambda i: i.endswith("|margin")),
                           ("HardPt", "hard", lambda i: i.endswith("|point")), ("Cc", "cc", lambda i: i.endswith("|margin")),
                           ("CcPt", "cc", lambda i: i.endswith("|point"))):
        put(f"dec{grp}Scen", str(sum(b["scenarios"] for b in db if b["kind"] == kind)))
        for key, P in PRED:
            rs = [r for b in db if b["kind"] == kind for r in b["per_decision"].get(key, []) if flt(r["id"])]
            if not rs: continue
            sel = [r for r in rs if not r["abstain"]]; reg = [r["regret"] for r in sel if r["regret"] is not None]
            put(f"dec{grp}{P}N", str(len(rs))); put(f"dec{grp}{P}Viol", num(sum(r["viol"] for r in sel)))
            put(f"dec{grp}{P}Exc", "{:.2f}".format(max([r["excess"] for r in sel] or [0.0])))
            if "confirmed" in rs[0]: put(f"dec{grp}{P}Conf", num(sum(r["confirmed"] for r in sel)))
            put(f"dec{grp}{P}Mean", "{:.1f}".format(100 * sum(reg) / len(reg)) if reg else "--")
            put(f"dec{grp}{P}Worst", "{:.1f}".format(100 * max(reg)) if reg else "--")
    put("decLonePred", rng([b["L1_predicted_layer"] for b in db])); put("decLoneTrue", rng([b["L1_true_layer"] for b in db]))
    put("decLoneGap", "{:.2f}".format(max(abs(b["L1_predicted_layer"] - b["L1_true_layer"]) for b in db)))
    put("decBlocks", str(len(db)))
    put("decSingleSig", str(sum(b["bootstrap"]["model/single"]["viol_diff_ci"][0] > 0 for b in db)))
    put("decBlindSig", str(sum(b["bootstrap"]["blind/model"]["regret_diff_ci"][0] > 0 for b in db)))
    put("decCalfreqSig", str(sum(b["bootstrap"]["calfreq/model"]["regret_diff_ci"][0] > 0 for b in db)))
    put("decRidgeSig", str(sum(b["bootstrap"]["ridge/model"]["regret_diff_ci"][0] > 0 or b["bootstrap"]["ridge/model"]["regret_diff_ci"][1] < 0 for b in db)))

for tag, P in (("revCCT", "ccT"), ("revCCR", "ccR")):   # protocol v4 (chance-constrained selector)
    ev = load(f"{tag}-evaluation.json")
    if ev:
        crit_nums(P, ev)
        for sname, s_ in ev["selectors"].items():
            Q = P + sname.capitalize()
            put(f"{Q}Dec", str(s_["decisions"])); put(f"{Q}Viol", str(s_["violations"])); put(f"{Q}Conf", str(s_["confirmed"]))
            put(f"{Q}Right", str(s_["oracle_choices"])); put(f"{Q}Regret", "{:.1f}".format(s_["mean_regret"])); put(f"{Q}Worst", "{:.1f}".format(s_["worst_regret"]))
        put(f"{P}Same", str(sum(r["cc"].get("pick") == r["margin"].get("pick") for r in ev["selection"].values())))
        mg = ev["cc_margin"]; put(f"{P}MarginMin", "{:.3f}".format(min(mg.values()))); put(f"{P}MarginMax", "{:.3f}".format(max(mg.values())))
der = load("cc-derivation.json")
if der:
    put("ccSdm", "{:.4f}".format(der["sd_m"])); put("ccRmse", "{:.3f}".format(der["rmse"])); put("ccRmsSds", "{:.3f}".format(der["rms_sd_s"]))
    put("ccCells", str(len(der["cells"]))); put("ccWithin", "{:.0f}".format(100 * der["frac_within"]))

with open(os.path.join(HERE, "numbers.tex"), "w") as f:
    f.write("% Generated by make_numbers.py from testbed/results/revision; do not edit.\n")
    for k, v in sorted(M.items()):
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(len(M), "macros ->", os.path.join(HERE, "numbers.tex"))
