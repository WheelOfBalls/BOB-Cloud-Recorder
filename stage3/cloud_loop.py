#!/usr/bin/env python3
# Stage 3 recording loop for GitHub Actions. Separate from stage 2 (own workflow, concurrency group and branch).
#   * one snapshot (record_snapshot.py) per 5-minute slot at phase hh:m2:30 UTC, so the slots sit 57.5, 52.5, ... 2.5
#     minutes before each hourly close and cover the pre-registered 2-to-60-minute row window;
#   * a 1-minute poll of both Deribit indices on the minute (hh:mm:00), in its own thread so that a slow snapshot or
#     push never delays it. The poll at hh:00:00 is the index at the hourly close.
# Windows (all UTC, files next to this script):
#   pilot : now < pilot_until_utc.txt          -> branch stage3-pilot (thrown away, never enters a test)
#   wait  : pilot end <= now < live start - 5 h -> no data, no branch: the run sleeps and queues its successor, so the
#           run chain survives the 12 days between the pilot and the live window without relying on GitHub's cron
#   live  : start_utc.txt <= slot < end_utc.txt -> branch stage3-data  (runs may begin up to 5 h early and wait)
#   off   : otherwise (after the live window)   -> the workflow exits at once and queues nothing
# Every attempt is logged to <data>/cloud_loop.csv with its target and actual start. Nothing is filled in.
import os, sys, time, argparse, threading, subprocess, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_snapshot as rs  # noqa: E402

STEP, PHASE = 300, 150          # 5-minute slots at hh:m2:30
RUN_LIMIT = 200                 # the snapshot's own watchdog fires at 170 s
LEAD_S = 5 * 3600               # a live run may start this long before the first slot and wait (cron can be hours late)
UTC = dt.timezone.utc
BRANCH = {"pilot": "stage3-pilot", "live": "stage3-data"}


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds")


def read_ts(name, here=HERE):
    with open(os.path.join(here, name)) as f:
        return dt.datetime.fromisoformat(f.read().strip()).timestamp()


def windows(here=HERE):
    return {"pilot_until": read_ts("pilot_until_utc.txt", here), "start": read_ts("start_utc.txt", here),
            "end": read_ts("end_utc.txt", here)}


def mode_at(t, w):
    if t < w["pilot_until"] and w["pilot_until"] <= w["start"]:
        return "pilot"
    if w["start"] - LEAD_S <= t < w["end"]:
        return "live"
    if t < w["start"] - LEAD_S:
        return "wait"
    return "off"


def wait_until(t, w, max_minutes):
    """A wait run sleeps until a minute after the live lead begins, or until its own time limit."""
    return min(w["start"] - LEAD_S + 60, t + max_minutes * 60)


def slot_range(mode, w):
    """[first, last) slot times allowed in this mode."""
    if mode == "pilot":
        return 0.0, w["pilot_until"]
    if mode == "live":
        return w["start"], w["end"]
    return 0.0, 0.0


def next_slot(t):
    return t + (PHASE - t) % STEP


