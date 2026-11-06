# Runs record_snapshot.py at every 5-minute slot for up to --max-minutes, then exits so the next queued
# GitHub Actions run takes over. Slots use the same phase as the Windows task (hh:m3:02 UTC), so status.py
# assigns cloud and local snapshots to the same slots. Public read-only data only: no keys, no orders.
#
# Every attempt is logged to <data>/data/cloud_loop.csv with the slot it aimed for and when it really started,
# because GitHub's cron can start runs late or skip them. The snapshot files hold the real request times.
import os, sys, time, argparse, subprocess, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
STEP, PHASE = 300, 182          # 5 minutes; 3 min 02 s into each 5 minutes, like the Windows task
RUN_LIMIT = 200                 # the recorder's own watchdog fires at 170 s
UTC = dt.timezone.utc

def iso(t): return dt.datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds")
def next_slot(t): return t + (PHASE - t) % STEP

def sh(*cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def push(repo, msg):
    sh("git", "add", "-A", cwd=repo)
    if sh("git", "diff", "--cached", "--quiet", cwd=repo).returncode == 0: return "nothing"
    sh("git", "commit", "-q", "-m", msg, cwd=repo)
    for wait in (0, 2, 4, 8, 16):
        time.sleep(wait)
        r = sh("git", "push", "-q", "origin", "HEAD:stage2-data", cwd=repo)
        if r.returncode == 0: return "pushed"
        sh("git", "pull", "-q", "--rebase", "origin", "stage2-data", cwd=repo)
    return "push failed: " + r.stderr.strip()[-200:].replace(",", ";").replace("\n", " ")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="checkout of the stage2-data branch; snapshots go to <data>/data")
    ap.add_argument("--max-minutes", type=float, default=340)
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    repo = os.path.abspath(a.data); data = os.path.join(repo, "data"); os.makedirs(data, exist_ok=True)
    started = time.time(); deadline = started + a.max_minutes * 60
    end = dt.datetime.fromisoformat(open(os.path.join(HERE, "end_utc.txt")).read().strip()).timestamp()
    log = os.path.join(data, "cloud_loop.csv")
    run = os.environ.get("GITHUB_RUN_ID", "local"); ev = os.environ.get("GITHUB_EVENT_NAME", "manual")
    def note(*cols):
        with open(log, "a") as f: f.write(",".join(str(c).replace(",", ";") for c in cols) + "\n")  # the cron string has commas
    note("run_start", iso(started), run, ev, os.environ.get("BOB_CRON", ""), "", "")
    while True:
        target = next_slot(time.time() + 5)
        if target >= end or target + RUN_LIMIT > deadline: break
        time.sleep(max(0, target - time.time()))
        t0 = time.time()
        env = dict(os.environ, BOB_DATA_DIR=data, BOB_SOURCE="github-actions", BOB_SLOT_TARGET=iso(target))
        try:
            rc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "record_snapshot.py")], env=env, timeout=RUN_LIMIT).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        t1 = time.time()
        p = "skipped" if a.no_push else push(repo, f"stage2 cloud snapshot {iso(target)}")
        note("slot", iso(target), run, ev, f"{t0 - target:.1f}", f"{t1 - t0:.1f}", f"rc={rc} {p}")
    note("run_end", iso(time.time()), run, ev, "", "", "")
    if not a.no_push: push(repo, f"stage2 cloud run {run} ended")

if __name__ == "__main__":
    main()
