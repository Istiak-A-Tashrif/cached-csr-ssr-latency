#!/usr/bin/env python3
"""Figures and summary tables for the paper, parsed from the committed evaluation outputs
(testbed/results/**/-evaluation.txt). Run from anywhere:  python3 paper/make_figs.py
Writes paper/figs/*.pdf and paper/tables/*.tex."""
import os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "testbed", "results")
FIG, TAB = os.path.join(HERE, "figs"), os.path.join(HERE, "tables")
os.makedirs(FIG, exist_ok=True); os.makedirs(TAB, exist_ok=True)

# Validated categorical slots 1-3 (light): blue, orange, aqua. Text stays neutral ink.
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "lines.linewidth": 1.0,
    "legend.frameon": False, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def path(tag):
    for sub in ("", "server-final", "server-R2"):
        p = os.path.join(RES, sub, f"{tag}-evaluation.txt")
        if os.path.exists(p): return p
    raise FileNotFoundError(tag)


CELL = re.compile(r"^\s+(initial|nav)\s+(csr|ssr) caches=(on |off) crtt=\s*(\d+) irtt=\s*(\d+): obs\s+([\d.]+) .*pred\s+([\d.]+)")
def cells(tag):
    out = []
    for l in open(path(tag)):
        m = CELL.match(l)
        if m: out.append({"action": m[1], "mode": m[2], "caches": m[3].strip(), "rtt": int(m[4]), "obs": float(m[6]), "pred": float(m[7])})
    return out

def summary(tag):
    t = open(path(tag)).read()
    m = re.search(r"mean rel error ([\d.]+)%\s+max ([\d.]+)%", t)
    crit = re.findall(r"(PASS|FAIL)\s+(C\d)", t)
    return float(m[1]), float(m[2]), {c: r for r, c in crit}, "NOT ACCEPTED" not in t

STALE = re.compile(r"^(csr|ssr)-fe(\w+)-redis(\w+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)")
LAT = re.compile(r"^(csr|ssr)-fe(\w+)-redis(\w+) (initial|nav)\s+([\d.]+)\s+([\d.]+)")
def stale(tag):
    return [{"mode": m[1], "fe": m[2], "rd": m[3], "obs": float(m[5]), "pred": float(m[6])}
            for m in map(STALE.match, open(path(tag))) if m]
def latx(tag):
    return [{"mode": m[1], "fe": m[2], "rd": m[3], "action": m[4], "obs": float(m[5]), "pred": float(m[6])}
            for m in map(LAT.match, open(path(tag))) if m]


# ---------- Fig. 2: predicted vs observed, every cell of every fresh latency test ----------
GROUPS = [
    ("Emulated, accepted (v5, SvelteKit, heavy page, v9b)", C1, "o", ["prosp5", "rep5", "testS", "repS", "testQ", "repQ", "reptest9b"]),
    ("Real network, accepted (v7, v8b, v9)", C2, "s", ["real7", "rep7", "real8b", "rep8b", "real9", "rep9"]),
    ("Near-misses (concurrency P3/P4, slow devices R2)", C3, "^", ["concP3", "repP3", "concP4", "repP4", "testR2", "repR2"]),
]
fig, ax = plt.subplots(figsize=(3.4, 3.1))
lo, hi = 25, 8000
ax.fill_between([lo, hi], [lo * 0.95, hi * 0.95], [lo * 1.05, hi * 1.05], color=GRID, lw=0, zorder=0, label="±5% band")
ax.plot([lo, hi], [lo, hi], color=INK2, lw=0.7, zorder=1)
n_cells = 0
for name, col, mk, tags in GROUPS:
    xs, ys = [], []
    for t in tags:
        for c in cells(t): xs.append(c["obs"]); ys.append(c["pred"])
    n_cells += len(xs)
    ax.scatter(xs, ys, s=12, marker=mk, facecolor=col, edgecolor="#fcfcfb", linewidth=0.4, label=name, zorder=3)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
ax.set_xlabel("Observed mean data-visible latency (ms)"); ax.set_ylabel("Predicted before the run (ms)")
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.17), handletextpad=0.3, fontsize=6)
fig.savefig(os.path.join(FIG, "scatter.pdf")); plt.close(fig)
print("scatter cells:", n_cells)