def sh(*cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def push(repo, branch, msg):
    sh("git", "add", "-A", cwd=repo)
    if sh("git", "diff", "--cached", "--quiet", cwd=repo).returncode == 0:
        return "nothing"
    sh("git", "commit", "-q", "-m", msg, cwd=repo)
    r = None
    for wait in (0, 2, 4, 8, 16):
        time.sleep(wait)
        r = sh("git", "push", "-q", "origin", f"HEAD:{branch}", cwd=repo)
        if r.returncode == 0:
            return "pushed"
        sh("git", "pull", "-q", "--rebase", "origin", branch, cwd=repo)
    return "push failed: " + r.stderr.strip()[-200:].replace(",", ";").replace("\n", " ")


class MinutePoller(threading.Thread):
    """Polls btc_usd and eth_usd at every whole minute until stop is set or `until` is reached.
    Rows: target_utc,coin,t0,t1,index_price,us_out,error  in <data>/index_1m/YYYY-MM-DD.csv (day of the target)."""
    def __init__(self, data, lo, until, fetch=None, clock=time.time, sleep=time.sleep):
        super().__init__(daemon=True)
        self.data, self.lo, self.until = data, lo, until
        self.fetch = fetch or (lambda url: rs.Fetcher().get(url, tries=1))
        self.clock, self.sleep = clock, sleep
        self.stop = threading.Event()
        os.makedirs(os.path.join(data, "index_1m"), exist_ok=True)

    def poll(self, target):
        rows = []
        for coin, _, _, name in rs.COINS:
            r = self.fetch(f"{rs.DB}/get_index_price?index_name={name}")
            body = r.get("body") or {}
            p = (body.get("result") or {}).get("index_price")
            err = "" if p is not None else "no index_price"
            rows.append(f"{iso(target)},{coin},{r['t0']:.3f},{r['t1']:.3f},{'' if p is None else p},{body.get('usOut', '')},{err}")
        fn = os.path.join(self.data, "index_1m", dt.datetime.fromtimestamp(target, UTC).strftime("%Y-%m-%d") + ".csv")
        new = not os.path.exists(fn)
        with open(fn, "a") as f:
            f.write(("target_utc,coin,t0,t1,index_price,us_out,error\n" if new else "") + "\n".join(rows) + "\n")

    def run(self):
        while not self.stop.is_set():
            now = self.clock()
            target = now - now % 60 + 60
            if target >= self.until:
                return
            self.sleep(max(0.0, target - self.clock()))
            if self.stop.is_set():
                return
            if target >= self.lo:
                try:
                    self.poll(target)
                except Exception as e:  # never let the hedge poll kill the loop; the minute is simply missing
                    with open(os.path.join(self.data, "crash_log.txt"), "a") as f:
                        f.write(f"{iso(time.time())} minute poll {type(e).__name__}: {e}\n")


def series_meta(data, fetch=None):
    """Fee fields of the two series, once per run (the pre-registration re-checks the fee before the start)."""
    fetch = fetch or (lambda url: rs.Fetcher().get(url, tries=1))
    fn = os.path.join(data, "series_meta.csv")
    new = not os.path.exists(fn)
    with open(fn, "a") as f:
        if new:
            f.write("utc,series,frequency,fee_type,fee_multiplier\n")
        for _, series, _, _ in rs.COINS:
            s = ((fetch(f"{rs.K}/series/{series}").get("body") or {}).get("series")) or {}
            f.write(f"{iso(time.time())},{series},{s.get('frequency', '')},{s.get('fee_type', '')},{s.get('fee_multiplier', '')}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", action="store_true", help="print the current mode and its branch, then exit")
    ap.add_argument("--data", help="checkout of the data branch; files go to <data>/data")
    ap.add_argument("--mode", choices=["pilot", "live", "test", "wait"],
                    help="test: a short run with no window and no push; wait: sleep (no data) so the next run can be queued")
    ap.add_argument("--max-minutes", type=float, default=340)
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    w = windows()
    if a.which:
        m = mode_at(time.time(), w)
        print(m, BRANCH.get(m, ""))
        return 0
    if a.mode == "wait":
        until = wait_until(time.time(), w, a.max_minutes)
        print(f"waiting until {iso(until)} (live lead starts {iso(w['start'] - LEAD_S)})", flush=True)
        time.sleep(max(0.0, until - time.time()))
        return 0
    repo = os.path.abspath(a.data)
    data = os.path.join(repo, "data")
    os.makedirs(data, exist_ok=True)
    started = time.time()
    deadline = started + a.max_minutes * 60
    lo, hi = (0.0, float("inf")) if a.mode == "test" else slot_range(a.mode, w)
    hi = min(hi, deadline)
    nopush = a.no_push or a.mode == "test"
    branch = BRANCH.get(a.mode, "")
    log = os.path.join(data, "cloud_loop.csv")
    run = os.environ.get("GITHUB_RUN_ID", "local")
    ev = os.environ.get("GITHUB_EVENT_NAME", "manual")

    def note(*cols):
        new = not os.path.exists(log)
        with open(log, "a") as f:
            if new:
                f.write("kind,utc,run_id,event,late_s_or_cron,duration_s,status\n")
            f.write(",".join(str(c).replace(",", ";") for c in cols) + "\n")

    note("run_start", iso(started), run, ev, os.environ.get("BOB_CRON", ""), "", a.mode)
    try:
        series_meta(data)
    except Exception as e:
        note("series_meta", iso(time.time()), run, ev, "", "", f"failed {type(e).__name__}")
    if a.mode == "test":                    # one snapshot now and about two minutes of index polls, nothing pushed
        poller = MinutePoller(data, 0.0, started + 150)
        poller.start()
        env = dict(os.environ, BOB_DATA_DIR=data, BOB_SOURCE="github-actions-check", BOB_SLOT_TARGET=iso(started), BOB_MODE="test")
        rc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "record_snapshot.py")], env=env, timeout=RUN_LIMIT).returncode
        note("slot", iso(started), run, ev, "0.0", f"{time.time() - started:.1f}", f"rc={rc} skipped")
        poller.join(timeout=200)
        note("run_end", iso(time.time()), run, ev, "", "", a.mode)
        return rc
    poller = MinutePoller(data, lo, hi)
    poller.start()
    while True:
        target = next_slot(time.time() + 5)
        if target < lo:
            target = next_slot(lo)
        if target >= hi or target + RUN_LIMIT > deadline:
            break
        time.sleep(max(0, target - time.time()))
        t0 = time.time()
        env = dict(os.environ, BOB_DATA_DIR=data, BOB_SOURCE="github-actions", BOB_SLOT_TARGET=iso(target), BOB_MODE=a.mode)
        try:
            rc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "record_snapshot.py")], env=env, timeout=RUN_LIMIT).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        t1 = time.time()
        p = "skipped" if nopush else push(repo, branch, f"stage3 {a.mode} snapshot {iso(target)}")
        note("slot", iso(target), run, ev, f"{t0 - target:.1f}", f"{t1 - t0:.1f}", f"rc={rc} {p}")
    # keep the minute poll going to the run's end (or the window's), so the last hourly close of the run is covered
    while time.time() < min(hi, deadline - 60) and poller.is_alive():
        time.sleep(5)
    poller.stop.set()
    poller.join(timeout=70)
    note("run_end", iso(time.time()), run, ev, "", "", a.mode)
    if not nopush:
        push(repo, branch, f"stage3 {a.mode} run {run} ended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
