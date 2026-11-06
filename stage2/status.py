# Coverage report for the stage 2 recording. Never writes to data/ or touches the recorder.
# It keeps a small cache of per-snapshot metrics (status_cache.json, next to this file) so it stays fast as files pile up.
# Validity and coverage follow PREREGISTRATION.md: a snapshot is valid if Deribit and Kalshi KXBTCD top-of-book
# requests finished within 5 s of each other and the Deribit index moved under 0.10% across the Kalshi pull.
# An event qualifies if at least 80% of its possible 5-minute slots (the 30 hours before its 5pm close) are valid.
#
# Sources (deviation 4 in PREREGISTRATION.md). With no --cloud, this reports the local data/ folder only, as before.
# With --cloud DIR (a checkout of the stage2-data branch, or its data/ folder) or --fetch-cloud, it reports the merged
# series: per slot, the local snapshot if it is valid, otherwise the first valid cloud snapshot in that slot. The merged
# series is what the 80% rule uses. Local-only and cloud-only coverage are printed next to it for reference only.
#
#   python -I status.py                         local only (unchanged)
#   python -I status.py --fetch-cloud           clone or update the stage2-data branch into cloud_data/, then merge
#   python -I status.py --cloud ../stage2-data  merge with an existing checkout
#   --source local|cloud|merged                 which series the detailed sections describe (default: merged if a cloud dir is given)
#   --data DIR                                  local data folder (default: data/ next to this file)
#   --now ISO                                   pretend it is this time (for testing)
import os, sys, csv, json, gzip, glob, hashlib, argparse, statistics, subprocess, datetime as dt, collections
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_V = 1
STEP = 300; WINDOW_H = 30; NEED_FRAC = 0.80; NEED_EVENTS = 10
GAP_LIMIT = 72  # slots (6 h). One outage longer than this inside an event's 30 h window uses up more than its whole 20% allowance.
CLOUD_REPO = "https://github.com/WheelOfBalls/BOB-Cloud-Recorder.git"; CLOUD_BRANCH = "stage2-data"
UTC = dt.timezone.utc
def ts(x): return dt.datetime.fromtimestamp(x, UTC)
def fmt(x): return ts(x).strftime("%m-%d %H:%M")
def lines(p):
    with open(p) as fh: return fh.readlines()

# ---------- per-snapshot metrics, read from the snapshot files themselves ----------
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0
def snapshot_metrics(path):
    try:
        with gzip.open(path, "rt") as fh: s = json.load(fh)
    except Exception as ex: return {"unreadable": f"{type(ex).__name__}: {ex}"[:120]}
    t = dt.datetime.fromisoformat(s["utc"]).timestamp()
    ch, kd, kb = s.get("deribit") or {}, s.get("kxbtcd") or {}, s.get("kxbtc") or {}
    opts, md = ch.get("options") or [], kd.get("markets") or []
    def idx(k):
        b = (s.get(k) or {}).get("body") or {}
        return ((b.get("result") or {}).get("index_price"))
    i0, i1 = idx("index_before"), idx("index_after")
    move = abs(i1 - i0) / i0 * 100 if i0 and i1 else None
    gap = abs(kd["t1"] - ch["t1"]) if opts and md else None
    created = [o.get("creation_timestamp") for o in opts if o.get("creation_timestamp")]
    der_age = ch["t1"] - max(created) / 1000 if created else None          # how old Deribit's own data was when it arrived
    eff_lag = kd["t1"] - max(created) / 1000 if created and md else None  # Kalshi quote time minus Deribit data time
    five = [m for m in md if (m.get("event_ticker") or "").endswith("17")]
    want_books = [m["ticker"] for m in five if 0.03 <= f(m.get("yes_bid_dollars")) and 0 < f(m.get("yes_ask_dollars")) <= 0.97]
    books = s.get("books") or {}
    events = {}
    for m in five:
        ev = events.setdefault(m["event_ticker"], [dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp(), 0, 0])
        b, a = f(m.get("yes_bid_dollars")), f(m.get("yes_ask_dollars"))
        ev[1] += 1
        if b > 0 and a > 0 and 0.06 <= (a + b) / 2 <= 0.94: ev[2] += 1  # candidate rows (the 30 h limit is applied later)
    h = lambda xs: hashlib.md5(json.dumps(xs, separators=(",", ":")).encode()).hexdigest()[:12]
    valid = bool(opts) and bool(md) and gap is not None and gap <= 5 and move is not None and move < 0.10
    why = [w for w, bad in (("no Deribit chain", not opts), ("no KXBTCD", not md), ("Deribit-Kalshi >5s", gap is not None and gap > 5),
                            ("index missing", move is None), ("index moved >=0.10%", move is not None and move >= 0.10)) if bad]
    return {"t": t, "valid": valid, "why": why, "gap": gap, "move": move, "der_age": der_age, "eff_lag": eff_lag, "idx": i0,
            "kd_pull": kd["t1"] - kd["t0"] if md else None, "n_opt": len(opts), "n_kd": len(md), "n_kb": len(kb.get("markets") or []),
            "books_want": len(want_books), "books_got": sum(1 for x in want_books if x in books), "errors": s.get("errors") or [],
            "kd_hash": h([[m["ticker"], m.get("yes_bid_dollars"), m.get("yes_ask_dollars"), m.get("volume_fp")] for m in md]) if md else None,
            "der_hash": h([[o["instrument_name"], o.get("bid_price"), o.get("ask_price"), o.get("mark_price")] for o in opts]) if opts else None,
            "kd_vol": sum(f(m.get("volume_fp")) for m in five), "events": events}

