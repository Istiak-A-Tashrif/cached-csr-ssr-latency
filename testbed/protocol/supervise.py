#!/usr/bin/env python3
"""Keep protocol/run_catalogue.sh going independently of the session that started it (TWEB revision).
Daemonizes, waits for the given runner pid, and if the runner ends before printing "== done", removes
the records of the interrupted run (browser records, write-log lines, its prediction), logs the discard
in results/discarded-runs.jsonl, and restarts the runner, which skips completed runs. The interrupted
run is then repeated from configuration with a fresh prediction (the logged-single-retry rule).
usage: python3 protocol/supervise.py <runner pid>"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(HERE, "results")
BLOCKS = ["revPilotT", "revT", "revPilotR", "revR", "revB2T", "revB2R"]
pid = int(sys.argv[1])
if os.fork(): sys.exit(0)
os.setsid()
if os.fork(): sys.exit(0)
log = open(os.path.join(R, "supervise.log"), "a", buffering=1)


def alive(p):
    try: os.kill(p, 0); return True
    except OSError: return False


def clean():
    for b in BLOCKS:
        rf, vf = os.path.join(R, f"{b}-runs.jsonl"), os.path.join(R, f"{b}.jsonl")
        if not os.path.exists(vf): continue
        done = {json.loads(l)["runId"] for l in open(rf)} if os.path.exists(rf) else set()
        lines = open(vf).read().splitlines()
        bad = {json.loads(l).get("runId") for l in lines if l.strip()} - done
        if not bad: continue
        open(vf, "w").write("".join(l + "\n" for l in lines if json.loads(l).get("runId") not in bad))
        for f in ("writes.jsonl", "predictionsR.jsonl"):
            p = os.path.join(R, f)
            ls = open(p).read().splitlines()
            open(p, "w").write("".join(l + "\n" for l in ls if json.loads(l).get("runId") not in bad))
        with open(os.path.join(R, "discarded-runs.jsonl"), "a") as d:
            for rid in sorted(bad):
                d.write(json.dumps({"runId": rid, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "why": "runner interrupted (session ended); records removed, run repeated"}) + "\n")
        log.write(f"{time.ctime()} cleaned interrupted runs {sorted(bad)}\n")


while True:
    while alive(pid): time.sleep(20)
    txt = open(os.path.join(R, "run_catalogue.log")).read()
    if "== done" in txt:
        log.write(f"{time.ctime()} runner finished\n"); break
    log.write(f"{time.ctime()} runner {pid} ended early; restarting\n")
    subprocess.run(["docker", "exec", "cachebed-api-1", "node", "-e",
                    'fetch("http://localhost:5001/__admin/writes",{method:"POST",headers:{"content-type":"application/json"},body:"{}"})'], cwd=HERE)
    time.sleep(5)
    clean()
    p = subprocess.Popen(["sh", "protocol/run_catalogue.sh"], cwd=HERE, stdout=open(os.path.join(R, "run_catalogue.log"), "a"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    pid = p.pid
    log.write(f"{time.ctime()} restarted runner pid {pid}\n")