# ---------- Fig. 3: model vs naive baselines (testbed/baselines.py output, PILOT_REPORT §10.2) ----------
BASE = [  # test, model, B_mean, B_nocache  (mean relative error, %)
    ("v5 test", 1.10, 15.33, 21.57), ("v5 rep.", 0.77, 14.78, 19.28), ("SvelteKit test", 0.69, 10.18, 13.18),
    ("SvelteKit rep.", 0.33, 10.97, 14.55), ("v7 real", 0.61, 47.22, 43.45), ("v7 real rep.", 1.08, 47.54, 43.03),
    ("v8b real", 0.62, 47.88, 43.54), ("v8b real rep.", 0.70, 47.04, 43.42), ("v9 HTTP/2 real", 0.26, 47.45, 42.78),
    ("v9 HTTP/2 rep.", 0.23, 46.94, 43.52),
]
fig, ax = plt.subplots(figsize=(3.4, 2.9))
yy = range(len(BASE)); h = 0.26
for k, (lab, col) in enumerate([("Path model (prospective)", C1), ("Baseline: cache-agnostic RTT line", C2), ("Baseline: no-cache RTT line", C3)]):
    ax.barh([y + (k - 1) * (h + 0.02) for y in yy], [b[k + 1] for b in BASE], height=h, color=col, label=lab)
ax.set_yticks(list(yy)); ax.set_yticklabels([b[0] for b in BASE]); ax.invert_yaxis()
ax.set_xscale("log"); ax.set_xlabel("Mean relative error over cells (%, log scale)")
from matplotlib.ticker import FixedLocator, FixedFormatter
ax.xaxis.set_major_locator(FixedLocator([0.3, 1, 3, 10, 30])); ax.xaxis.set_major_formatter(FixedFormatter(["0.3", "1", "3", "10", "30"]))
ax.grid(axis="y", visible=False); ax.legend(loc="lower right", bbox_to_anchor=(1.0, -0.42), ncol=1)
fig.savefig(os.path.join(FIG, "baselines.pdf")); plt.close(fig)


# ---------- Fig. 4: staleness, predicted vs observed stale share per policy cell ----------
fig, ax = plt.subplots(figsize=(3.4, 3.0))
ax.fill_between([0, 0.75], [-0.05, 0.70], [0.05, 0.80], color=GRID, lw=0, zorder=0, label="±0.05 (criterion W2)")
ax.plot([0, 0.75], [0, 0.75], color=INK2, lw=0.7)
for name, col, mk, tags in [("Writes + invalidation, fast query (testW2, repW2)", C1, "o", ["testW2", "repW2"]),
                            ("Server-work regime, 25 / 100 ms DB work (testX, repX)", C2, "s", ["testX", "repX"])]:
    xs = [c["obs"] for t in tags for c in stale(t)]; ys = [c["pred"] for t in tags for c in stale(t)]
    ax.scatter(xs, ys, s=14, marker=mk, facecolor=col, edgecolor="#fcfcfb", linewidth=0.4, label=name, zorder=3)
ax.set_xlim(0, 0.75); ax.set_ylim(0, 0.75)
ax.set_xlabel("Observed share of views showing stale data"); ax.set_ylabel("Predicted before the run")
ax.legend(loc="upper left", handletextpad=0.3)
fig.savefig(os.path.join(FIG, "stale.pdf")); plt.close(fig)


# ---------- Fig. 5: latency vs staleness per policy, repX (100 ms DB work, RTT 200) ----------
# (label, x offset, y offset in points) chosen so no label overlaps another or a mark
OFF = {("csr", "off", "off"): ("CSR none", 6, -9), ("ssr", "off", "off"): ("SSR none", 6, 2),
       ("csr", "off", "ttl"): ("CSR Redis-TTL", -52, -11), ("ssr", "off", "ttl"): ("SSR Redis-TTL", 6, 3),
       ("csr", "ttl", "ttl"): ("CSR TanStack+Redis-TTL", 6, -3), ("csr", "ttl", "push"): ("CSR TanStack+Redis-push", 6, 4),
       ("ssr", "ttl", "ttl"): ("SSR Next-TTL+Redis-TTL", -40, 7), ("ssr", "ttl", "push"): ("SSR Next-TTL+Redis-push", -20, -11),
       ("ssr", "push", "push"): ("SSR Next-push+Redis-push", 6, 2)}