# ---------- one recorder's folder ----------
def run_log_summary(D, now, END):
    """The original summary, from run_log.csv. Returns False if there is no run log yet."""
    log = os.path.join(D, "run_log.csv")
    R = [r for r in csv.reader(lines(log)) if r] if os.path.exists(log) else []
    if not R: return False
    rts = [dt.datetime.fromisoformat(r[0]) for r in R]
    span = max(now - rts[0].timestamp(), 1)
    ok = [r for r in R if int(r[7]) == 0 and int(r[1]) > 0 and int(r[2]) > 0 and float(r[5]) <= 5]
    print(f"snapshots {len(R)} of about {int(span // 300) + 1} expected; clean {len(ok)}; first {rts[0]:%Y-%m-%d %H:%M}Z; last {rts[-1]:%Y-%m-%d %H:%M}Z ({(now - rts[-1].timestamp()) / 60:.0f} min ago)")
    if END: print("ends", ts(END).isoformat())
    print("mean per snapshot: options %.0f, KXBTCD %.0f, KXBTC %.0f, books %.0f; mean run %.1fs; max Deribit-Kalshi gap %.2fs" % tuple([sum(float(r[i]) for r in R) / len(R) for i in (1, 2, 3, 4, 6)] + [max(float(r[5]) for r in R)]))
    e = collections.Counter(x.split(":")[0] + ":" + x.split(":", 1)[-1][:60] for r in R if r[8] for x in r[8].split(" | "))
    for k, v in e.most_common(5): print("error", v, k)
    print("disk MB %.1f" % (sum(os.path.getsize(os.path.join(p, fn)) for p, _, fs in os.walk(D) for fn in fs) / 1e6))
    return True

