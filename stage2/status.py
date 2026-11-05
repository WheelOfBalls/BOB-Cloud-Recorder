# Coverage report for the stage 2 recording. Never writes to data/ or touches the recorder.
# It keeps a small cache of per-snapshot metrics (status_cache.json, next to this file) so it stays fast as files pile up.
# Validity and coverage follow PREREGISTRATION.md: a snapshot is valid if Deribit and Kalshi KXBTCD top-of-book
# requests finished within 5 s of each other and the Deribit index moved under 0.10% across the Kalshi pull.
# An event qualifies if at least 80% of its possible 5-minute slots (the 30 hours before its 5pm close) are valid.
import os, sys, csv, json, gzip, glob, hashlib, statistics, datetime as dt, collections
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "data")
CACHE = os.path.join(HERE, "status_cache.json"); CACHE_V = 1
STEP = 300; WINDOW_H = 30; NEED_FRAC = 0.80; NEED_EVENTS = 10
UTC = dt.timezone.utc
def ts(x): return dt.datetime.fromtimestamp(x, UTC)
def fmt(x): return ts(x).strftime("%m-%d %H:%M")

log = os.path.join(D, "run_log.csv")
if not os.path.exists(log): raise SystemExit("no snapshots yet")
now = dt.datetime.now(UTC).timestamp()
if "--now" in sys.argv: now = dt.datetime.fromisoformat(sys.argv[sys.argv.index("--now") + 1]).timestamp()  # for testing
END = dt.datetime.fromisoformat(open(os.path.join(HERE, "end_utc.txt")).read().strip()).timestamp() if os.path.exists(os.path.join(HERE, "end_utc.txt")) else None

# ---------- the original summary, from run_log.csv ----------
R = [r for r in csv.reader(open(log)) if r]
rts = [dt.datetime.fromisoformat(r[0]) for r in R]
span = max((dt.datetime.now(UTC) - rts[0]).total_seconds(), 1)
ok = [r for r in R if int(r[7]) == 0 and int(r[1]) > 0 and int(r[2]) > 0 and float(r[5]) <= 5]
print(f"snapshots {len(R)} of about {int(span // 300) + 1} expected; clean {len(ok)}; first {rts[0]:%Y-%m-%d %H:%M}Z; last {rts[-1]:%Y-%m-%d %H:%M}Z ({(now - rts[-1].timestamp()) / 60:.0f} min ago)")
if END: print("ends", ts(END).isoformat())
print("mean per snapshot: options %.0f, KXBTCD %.0f, KXBTC %.0f, books %.0f; mean run %.1fs; max Deribit-Kalshi gap %.2fs" % tuple([sum(float(r[i]) for r in R) / len(R) for i in (1, 2, 3, 4, 6)] + [max(float(r[5]) for r in R)]))
e = collections.Counter(x.split(":")[0] + ":" + x.split(":", 1)[-1][:60] for r in R if r[8] for x in r[8].split(" | "))
for k, v in e.most_common(5): print("error", v, k)
print("disk MB %.1f" % (sum(os.path.getsize(os.path.join(p, f)) for p, _, fs in os.walk(D) for f in fs) / 1e6))

# ---------- per-snapshot metrics, read from the snapshot files themselves ----------
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0
def snapshot_metrics(path):
    try: s = json.load(gzip.open(path, "rt"))
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

cache = {}
try:
    c = json.load(open(CACHE))
    if c.get("v") == CACHE_V: cache = c["snaps"]
except Exception: pass
files = sorted(glob.glob(os.path.join(D, "*", "*.json.gz")))
for p in files:
    k = os.path.relpath(p, D).replace("\\", "/")
    if k not in cache or cache[k].get("size") != os.path.getsize(p):
        cache[k] = snapshot_metrics(p); cache[k]["size"] = os.path.getsize(p)
cache = {k: v for k, v in cache.items() if os.path.exists(os.path.join(D, k))}
try: json.dump({"v": CACHE_V, "snaps": cache}, open(CACHE, "w"))
except Exception as ex: print("note: could not write cache:", ex)
bad_files = sorted(k for k, v in cache.items() if "unreadable" in v)
S = sorted((v for v in cache.values() if "t" in v), key=lambda v: v["t"])
if not S: raise SystemExit("no readable snapshots")