LABEL = {("csr", "off", "off"): "CSR, no caches", ("csr", "off", "ttl"): "CSR, Redis TTL", ("csr", "ttl", "ttl"): "CSR, TanStack + Redis TTL",
         ("csr", "ttl", "push"): "CSR, TanStack + Redis push", ("ssr", "off", "off"): "SSR, no caches", ("ssr", "off", "ttl"): "SSR, Redis TTL",
         ("ssr", "ttl", "ttl"): "SSR, Next TTL + Redis TTL", ("ssr", "ttl", "push"): "SSR, Next TTL + Redis push", ("ssr", "push", "push"): "SSR, Next push + Redis push"}
st = {(c["mode"], c["fe"], c["rd"]): c for c in stale("repX")}
la = {(c["mode"], c["fe"], c["rd"]): c for c in latx("repX") if c["action"] == "nav"}
fig, ax = plt.subplots(figsize=(3.4, 2.9))
for k, lab in LABEL.items():
    col = C1 if k[0] == "csr" else C2
    xo, yo, xp, yp = st[k]["obs"], la[k]["obs"], st[k]["pred"], la[k]["pred"]
    ax.plot([xp, xo], [yp, yo], color=INK2, lw=0.5, zorder=1)
    ax.scatter([xo], [yo], s=18, marker="o" if k[0] == "csr" else "s", facecolor=col, edgecolor="#fcfcfb", linewidth=0.4, zorder=3)
    ax.scatter([xp], [yp], s=18, marker="o" if k[0] == "csr" else "s", facecolor="none", edgecolor=col, linewidth=0.8, zorder=2)
    t, dx, dy = OFF[k]
    ax.annotate(t, (xo, yo), xytext=(dx, dy), textcoords="offset points", fontsize=5.5, color=INK2)
ax.scatter([], [], s=18, marker="o", facecolor=C1, label="CSR, observed"); ax.scatter([], [], s=18, marker="s", facecolor=C2, label="SSR, observed")
ax.scatter([], [], s=18, marker="o", facecolor="none", edgecolor=INK2, label="predicted before the run")
ax.set_xlabel("Share of views showing stale data"); ax.set_ylabel("Mean navigation latency (ms)")
ax.set_xlim(-0.02, 0.78); ax.set_ylim(120, 340); ax.legend(loc="lower right", bbox_to_anchor=(1.0, -0.42), ncol=2)
fig.savefig(os.path.join(FIG, "regime.pdf")); plt.close(fig)


# ---------- Fig. 6: concurrency, latency vs N per action class (P3, P4) ----------
fig, axs = plt.subplots(1, 4, figsize=(7.0, 1.9))
for ax, (mode, act) in zip(axs, [("csr", "initial"), ("csr", "nav"), ("ssr", "initial"), ("ssr", "nav")]):
    for tag, n, mk in [("concP4", 3, "s"), ("concP3", 4, "o"), ("repP4", 7, "s"), ("repP3", 8, "o")]:
        c = [x for x in cells(tag) if x["mode"] == mode and x["action"] == act][0]
        ax.scatter([n], [c["obs"]], s=16, marker=mk, facecolor=C1, edgecolor="#fcfcfb", linewidth=0.4, zorder=3)
        ax.scatter([n], [c["pred"]], s=16, marker=mk, facecolor="none", edgecolor=C2, linewidth=0.8, zorder=2)
    ax.set_title(f"{mode.upper()} {'initial load' if act == 'initial' else 'navigation'}", fontsize=7, color=INK)
    ax.set_xticks([3, 4, 7, 8]); ax.set_xlabel("Concurrent users N")
axs[0].set_ylabel("Mean latency (ms)")
axs[0].scatter([], [], s=16, marker="o", facecolor=C1, label="observed"); axs[0].scatter([], [], s=16, marker="o", facecolor="none", edgecolor=C2, label="predicted")
axs[0].scatter([], [], s=16, marker="o", facecolor=INK2, label="modelP3 (N = 4, 8)"); axs[0].scatter([], [], s=16, marker="s", facecolor=INK2, label="modelP4 (N = 3, 7)")
fig.legend(*axs[0].get_legend_handles_labels(), loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.12))
fig.tight_layout(); fig.savefig(os.path.join(FIG, "concurrency.pdf")); plt.close(fig)