def load_source(name, D, cache_path):
    """Snapshot metrics (cached), plus the trace, crash and hang logs, for one recorder's data folder."""
    cache = {}
    try:
        with open(cache_path) as fh: c = json.load(fh)
        if c.get("v") == CACHE_V: cache = c["snaps"]
    except Exception: pass
    for p in sorted(glob.glob(os.path.join(D, "*", "*.json.gz"))):
        k = os.path.relpath(p, D).replace("\\", "/")
        if k not in cache or cache[k].get("size") != os.path.getsize(p):
            cache[k] = snapshot_metrics(p); cache[k]["size"] = os.path.getsize(p)
    cache = {k: v for k, v in cache.items() if os.path.exists(os.path.join(D, k))}
    try:
        with open(cache_path, "w") as fh: json.dump({"v": CACHE_V, "snaps": cache}, fh)
    except Exception as ex: print("note: could not write cache:", ex)
    S = sorted((dict(v, src=name) for v in cache.values() if "t" in v), key=lambda v: v["t"])
    runs = collections.OrderedDict()  # runs that started, from trace.log, to find the ones that never wrote a snapshot
    tp = os.path.join(D, "trace.log")
    if os.path.exists(tp):
        for line in lines(tp):
            parts = line.split(None, 3)
            if len(parts) < 4: continue
            try: t = dt.datetime.fromisoformat(parts[0]).timestamp()
            except ValueError: continue
            r = runs.setdefault(parts[2], {"t": t, "steps": []}); r["steps"].append(parts[3].strip())
    crash_t = []
    cp = os.path.join(D, "crash_log.txt")
    if os.path.exists(cp):
        for line in lines(cp):
            try: crash_t.append(dt.datetime.fromisoformat(line.split()[0]).timestamp())
            except (ValueError, IndexError): pass
    hp = os.path.join(D, "hang_log.txt")
    hangs = sum(line.startswith("Timeout") for line in lines(hp)) if os.path.exists(hp) else 0
    return {"name": name, "D": D, "S": S, "bad_files": sorted(k for k, v in cache.items() if "unreadable" in v),
            "runs": runs, "crash_t": crash_t, "hangs": hangs}