# ---------- the 5-minute grid ----------
# The task fires at a fixed phase within each 5 minutes (about hh:m3:02). Each snapshot is assigned to the nearest slot.
phase = statistics.median(v["t"] % STEP for v in S)
def slot(t): return int((t - phase + STEP / 2) // STEP)
def slot_t(i): return i * STEP + phase
by_slot = collections.defaultdict(list)
for v in S: by_slot[slot(v["t"])].append(v)
first = slot(S[0]["t"])
last_done = int((min(now, END or now) - 240 - phase) // STEP)  # last slot whose run should have finished
slots = range(first, last_done + 1)
dupes = {i: vs for i, vs in by_slot.items() if len(vs) > 1}
pick = {i: vs[0] for i, vs in by_slot.items()}  # first snapshot in a slot counts; later ones are duplicates

# runs that started but never wrote a snapshot, from trace.log
runs = collections.OrderedDict()
tp = os.path.join(D, "trace.log")
if os.path.exists(tp):
    for line in open(tp):
        parts = line.split(None, 3)
        if len(parts) < 4: continue
        try: t = dt.datetime.fromisoformat(parts[0]).timestamp()
        except ValueError: continue
        r = runs.setdefault(parts[2], {"t": t, "steps": []}); r["steps"].append(parts[3].strip())
died = {slot(r["t"]): r["steps"][-1] for r in runs.values() if "written" not in r["steps"] and now - r["t"] > 240}
crash_t = []
cp = os.path.join(D, "crash_log.txt")
if os.path.exists(cp):
    for line in open(cp):
        try: crash_t.append(dt.datetime.fromisoformat(line.split()[0]).timestamp())
        except (ValueError, IndexError): pass
crash_slots = {slot(t) for t in crash_t}
hangs = sum(line.startswith("Timeout") for line in open(os.path.join(D, "hang_log.txt"))) if os.path.exists(os.path.join(D, "hang_log.txt")) else 0

def status(i):
    if i in pick: return "valid" if pick[i]["valid"] else "invalid"
    if i in died or i in crash_slots: return "died"
    return "none"
st = {i: status(i) for i in slots}
cnt = collections.Counter(st.values())
print(f"\n== Slots (5 min, phase :{int(phase // 60) % 5}m{int(phase % 60):02d}s) from {fmt(slot_t(first))}Z to {fmt(slot_t(last_done))}Z: {len(slots)}")
print(f"valid {cnt['valid']} ({cnt['valid'] / len(slots):.0%}); invalid snapshot {cnt['invalid']}; run started but died {cnt['died']}; no run at all {cnt['none']}")
print(f"duplicate snapshots in one slot: {sum(len(v) - 1 for v in dupes.values())} (only the first counts)" + (f"; unreadable files: {', '.join(bad_files)}" if bad_files else ""))
print(f"watchdog hang dumps {hangs}; crash log lines {len(crash_t)}; trace runs that never wrote: {len(died)}" +
      (" (" + ", ".join(f"{fmt(slot_t(i))} after '{s}'" for i, s in sorted(died.items())[-5:]) + ")" if died else ""))
why = collections.Counter(w for i in slots if st[i] == "invalid" for w in pick[i]["why"])
if why: print("invalid because:", "; ".join(f"{k} x{v}" for k, v in why.most_common()))

# ---------- outage windows ----------
print("\n== Outage windows (consecutive slots without a valid snapshot)")
wins, cur = [], None
for i in slots:
    if st[i] != "valid":
        cur = cur or {"a": i, "b": i, "kinds": collections.Counter()}; cur["b"] = i; cur["kinds"][st[i]] += 1
    elif cur: wins.append(cur); cur = None
if cur: wins.append(cur)
def nearest_valid(i, d):
    j = i + d
    while first <= j <= last_done:
        if st.get(j) == "valid": return pick[j]
        j += d
moves_all = [abs(b["idx"] / a["idx"] - 1) * 100 for a, b in zip(S, S[1:]) if a["idx"] and b["idx"] and b["t"] - a["t"] < 400]
typ = statistics.median(moves_all) if moves_all else None
for w in wins[-15:]:
    n = w["b"] - w["a"] + 1; a, b = nearest_valid(w["a"], -1), nearest_valid(w["b"], 1)
    mv = f"BTC {(b['idx'] / a['idx'] - 1) * 100:+.2f}% across it" if a and b and a["idx"] and b["idx"] else "BTC move unknown (edge of record)"
    print(f"  {fmt(slot_t(w['a']))}Z to {fmt(slot_t(w['b']) + STEP)}Z  {n} slots ({n * 5 / 60:.1f} h)  " +
          ", ".join(f"{k} {v}" for k, v in w["kinds"].items()) + f"  {mv}")
if len(wins) > 15: print(f"  ... {len(wins) - 15} earlier windows not shown")
if not wins: print("  none")
if typ is not None: print(f"  typical |BTC move| per 5 min while recording: {typ:.3f}%  (a gap's move is roughly comparable to this x sqrt(slots))")

# ---------- partial pulls, stale and duplicate data, alignment ----------
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

# ---------- are gaps random? ----------
print("\n== Coverage by UTC hour (valid / slots so far). Gaps tied to the hour bias rows toward some hours to close.")
hv, hn = collections.Counter(), collections.Counter()
for i in slots:
    h = ts(slot_t(i)).hour; hn[h] += 1; hv[h] += st[i] == "valid"
print("  " + "  ".join(f"{h:02d}h {hv[h] / hn[h]:.0%}" for h in range(24) if hn[h]))
print("  hours to the 22:00Z close for each UTC hour: 16-21Z is 0-6 h (and 24-30 h for the next day), 22-03Z 18-24 h, 04-09Z 12-18 h, 10-15Z 6-12 h")

# ---------- event coverage against the 10-event rule ----------
print(f"\n== 5pm events: need {NEED_EVENTS} settled events with >= {NEED_FRAC:.0%} of the {WINDOW_H * 12} slots in the {WINDOW_H} h before close valid")
ev = {}
for v in S:
    for name, (close, n, rows) in v["events"].items(): ev[name] = close
if END:  # events the recording can still reach, assuming one 5pm event per day as seen so far
    closes = sorted(ev.values()); c = closes[-1] if closes else None
    while c and c + 86400 - WINDOW_H * 3600 < END: c += 86400; ev.setdefault(ts(c).strftime("KXBTCD-%y%b%d17").upper() + " (expected)", c)
need = int(NEED_FRAC * WINDOW_H * 12 + 0.999)
can, done_ok, lines = 0, 0, []
for name, close in sorted(ev.items(), key=lambda x: x[1]):
    ws = [i for i in range(slot(close - WINDOW_H * 3600), slot(close) + 1) if close - WINDOW_H * 3600 <= slot_t(i) < close]
    good = sum(1 for i in ws if st.get(i) == "valid" and name.split()[0] in pick[i]["events"])
    future = sum(1 for i in ws if slot_t(i) > max(now, slot_t(last_done)) and (END is None or slot_t(i) < END))
    rec_slots = [i for i in ws if first <= i <= last_done]
    len_s = f"{good / len(rec_slots):.0%}" if rec_slots else "-"
    best = good + future; ok_now = best >= need
    can += ok_now; settled = close <= now; done_ok += settled and good >= need
    tag = "QUALIFIES" if settled and good >= need else ("FAILED" if settled or not ok_now else f"open, can still miss {best - need} slots ({(best - need) * 5 / 60:.1f} h)")
    lines.append(f"  {name:32s} close {fmt(close)}Z  valid {good}/{len(ws)}  future {future}  {tag}  [share of recorded slots {len_s}]")
print("\n".join(lines))
print(f"settled and qualifying {done_ok}; best case if every remaining slot is valid {can}; needed {NEED_EVENTS}; spare events {can - NEED_EVENTS}")
print("  verdict now:", "a pass/fail is still possible" if can >= NEED_EVENTS else "INCOMPLETE is now certain: too few events can reach 80%")
print("  note: the verdict uses the full 30 h window (deviation 3 in PREREGISTRATION.md); [share of recorded slots] is shown for reference only.")