# ---------- Table: every fresh prospective latency test ----------
ROWS = [  # tag, experiment, conditions
    ("prosp5", "Emulated (v5)", "netem, client 90/210 ms × internal 20/75 ms"),
    ("rep5", "Emulated (v5), replication", "netem, client 150/320 × internal 35/100 ms"),
    ("real7", "Real path (v7)", "relay + 40 ms"), ("rep7", "Real path (v7), replication", "relay + 20 ms"),
    ("real8b", "Real path, bandwidth input (v8b)", "relay + 10 ms, uncapped"), ("rep8b", "\\quad replication", "relay + 40 ms, 15 Mbit/s"),
    ("real9", "Real path, HTTPS + HTTP/2 (v9)", "relay + 35 ms"), ("rep9", "\\quad replication", "relay + 15 ms"),
    ("test9b", "HTTP/2, certificate trusted (v9b)", "netem 80/330 ms"), ("reptest9b", "\\quad replication", "netem 200/450 ms"),
    ("testS", "SvelteKit", "netem 90/300 ms"), ("repS", "\\quad replication", "netem 200/350 ms"),
    ("testQ", "Heavier page", "netem 90/300 ms"), ("repQ", "\\quad replication", "netem 200/350 ms"),
    ("testR2", "Slow device, 4× CPU", "netem 80/200 ms"), ("repR2", "\\quad replication, 2× CPU", "netem 60/180 ms"),
    ("concP3", "Concurrency (P3), N = 4", "netem 100 ms"), ("repP3", "\\quad replication, N = 8", "netem 100 ms"),
    ("concP4", "Concurrency (P4), N = 3", "netem 100 ms"), ("repP4", "\\quad replication, N = 7", "netem 100 ms"),
    ("realH3", "Home broadband (H3)", "real home path + 5 ms"), ("repH3", "\\quad replication", "real + 25 ms"),
]
lines = []
for tag, exp, cond in ROWS:
    mean, mx, crit, ok = summary(tag)
    fails = ", ".join(c for c in ("C1", "C2", "C3", "C4", "C5") if crit.get(c) == "FAIL") or "--"
    lines.append(f"{exp} & {cond} & {mean:.2f} & {mx:.2f} & {fails} & {'yes' if ok else 'no'} \\\\")
open(os.path.join(TAB, "tests.tex"), "w").write(
    "\\begin{tabularx}{\\textwidth}{>{\\raggedright\\arraybackslash}p{4.6cm} X r r l l}\n\\toprule\n"
    "Experiment & Conditions & Mean \\% & Max \\% & Fails & Passed \\\\\n\\midrule\n"
    + "\n".join(lines) + "\n\\bottomrule\n\\end{tabularx}\n")

# ---------- Table: staleness and regime tests ----------
def wline(tag, label):
    t = open(path(tag)).read()
    w1 = re.search(r"W1 pooled MAE <= 0.03: ([\d.]+)", t)[1]; w2 = re.search(r"W2 every cell within 0.05: max ([\d.]+)", t)[1]
    w3 = re.search(r"W3 orderings: (\d+/\d+)", t)[1]
    l1 = re.search(r"L1 mean latency error <= 3%: ([\d.]+)%", t); l2 = re.search(r"L2 every latency cell within max\(5%, 10 ms\): max ([\d.]+)%", t)
    return f"{label} & {w1} & {w2} & {w3} & {l1[1] + chr(92) + '%' if l1 else '--'} & {l2[1] + chr(92) + '%' if l2 else '--'} \\\\"
open(os.path.join(TAB, "stale.tex"), "w").write("\\begin{tabular}{lrrrrr}\n\\toprule\nTest & W1 MAE & W2 max & W3 & L1 & L2 max \\\\\n\\midrule\n" + "\n".join([
    wline("testW2", "Writes, fast query: test (RTT 150, $\\lambda$ 3/s)"), wline("repW2", "\\quad replication (RTT 60, $\\lambda$ 1.5/s)"),
    wline("testX", "Regime: test (RTT 100, $d$ 25 ms)"), wline("repX", "\\quad replication (RTT 200, $d$ 100 ms)")]) + "\n\\bottomrule\n\\end{tabular}\n")
print("wrote", sorted(os.listdir(FIG)), sorted(os.listdir(TAB)))