# ---------- the 5-minute grid ----------
# Each recorder fires at a fixed phase within each 5 minutes (about hh:m3:02). Each snapshot is assigned to the nearest slot.
# The phase comes from the local snapshots when there are any (the cloud recorder copies the local phase), so the local-only
# report is exactly what it was before the cloud recorder existed.
class Grid:
    def __init__(self, snaps, now, END):
        self.phase = statistics.median(v["t"] % STEP for v in snaps)
        self.now, self.END = now, END
        self.last_done = int((min(now, END or now) - 240 - self.phase) // STEP)  # last slot whose run should have finished
    def slot(self, t): return int((t - self.phase + STEP / 2) // STEP)
    def slot_t(self, i): return i * STEP + self.phase

def source_series(src, g):
    """One recorder on its own, as status.py always counted it: the first snapshot in a slot counts, later ones are duplicates."""
    by_slot = collections.defaultdict(list)
    for v in src["S"]: by_slot[g.slot(v["t"])].append(v)
    pick = {i: vs[0] for i, vs in by_slot.items()}
    died = {g.slot(r["t"]): r["steps"][-1] for r in src["runs"].values() if "written" not in r["steps"] and g.now - r["t"] > 240}
    crash_slots = {g.slot(t) for t in src["crash_t"]}
    def status(i):
        if i in pick: return "valid" if pick[i]["valid"] else "invalid"
        if i in died or i in crash_slots: return "died"
        return "none"
    first = g.slot(src["S"][0]["t"])
    slots = range(first, g.last_done + 1)
    n_dupes = sum(len(vs) - 1 for vs in by_slot.values() if len(vs) > 1)
    diag = [f"duplicate snapshots in one slot: {n_dupes} (only the first counts)" + (f"; unreadable files: {', '.join(src['bad_files'])}" if src["bad_files"] else ""),
            f"watchdog hang dumps {src['hangs']}; crash log lines {len(src['crash_t'])}; trace runs that never wrote: {len(died)}" +
            (" (" + ", ".join(f"{fmt(g.slot_t(i))} after '{s}'" for i, s in sorted(died.items())[-5:]) + ")" if died else "")]
    return {"name": src["name"], "first": first, "slots": slots, "pick": pick, "by_slot": by_slot, "died": died, "crash_slots": crash_slots,
            "st": {i: status(i) for i in slots}, "moves_from": src["S"], "diag": diag, "from": collections.Counter(), "first_t": src["S"][0]["t"]}

def merged_series(L, C, g):
    """Deviation 4: per slot, the local snapshot if it is valid, otherwise the first valid cloud snapshot in that slot.
    "The local snapshot" is the one the local-only report counts (the first local snapshot in the slot)."""
    first = min(L["first"], C["first"]); slots = range(first, g.last_done + 1)
    pick, st, frm = {}, {}, collections.Counter()
    for i in slots:
        loc = L["pick"].get(i); cl = C["by_slot"].get(i, [])
        cv = next((v for v in cl if v["valid"]), None)
        if loc and loc["valid"]: pick[i], st[i] = loc, "valid"; frm["local"] += 1
        elif cv: pick[i], st[i] = cv, "valid"; frm["cloud"] += 1
        elif loc or cl: pick[i], st[i] = loc or cl[0], "invalid"
        elif i in L["died"] or i in L["crash_slots"] or i in C["died"] or i in C["crash_slots"]: st[i] = "died"
        else: st[i] = "none"
    filled = sum(1 for i in slots if st[i] == "valid" and pick[i]["src"] == "cloud")
    l_missing = sum(1 for i in slots if pick.get(i) and pick[i]["src"] == "cloud" and i not in L["pick"])
    diag = [f"valid slots taken from local {frm['local']}, from cloud {frm['cloud']} (cloud filled {l_missing} slots with no local snapshot "
            f"and {filled - l_missing} where the local one was invalid); slots where both sources have a snapshot "
            f"{sum(1 for i in slots if i in L['pick'] and C['by_slot'].get(i))}"]
    for s in (L, C): diag += [f"{s['name']}: {x}" for x in s["diag"]]
    return {"name": "merged", "first": first, "slots": slots, "pick": pick, "st": st, "diag": diag, "from": frm, "first_t": min(L["first_t"], C["first_t"]),
            "moves_from": sorted((pick[i] for i in slots if i in pick), key=lambda v: v["t"])}

# ---------- shared pieces ----------
def outage_windows(R):
    wins, cur = [], None
    for i in R["slots"]:
        if R["st"][i] != "valid":
            cur = cur or {"a": i, "b": i, "kinds": collections.Counter()}; cur["b"] = i; cur["kinds"][R["st"][i]] += 1
        elif cur: wins.append(cur); cur = None
    if cur: wins.append(cur)
    return wins

def event_list(sources, g):
    ev = {}
    for src in sources:
        for v in src["S"]:
            for name, (close, n, rows) in v["events"].items(): ev[name] = close
    if g.END:  # events the recording can still reach, assuming one 5pm event per day as seen so far
        closes = sorted(ev.values()); c = closes[-1] if closes else None
        while c and c + 86400 - WINDOW_H * 3600 < g.END: c += 86400; ev.setdefault(ts(c).strftime("KXBTCD-%y%b%d17").upper() + " (expected)", c)
    return ev

def event_table(R, g, ev):
    need = int(NEED_FRAC * WINDOW_H * 12 + 0.999)
    out = []
    for name, close in sorted(ev.items(), key=lambda x: x[1]):
        ws = [i for i in range(g.slot(close - WINDOW_H * 3600), g.slot(close) + 1) if close - WINDOW_H * 3600 <= g.slot_t(i) < close]
        good = sum(1 for i in ws if R["st"].get(i) == "valid" and name.split()[0] in R["pick"][i]["events"])
        future = sum(1 for i in ws if g.slot_t(i) > max(g.now, g.slot_t(g.last_done)) and (g.END is None or g.slot_t(i) < g.END))
        rec_slots = [i for i in ws if R["first"] <= i <= g.last_done]
        best = good + future; settled = close <= g.now
        tag = "QUALIFIES" if settled and good >= need else ("FAILED" if settled or best < need else f"open, can still miss {best - need} slots ({(best - need) * 5 / 60:.1f} h)")
        out.append({"name": name, "close": close, "ws": len(ws), "good": good, "future": future, "rec": len(rec_slots), "need": need,
                    "can": best >= need, "qualifies": settled and good >= need, "tag": tag})
    return out

# ---------- the detailed report on one series ----------
def report(R, g, ev):
    slots, st, pick, first, last_done, slot_t = R["slots"], R["st"], R["pick"], R["first"], g.last_done, g.slot_t
    cnt = collections.Counter(st.values())
    print(f"\n== Slots (5 min, phase :{int(g.phase // 60) % 5}m{int(g.phase % 60):02d}s) from {fmt(slot_t(first))}Z to {fmt(slot_t(last_done))}Z: {len(slots)}")
    print(f"valid {cnt['valid']} ({cnt['valid'] / len(slots):.0%}); invalid snapshot {cnt['invalid']}; run started but died {cnt['died']}; no run at all {cnt['none']}")
    for line in R["diag"]: print(line)
    why = collections.Counter(w for i in slots if st[i] == "invalid" for w in pick[i]["why"])
    if why: print("invalid because:", "; ".join(f"{k} x{v}" for k, v in why.most_common()))

    print("\n== Outage windows (consecutive slots without a valid snapshot)")
    wins = outage_windows(R)
    def nearest_valid(i, d):
        j = i + d
        while first <= j <= last_done:
            if st.get(j) == "valid": return pick[j]
            j += d
    M = R["moves_from"]
    moves_all = [abs(b["idx"] / a["idx"] - 1) * 100 for a, b in zip(M, M[1:]) if a["idx"] and b["idx"] and b["t"] - a["t"] < 400]
    typ = statistics.median(moves_all) if moves_all else None
    for w in wins[-15:]:
        n = w["b"] - w["a"] + 1; a, b = nearest_valid(w["a"], -1), nearest_valid(w["b"], 1)
        mv = f"BTC {(b['idx'] / a['idx'] - 1) * 100:+.2f}% across it" if a and b and a["idx"] and b["idx"] else "BTC move unknown (edge of record)"
        print(f"  {fmt(slot_t(w['a']))}Z to {fmt(slot_t(w['b']) + STEP)}Z  {n} slots ({n * 5 / 60:.1f} h)  " +
              ", ".join(f"{k} {v}" for k, v in w["kinds"].items()) + f"  {mv}" + ("  OVER 6 H" if n > GAP_LIMIT else ""))
    if len(wins) > 15: print(f"  ... {len(wins) - 15} earlier windows not shown")
    if not wins: print("  none")
    if typ is not None: print(f"  typical |BTC move| per 5 min while recording: {typ:.3f}%  (a gap's move is roughly comparable to this x sqrt(slots))")

    P = [pick[i] for i in slots if i in pick]
    print("\n== Pull quality (one snapshot per slot)")
    part = [v for v in P if v["books_got"] < v["books_want"]]
    print(f"order books: {sum(v['books_got'] for v in P)} of {sum(v['books_want'] for v in P)} wanted; snapshots missing some books {len(part)}")
    print(f"snapshots with request errors {sum(1 for v in P if v['errors'])}; KXBTC (brackets) missing {sum(1 for v in P if v['n_kb'] == 0)}")
    same_kd = sum(1 for a, b in zip(P, P[1:]) if a["kd_hash"] and a["kd_hash"] == b["kd_hash"])
    same_der = sum(1 for a, b in zip(P, P[1:]) if a["der_hash"] and a["der_hash"] == b["der_hash"])
    flat_vol = sum(1 for a, b in zip(P, P[1:]) if a["kd_vol"] and a["kd_vol"] == b["kd_vol"])
    print(f"identical to previous snapshot: KXBTCD list {same_kd}, Deribit chain {same_der}; 5pm volume unchanged {flat_vol} (possible stale Kalshi data)")
    def q(xs, p): xs = sorted(x for x in xs if x is not None); return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")
    for name, k in (("Deribit-Kalshi finish gap s", "gap"), ("Deribit data age on arrival s", "der_age"), ("Kalshi quote time minus Deribit data time s", "eff_lag"),
                    ("index move across Kalshi pull %", "move"), ("KXBTCD pull duration s", "kd_pull")):
        print(f"  {name}: median {q([v[k] for v in P], .5):.3f}, p95 {q([v[k] for v in P], .95):.3f}, max {q([v[k] for v in P], 1):.3f}")
    print(f"  near the limits: finish gap >3s {sum(1 for v in P if (v['gap'] or 0) > 3)}, index move >0.07% {sum(1 for v in P if (v['move'] or 0) > 0.07)}, Deribit data >10s old {sum(1 for v in P if (v['der_age'] or 0) > 10)}")

    print("\n== Coverage by UTC hour (valid / slots so far). Gaps tied to the hour bias rows toward some hours to close.")
    hv, hn = collections.Counter(), collections.Counter()
    for i in slots:
        h = ts(slot_t(i)).hour; hn[h] += 1; hv[h] += st[i] == "valid"
    print("  " + "  ".join(f"{h:02d}h {hv[h] / hn[h]:.0%}" for h in range(24) if hn[h]))
    print("  hours to the 22:00Z close for each UTC hour: 16-21Z is 0-6 h (and 24-30 h for the next day), 22-03Z 18-24 h, 04-09Z 12-18 h, 10-15Z 6-12 h")

    print(f"\n== 5pm events: need {NEED_EVENTS} settled events with >= {NEED_FRAC:.0%} of the {WINDOW_H * 12} slots in the {WINDOW_H} h before close valid")
    E = event_table(R, g, ev)
    for e in E:
        len_s = f"{e['good'] / e['rec']:.0%}" if e["rec"] else "-"
        print(f"  {e['name']:32s} close {fmt(e['close'])}Z  valid {e['good']}/{e['ws']}  future {e['future']}  {e['tag']}  [share of recorded slots {len_s}]")
    can, done_ok = sum(e["can"] for e in E), sum(e["qualifies"] for e in E)
    print(f"settled and qualifying {done_ok}; best case if every remaining slot is valid {can}; needed {NEED_EVENTS}; spare events {can - NEED_EVENTS}")
    print("  verdict now:", "a pass/fail is still possible" if can >= NEED_EVENTS else "INCOMPLETE is now certain: too few events can reach 80%")
    print("  note: the verdict uses the full 30 h window (deviation 3 in PREREGISTRATION.md); [share of recorded slots] is shown for reference only.")
    return E

# ---------- local, cloud and merged side by side ----------
def compare(series, g, ev, main_name):
    print("\n== Sources compared (deviation 4: per slot, the local snapshot if valid, else the first valid cloud snapshot)")
    print(f"  the merged series is what the 80% rule uses; local-only and cloud-only lines are for reference and never choose between sources")
    W = {s["name"]: outage_windows(s) for s in series}
    E = {s["name"]: event_table(s, g, ev) for s in series}
    for s in series:
        n = len(s["slots"]); v = sum(1 for i in s["slots"] if s["st"][i] == "valid")
        longest = max((w["b"] - w["a"] + 1 for w in W[s["name"]]), default=0)
        over = [w for w in W[s["name"]] if w["b"] - w["a"] + 1 > GAP_LIMIT]
        print(f"  {s['name']:7s} first snapshot {fmt(s['first_t'])}Z  valid {v}/{n} slots ({v / n:.0%})  longest gap {longest * 5 / 60:.1f} h  "
              f"gaps over 6 h {len(over)}  events: qualifying {sum(e['qualifies'] for e in E[s['name']])}, can still reach 80% {sum(e['can'] for e in E[s['name']])}")
        for w in over:
            k = w["b"] - w["a"] + 1
            print(f"           gap over 6 h: {fmt(g.slot_t(w['a']))}Z to {fmt(g.slot_t(w['b']) + STEP)}Z  {k} slots ({k * 5 / 60:.1f} h)")
    print("  valid slots in each event's 30 h window (need %d of 360):" % E[series[0]["name"]][0]["need"] if E[series[0]["name"]] else "  no events seen yet")
    names = [s["name"] for s in series]
    print("  " + f"{'event':32s}" + "".join(f"{n:>9s}" for n in names) + f"   {main_name} verdict")
    for rows in zip(*(E[n] for n in names)):
        if not any(r["good"] for r in rows) and rows[0]["future"] == rows[0]["ws"]: continue  # not started yet in any source
        print("  " + f"{rows[0]['name']:32s}" + "".join(f"{r['good']:9d}" for r in rows) + f"   {rows[names.index(main_name)]['tag']}")

# ---------- cloud data ----------
def fetch_cloud(dest):
    """Clone the stage2-data branch into dest, or bring an existing clone up to date. Read-only: never pushes."""
    def git(*a, cwd=None):
        r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
        if r.returncode: raise SystemExit(f"git {' '.join(a)} failed: {r.stderr.strip()[-300:]}")
    if os.path.isdir(os.path.join(dest, ".git")):
        git("fetch", "-q", "--depth", "1", "origin", CLOUD_BRANCH, cwd=dest); git("reset", "-q", "--hard", "FETCH_HEAD", cwd=dest)
    else:
        git("clone", "-q", "--depth", "1", "--single-branch", "--branch", CLOUD_BRANCH, CLOUD_REPO, dest)

def cloud_data_dir(p):
    """Accept a stage2-data checkout or its data/ folder."""
    return os.path.join(p, "data") if os.path.isdir(os.path.join(p, "data")) and not glob.glob(os.path.join(p, "*", "*.json.gz")) else p

def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 2 coverage report (read-only).")
    ap.add_argument("--now", help="pretend it is this ISO time (for testing)")
    ap.add_argument("--data", default=os.path.join(HERE, "data"), help="local data folder (default: data/ next to this file)")
    ap.add_argument("--cloud", help="stage2-data checkout, or its data/ folder; turns on the merged series")
    ap.add_argument("--fetch-cloud", nargs="?", const=os.path.join(HERE, "cloud_data"), metavar="DIR",
                    help="clone or update the stage2-data branch into DIR (default cloud_data/ next to this file) and use it")
    ap.add_argument("--source", choices=("local", "cloud", "merged"), help="series for the detailed sections (default: merged when cloud data is given)")
    ap.add_argument("--cache-dir", default=HERE, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    now = dt.datetime.fromisoformat(a.now).timestamp() if a.now else dt.datetime.now(UTC).timestamp()
    ef = os.path.join(HERE, "end_utc.txt")
    END = dt.datetime.fromisoformat("".join(lines(ef)).strip()).timestamp() if os.path.exists(ef) else None
    if a.fetch_cloud: fetch_cloud(a.fetch_cloud); a.cloud = a.cloud or a.fetch_cloud
    if not a.cloud:  # local only, exactly as before
        if a.source not in (None, "local"): raise SystemExit("--source cloud/merged needs --cloud DIR or --fetch-cloud")
        if not run_log_summary(a.data, now, END): raise SystemExit("no snapshots yet")
        L = load_source("local", a.data, os.path.join(a.cache_dir, "status_cache.json"))
        if not L["S"]: raise SystemExit("no readable snapshots")
        g = Grid(L["S"], now, END)
        report(source_series(L, g), g, event_list([L], g))
        return
    CD = cloud_data_dir(a.cloud)
    print("=== local recorder:", a.data)
    if not run_log_summary(a.data, now, END): print("no local run log")
    print("\n=== cloud recorder:", CD)
    if not run_log_summary(CD, now, END): print("no cloud run log")
    L = load_source("local", a.data, os.path.join(a.cache_dir, "status_cache.json"))
    C = load_source("cloud", CD, os.path.join(a.cache_dir, "status_cache_cloud.json"))
    if not L["S"] and not C["S"]: raise SystemExit("no readable snapshots")
    g = Grid(L["S"] or C["S"], now, END)
    ev = event_list([L, C], g)
    series = [source_series(s, g) for s in (L, C) if s["S"]]
    if L["S"] and C["S"]: series.append(merged_series(series[0], series[1], g))
    main_name = a.source or series[-1]["name"]
    pick = {s["name"]: s for s in series}
    if main_name not in pick: raise SystemExit(f"no {main_name} snapshots")
    print(f"\n=== detailed report on the {main_name} series" + ("" if main_name == "merged" else " (reference only; the 80% rule uses the merged series)"))
    report(pick[main_name], g, ev)
    compare(series, g, ev, main_name)

if __name__ == "__main__":
    main()
