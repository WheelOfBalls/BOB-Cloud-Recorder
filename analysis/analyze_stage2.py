#!/usr/bin/env python3
# Stage 2 analysis for the BOB crypto kill test, written to docs/PREREGISTRATION_stage2.md (a verbatim copy of
# stage2/PREREGISTRATION.md in the BOB folder), including deviations 3 and 4. Choices the pre-registration leaves
# open are listed in analysis/NOTES.md, each with the reading taken here. Research only: it reads recorded public
# data and simulates trades. It places no orders and needs no account.
#
#   coverage  slot validity, the deviation-4 merge and per-event 80% coverage. Reads snapshots only, never
#             outcomes or trades, so it is safe to run while recording continues.
#   run       the one-shot test: S1, S2, S3 and the reference results. Needs settlements and the trade tape
#             (pull_after.py). Refuses to run on real data before the recording end time, refuses before
#             every qualifying event has settled, and refuses to overwrite an earlier result.
#
# Stdlib only, so it runs with any Python 3.9+ on Windows, Linux or GitHub Actions.
import os, sys, json, gzip, glob, math, random, argparse, hashlib, statistics, collections, datetime as dt

UTC = dt.timezone.utc
# ---- fixed by the pre-registration ----
STEP = 300                      # 5-minute slots
WINDOW_H = 30                   # possible slots = the 360 slots in the 30 h before a 5pm close (deviation 3)
NEED_FRAC = 0.80                # an event qualifies with >= 80% of possible slots valid
NEED_EVENTS = 10                # a test needs >= 10 settled qualifying events
NEED_FILLS = 100                # S3 kills with fewer than 100 fills
MAX_GAP_S = 5.0                 # Deribit and Kalshi top-of-book requests finished within 5 s
MAX_MOVE_PCT = 0.10             # Deribit index moved under 0.10% across the Kalshi pull
MID_LO, MID_HI = 0.06, 0.94     # row filter on the Kalshi mid
MAX_H = 30.0                    # row filter: under 30 hours to close
FEE_RATE = 0.07                 # taker fee f(q) = 0.07 q (1 - q); makers pay none
DK = 50.0                       # strike step for -dC/dK
BOOT = 2000                     # bootstrap reps over days
SEED = 20261105                 # same seed as stage 1
# ---- conventions chosen here (see NOTES.md) ----
YEAR_S = 365.0 * 86400          # calendar time, ACT/365
DERIBIT_EXPIRY_HOUR = 8         # Deribit BTC options expire 08:00 UTC
NEED_SLOTS = int(NEED_FRAC * WINDOW_H * 12 + 0.999)   # 288, as in status.py
FIVE_PM = "17"                  # 5pm ET events: event ticker ends in 17
TOL = 1e-6
END_UTC = "2026-11-19T15:25:00+00:00"   # stage2/end_utc.txt; on real data --end must match it


def fee(q):
    return FEE_RATE * q * (1.0 - q)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def iso_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fmt(t):
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


# =====================================================================================================
# Fair value: Black-76 on a cubic total-variance smile, undiscounted
# =====================================================================================================
def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def black(F, K, w, call=True):
    """Undiscounted Black-76 price with total variance w = sigma^2 * T."""
    if w <= 0:
        c = max(F - K, 0.0)
    else:
        s = math.sqrt(w)
        d1 = (math.log(F / K) + 0.5 * w) / s
        c = F * ncdf(d1) - K * ncdf(d1 - s)
    return c if call else c - F + K


def implied_w(price, x, call):
    """Total variance from a price in units of the forward (F = 1, K = x). None if no solution."""
    lo_p = max(1.0 - x, 0.0) if call else max(x - 1.0, 0.0)
    hi_p = 1.0 if call else x
    if not (lo_p + 1e-12 < price < hi_p - 1e-12):
        return None
    lo, hi = 1e-6, 6.0                      # sqrt(w); 6 is far beyond any short-dated BTC option
    if black(1.0, x, hi * hi, call) < price:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if black(1.0, x, mid * mid, call) < price:
            lo = mid
        else:
            hi = mid
    s = 0.5 * (lo + hi)
    return s * s


def lstsq_cubic(ks, ws):
    """Ordinary least squares fit of w = a + b k + c k^2 + d k^3. Returns (a, b, c, d) or None."""
    if len(ks) < 4 or len({round(k, 9) for k in ks}) < 4:
        return None
    A = [[0.0] * 4 for _ in range(4)]
    y = [0.0] * 4
    for k, w in zip(ks, ws):
        p = (1.0, k, k * k, k * k * k)
        for i in range(4):
            y[i] += p[i] * w
            for j in range(4):
                A[i][j] += p[i] * p[j]
    # Gaussian elimination with partial pivoting
    M = [A[i][:] + [y[i]] for i in range(4)]
    for c in range(4):
        piv = max(range(c, 4), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-300:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(c + 1, 4):
            f = M[r][c] / M[c][c]
            for j in range(c, 5):
                M[r][j] -= f * M[c][j]
    out = [0.0] * 4
    for r in range(3, -1, -1):
        out[r] = (M[r][4] - sum(M[r][j] * out[j] for j in range(r + 1, 4))) / M[r][r]
    return tuple(out)


def cubic(co, k):
    a, b, c, d = co
    return a + k * (b + k * (c + k * d))


def parse_instrument(name):
    """BTC-8NOV26-88000-P -> (expiry timestamp, strike, is_call)."""
    _, exp, strike, cp = name.split("-")
    e = dt.datetime.strptime(exp, "%d%b%y").replace(hour=DERIBIT_EXPIRY_HOUR, tzinfo=UTC).timestamp()
    return e, float(strike), cp == "C"


def fit_chain(options, t_now):
    """One cubic w(k) per Deribit expiry. Returns a list of dicts sorted by time to expiry."""
    by_exp = collections.defaultdict(list)
    for o in options:
        bid, ask, F, iv = num(o.get("bid_price")), num(o.get("ask_price")), num(o.get("underlying_price")), num(o.get("mark_iv"))
        if iv is None or bid is None or ask is None or F is None:   # mark_iv missing, or not two-sided
            continue
        if bid <= 0 or ask <= 0 or ask < bid or F <= 0:
            continue
        try:
            e, K, call = parse_instrument(o["instrument_name"])
        except (ValueError, KeyError):
            continue
        if (K >= F) != call:              # out-of-the-money only: calls at K >= F, puts at K < F (NOTES.md item 6)
            continue
        by_exp[e].append((K, call, F, 0.5 * (bid + ask)))
    fits = []
    for e, rows in by_exp.items():
        tau = (e - t_now) / YEAR_S
        if tau <= 0:
            continue
        ks, ws = [], []
        for K, call, F, mid in rows:
            x = K / F
            w = implied_w(mid, x, call)          # Deribit prices are in BTC, i.e. USD price / underlying_price
            if w is not None:
                ks.append(math.log(x)); ws.append(w)
        co = lstsq_cubic(ks, ws)
        if co is None:
            continue
        fits.append({"expiry": e, "tau": tau, "F": statistics.median(r[2] for r in rows), "co": co,
                     "n": len(ks), "kmin": min(ks), "kmax": max(ks)})
    fits.sort(key=lambda f: f["tau"])
    return fits


def p_above(fits, K, t_close, t_now):
    """Risk-neutral P(BTC > K at t_close) as -dC/dK of the Black price, central difference +-DK. None if undefined."""
    tauT = (t_close - t_now) / YEAR_S
    if tauT <= 0 or not fits:
        return None
    if tauT < fits[0]["tau"]:                                 # before the first expiry: scale by time remaining
        f1 = fits[0]; F = f1["F"]
        W = lambda k: cubic(f1["co"], k) * tauT / f1["tau"]
    else:
        f1 = f2 = None
        for a, b in zip(fits, fits[1:]):
            if a["tau"] <= tauT <= b["tau"]:
                f1, f2 = a, b; break
        if f1 is None:
            return None                                      # beyond the last fitted expiry: no extrapolation
        u = (tauT - f1["tau"]) / (f2["tau"] - f1["tau"])
        F = f1["F"] + u * (f2["F"] - f1["F"])                 # forward interpolated in calendar time too
        W = lambda k: cubic(f1["co"], k) + u * (cubic(f2["co"], k) - cubic(f1["co"], k))
    lo, hi = K - DK, K + DK
    wl, wh = W(math.log(lo / F)), W(math.log(hi / F))
    if wl <= 0 or wh <= 0:
        return None
    p = (black(F, lo, wl) - black(F, hi, wh)) / (2 * DK)
    return p if 0.0 <= p <= 1.0 else None


# =====================================================================================================
# Snapshots: validity, slots, and the deviation-4 merge
# =====================================================================================================
def read_snapshot(path):
    try:
        with gzip.open(path, "rt") as f:
            return json.load(f)
    except Exception:
        return None


def index_price(s, key):
    b = (s.get(key) or {}).get("body") or {}
    return (b.get("result") or {}).get("index_price")


def snapshot_meta(s, path, src):
    """Validity exactly as status.py computes it."""
    t = dt.datetime.fromisoformat(s["utc"]).timestamp()
    ch, kd = s.get("deribit") or {}, s.get("kxbtcd") or {}
    opts, md = ch.get("options") or [], kd.get("markets") or []
    i0, i1 = index_price(s, "index_before"), index_price(s, "index_after")
    move = abs(i1 - i0) / i0 * 100 if i0 and i1 else None
    gap = abs(kd["t1"] - ch["t1"]) if opts and md else None
    valid = bool(opts) and bool(md) and gap is not None and gap <= MAX_GAP_S and move is not None and move < MAX_MOVE_PCT
    events = {}
    for m in md:
        ev = m.get("event_ticker") or ""
        if ev.endswith(FIVE_PM) and m.get("close_time"):
            events[ev] = iso_ts(m["close_time"])
    return {"path": path, "src": src, "t": t, "valid": valid, "gap": gap, "move": move, "events": events,
            "synthetic": s.get("synthetic") is True,
            "kd_t0": kd.get("t0"), "kd_t1": kd.get("t1"), "chain_t1": ch.get("t1"),
            "declared": ((s.get("source") or {}).get("host"))}


def load_meta(dirs):
    """dirs: list of (src, data_dir). Snapshot files are <data_dir>/<YYYY-MM-DD>/<HHMMSS>.json.gz."""
    metas, unreadable = [], []
    for src, d in dirs:
        if not d:
            continue
        for p in sorted(glob.glob(os.path.join(d, "*", "*.json.gz"))):
            s = read_snapshot(p)
            if s is None or "utc" not in s:
                unreadable.append(p); continue
            metas.append(snapshot_meta(s, p, src))
    metas.sort(key=lambda m: (m["t"], m["src"]))
    return metas, unreadable


class Grid:
    """Slot assignment as in status.py: phase = median of t mod 300, each snapshot to the nearest slot."""
    def __init__(self, metas):
        self.phase = statistics.median(m["t"] % STEP for m in metas) if metas else 182.0

    def slot(self, t):
        return int((t - self.phase + STEP / 2) // STEP)

    def slot_t(self, i):
        return i * STEP + self.phase


def build_series(metas, grid, rule):
    """Returns {slot: meta or None-for-invalid}, plus {slot: first recorded meta} for order cancellation timing.
    rule 'merged'  : deviation 4. Local snapshot (status.py's pick: the first local one in the slot) if valid,
                     else the first valid cloud snapshot in the slot, else the slot is invalid.
    rule 'local' / 'cloud' : that source alone, status.py's rule (first snapshot in the slot counts)."""
    by = collections.defaultdict(lambda: {"local": [], "cloud": []})
    for m in metas:
        by[grid.slot(m["t"])][m["src"]].append(m)
    pick, recorded = {}, {}
    for i, d in by.items():
        loc, cld = d["local"], d["cloud"]
        if rule == "merged":
            if loc and loc[0]["valid"]:
                pick[i] = loc[0]
            else:
                pick[i] = next((c for c in cld if c["valid"]), None)
            first = (loc or cld or [None])[0]
        else:
            xs = loc if rule == "local" else cld
            if not xs:
                continue
            pick[i] = xs[0] if xs[0]["valid"] else None
            first = xs[0]
        recorded[i] = pick[i] if pick.get(i) is not None else first
    return pick, recorded


def event_coverage(pick, grid, events):
    """events: {event_ticker: close_ts}. Valid slots in the 30 h window where the event was listed."""
    out = {}
    for ev, close in events.items():
        ws = [i for i in range(grid.slot(close - WINDOW_H * 3600) - 1, grid.slot(close) + 2)
              if close - WINDOW_H * 3600 <= grid.slot_t(i) < close]
        good = sum(1 for i in ws if pick.get(i) is not None and ev in pick[i]["events"])
        out[ev] = {"close": close, "possible": len(ws), "valid": good, "qualifies": good >= NEED_SLOTS}
    return out


# =====================================================================================================
# Rows
# =====================================================================================================
def book_depth(book, side, price):
    """Contracts resting at exactly `price` on the YES-bid (side 'yes') or NO-bid (side 'no') ladder."""
    if not book:
        return None
    lvl = book.get("yes_dollars" if side == "yes" else "no_dollars") or []
    for p, q in lvl:
        if abs(float(p) - price) < TOL:
            return float(q)
    return 0.0


def market_prob(fits, m, t_close, t_now):
    st = m.get("strike_type")
    lo, hi = num(m.get("floor_strike")), num(m.get("cap_strike"))
    if st == "greater" and lo:
        return p_above(fits, lo, t_close, t_now)
    if st == "less" and hi:
        p = p_above(fits, hi, t_close, t_now); return None if p is None else 1 - p
    if st == "between" and lo and hi:
        a, b = p_above(fits, lo, t_close, t_now), p_above(fits, hi, t_close, t_now)
        return None if a is None or b is None else max(a - b, 0.0)
    return None


def snapshot_rows(meta, want_brackets=True):
    """All candidate rows of one valid snapshot (5pm KXBTCD markets that pass the row filters)."""
    s = read_snapshot(meta["path"])
    ch, kd = s["deribit"], s["kxbtcd"]
    t_now, t_q = ch["t1"], kd["t1"]
    fits = fit_chain(ch["options"], t_now)
    books = s.get("books") or {}
    rows, dropped, brackets = [], [], []

    def candidates(markets):
        for m in markets:
            ev = m.get("event_ticker") or ""
            if not ev.endswith(FIVE_PM) or not m.get("close_time"):
                continue
            bid, ask = num(m.get("yes_bid_dollars")), num(m.get("yes_ask_dollars"))
            if bid is None or ask is None or not (0 < bid < ask < 1):      # two-sided quote
                continue
            mid = 0.5 * (bid + ask)
            close = iso_ts(m["close_time"]); h = (close - t_q) / 3600
            if not (MID_LO - TOL <= mid <= MID_HI + TOL) or not (0 < h < MAX_H):
                continue
            yield m, ev, bid, ask, mid, close, h

    for m, ev, bid, ask, mid, close, h in candidates(kd["markets"]):
        p = market_prob(fits, m, close, t_now)
        if p is None:
            dropped.append(ev); continue
        book = (books.get(m["ticker"]) or {}).get("book")
        rows.append({"event": ev, "ticker": m["ticker"], "close": close, "t": meta["t"], "t_q": t_q, "h": h,
                     "bid": bid, "ask": ask, "mid": mid, "p": p, "src": meta["src"],
                     "yes_depth_book": book_depth(book, "yes", bid), "no_depth_book": book_depth(book, "no", 1 - ask),
                     "yes_depth_top": num(m.get("yes_bid_size_fp")), "no_depth_top": num(m.get("yes_ask_size_fp"))})
    if want_brackets:
        for m, ev, bid, ask, mid, close, h in candidates((s.get("kxbtc") or {}).get("markets") or []):
            p = market_prob(fits, m, close, t_now)
            if p is not None:
                brackets.append({"event": ev, "ticker": m["ticker"], "t": meta["t"], "h": h, "bid": bid, "ask": ask, "p": p})
    return rows, brackets, dropped, len(fits)


# =====================================================================================================
# Tests
# =====================================================================================================
def gap_sides(r):
    """S1 gap for each side: YES bought at the ask, NO bought at 1 - bid, both net of the taker fee."""
    gy = r["p"] - r["ask"] - fee(r["ask"])
    no_price = 1 - r["bid"]
    gn = (1 - r["p"]) - no_price - fee(no_price)
    return gy, gn


def boot_ratio(groups, rng):
    """groups: {day: (numerator, denominator)}. Ratio estimate and 95% percentile CI, resampling days."""
    keys = sorted(groups)
    if not keys:
        return {"est": None, "lo": None, "hi": None, "days": 0, "n": 0}
    nums = [groups[k][0] for k in keys]; dens = [groups[k][1] for k in keys]
    est = sum(nums) / sum(dens) if sum(dens) else None
    bs = []
    for _ in range(BOOT):
        a = b = 0.0
        for _ in keys:
            j = rng.randrange(len(keys)); a += nums[j]; b += dens[j]
        if b:
            bs.append(a / b)
    bs.sort()
    lo = bs[int(0.025 * len(bs))] if bs else None
    hi = bs[min(len(bs) - 1, int(0.975 * len(bs)))] if bs else None
    return {"est": est, "lo": lo, "hi": hi, "days": len(keys), "n": sum(dens)}


def by_day(items, key_num, key_den=lambda x: 1.0):
    g = collections.defaultdict(lambda: [0.0, 0.0])
    for x in items:
        g[x["event"]][0] += key_num(x); g[x["event"]][1] += key_den(x)
    return {k: tuple(v) for k, v in g.items()}


def payoff(result, side):
    return 1.0 if result == side else 0.0


def s1(rows, rng):
    for r in rows:
        r["g"] = max(gap_sides(r))
    return boot_ratio(by_day(rows, lambda r: r["g"]), rng)


def s2_trades(rows, results):
    """First row with g > 0 per strike and event; buy the better side at the touch, pay the taker fee."""
    seen, trades = set(), []
    for r in sorted(rows, key=lambda r: r["t"]):
        k = (r["event"], r["ticker"])
        if k in seen or r["g"] <= 0:
            continue
        seen.add(k)
        res = results.get(r["ticker"])
        if res not in ("yes", "no"):
            continue
        gy, gn = gap_sides(r)
        side = "yes" if gy >= gn else "no"
        price = r["ask"] if side == "yes" else 1 - r["bid"]
        trades.append({"event": r["event"], "ticker": r["ticker"], "t": r["t"], "side": side, "price": price,
                       "pnl": payoff(res, side) - price - fee(price)})
    return trades


def tape_volume(tape, side, price, t0, t1):
    """Contracts that traded at `price` against a resting `side` bid in (t0, t1].
    A resting YES bid at p is hit by a taker selling YES, i.e. taker_side 'no' at yes_price p.
    A resting NO bid at q is hit by a taker buying YES at yes_price 1 - q (taker_side 'yes')."""
    want_taker = "no" if side == "yes" else "yes"
    yes_price = price if side == "yes" else 1 - price
    v = 0.0
    for tt, yp, c, ts in tape:
        if t0 < tt <= t1 and ts == want_taker and abs(yp - yes_price) < TOL:
            v += c
    return v


def s3_fills(rows, results, tapes, windows, depth_mult=1.0, both_sides=False):
    """Back-of-queue 1-contract maker orders at the best bid, cancelled at the next snapshot, held to settlement.
    A fill needs more contracts traded at that price and side than the recorded depth (times depth_mult)."""
    fills, orders, no_tape = [], 0, 0
    for r in rows:
        res = results.get(r["ticker"])
        tape = tapes.get(r["ticker"])
        t0, t1 = windows[(r["t"], r["src"])]
        for side, price, fair, dbook, dtop in (("yes", r["bid"], r["p"], r["yes_depth_book"], r["yes_depth_top"]),
                                               ("no", 1 - r["ask"], 1 - r["p"], r["no_depth_book"], r["no_depth_top"])):
            if not both_sides and not fair > price:
                continue
            orders += 1
            if tape is None or res not in ("yes", "no"):
                no_tape += 1; continue
            depth = max(x for x in (dbook, dtop, 0.0) if x is not None)
            if tape_volume(tape, side, price, t0, t1) > depth * depth_mult:
                fills.append({"event": r["event"], "ticker": r["ticker"], "t": r["t"], "h": r["h"], "side": side,
                              "price": price, "pnl": payoff(res, side) - price})
    return fills, orders, no_tape


def s3_summary(fills, rng):
    out = boot_ratio(by_day(fills, lambda f: f["pnl"], lambda f: f["price"]), rng)
    out["fills"] = len(fills)
    out["mean_return_per_fill"] = (sum(f["pnl"] / f["price"] for f in fills) / len(fills)) if fills else None
    return out


def brier_logloss(rows, results, rng):
    """p_opt against the Kalshi mid on each market's last row more than 1 h before close."""
    last = {}
    for r in rows:
        if r["h"] > 1 and r["ticker"] in results and results[r["ticker"]] in ("yes", "no"):
            k = (r["event"], r["ticker"])
            if k not in last or r["t"] > last[k]["t"]:
                last[k] = r
    xs = list(last.values())
    clip = lambda p: min(max(p, 1e-6), 1 - 1e-6)
    out = {"markets": len(xs)}
    for name, f in (("brier", lambda p, y: (p - y) ** 2), ("logloss", lambda p, y: -(y * math.log(clip(p)) + (1 - y) * math.log(1 - clip(p))))):
        for who in ("p_opt", "mid"):
            key = "p" if who == "p_opt" else "mid"
            out[f"{name}_{who}"] = boot_ratio(by_day(xs, lambda r: f(r[key], 1.0 if results[r["ticker"]] == "yes" else 0.0)), rng)
        out[f"{name}_p_opt_minus_mid"] = boot_ratio(by_day(xs, lambda r: f(r["p"], 1.0 if results[r["ticker"]] == "yes" else 0.0)
                                                           - f(r["mid"], 1.0 if results[r["ticker"]] == "yes" else 0.0)), rng)
    return out


# =====================================================================================================
# Driver
# =====================================================================================================
def is_synthetic(dirs, metas=None):
    """Synthetic only if every folder has a SYNTHETIC_FIXTURE marker and every snapshot says so itself.
    Real recorder snapshots never carry "synthetic", so a stray marker file cannot unlock the test guards."""
    marked = all(os.path.exists(os.path.join(d, "SYNTHETIC_FIXTURE")) for _, d in dirs if d)
    return marked and (metas is None or (bool(metas) and all(m.get("synthetic") for m in metas)))


def read_end(path):
    with open(path) as f:
        return dt.datetime.fromisoformat(f.read().strip()).timestamp()


def load_results(path):
    """settlements.json: {"markets": {ticker: {"result": "yes"|"no"|..., "event_ticker": ...}}}"""
    with open(path) as f:
        d = json.load(f)
    return {k: (v.get("result") if isinstance(v, dict) else v) for k, v in d["markets"].items()}


def load_tape(trades_dir, ticker):
    p = os.path.join(trades_dir, ticker + ".json.gz")
    if not os.path.exists(p):
        return None, False
    with gzip.open(p, "rt") as f:
        d = json.load(f)
    out = []
    trunc = bool(d.get("truncated"))
    for t in d["trades"]:
        yp, c = num(t.get("yes_price_dollars")), num(t.get("count_fp"))
        if yp is None or c is None or not t.get("created_time"):
            continue
        out.append((iso_ts(t["created_time"]), yp, c, t.get("taker_side")))
    out.sort()
    return out, trunc


def series_report(name, metas, grid, rule, now):
    pick, recorded = build_series(metas, grid, rule)
    events = {}
    for m in metas:
        if rule == "merged" or m["src"] == rule:
            events.update(m["events"])
    cov = event_coverage(pick, grid, events)
    return {"name": name, "pick": pick, "recorded": recorded, "coverage": cov}


def coverage_text(rep, now, end):
    pick, cov = rep["pick"], rep["coverage"]
    lines = [f"== coverage, {rep['name']}: slots with a snapshot {len(pick)}, valid {sum(1 for v in pick.values() if v)}"]
    srcs = collections.Counter(v["src"] for v in pick.values() if v)
    lines.append("   valid slots by source: " + ", ".join(f"{k} {v}" for k, v in sorted(srcs.items())))
    for ev, c in sorted(cov.items(), key=lambda x: x[1]["close"]):
        tag = "QUALIFIES" if c["qualifies"] else ("fails" if c["close"] <= now or now >= end else "open")
        lines.append(f"   {ev:22s} close {fmt(c['close'])}Z  valid {c['valid']}/{c['possible']} (need {NEED_SLOTS})  {tag}")
    return lines


def windows_for(rep, grid):
    """Order life: from this snapshot's Kalshi pull finish to the next recorded snapshot's Kalshi pull start,
    at most 300 s."""
    rec = rep["recorded"]; slots = sorted(rec)
    win = {}
    for a, b in zip(slots, slots[1:] + [None]):
        m = rep["pick"].get(a)
        if m is None:
            continue
        t0 = m["kd_t1"]; t1 = t0 + STEP
        if b is not None:
            nxt = rec[b]
            t1 = min(t1, nxt["kd_t0"] if nxt.get("kd_t0") else nxt["t"])
        win[(m["t"], m["src"])] = (t0, t1)
    return win


def run_tests(rep, grid, row_cache, results, tapes_dir, now, verbose_lines):
    rng = random.Random(SEED)
    cov = rep["coverage"]
    settled = {}
    for ev, c in cov.items():
        tick = [t for t, r in results.items() if t.startswith(ev + "-")]
        # settled: closed, and every market of the event has a final result (a void market only loses its own rows)
        settled[ev] = c["close"] <= now and bool(tick) and all(results[t] for t in tick)
    qual = sorted(ev for ev, c in cov.items() if c["qualifies"] and settled[ev])
    rows, brackets, dropped = [], [], 0
    for i, m in sorted(rep["pick"].items()):
        if m is None:
            continue
        rs, bs, dr, _ = row_cache(m)
        rows += [r for r in rs if r["event"] in qual]
        brackets += [b for b in bs if b["event"].replace("KXBTC-", "KXBTCD-") in qual]
        dropped += sum(1 for ev in dr if ev in qual)
    tapes, truncated = {}, 0
    for t in {r["ticker"] for r in rows}:
        tapes[t], tr = load_tape(tapes_dir, t)
        truncated += tr
    win = windows_for(rep, grid)
    out = {"series": rep["name"], "qualifying_settled_events": qual, "n_events": len(qual), "rows": len(rows),
           "rows_dropped_no_fair_value": dropped, "row_sources": dict(collections.Counter(r["src"] for r in rows))}
    complete = len(qual) >= NEED_EVENTS
    out["complete"] = complete
    out["S1"] = s1(rows, rng)
    tr = s2_trades(rows, results)
    out["S2"] = boot_ratio(by_day(tr, lambda x: x["pnl"]), rng); out["S2"]["trades"] = len(tr)
    fills, orders, no_tape = s3_fills(rows, results, tapes, win)
    out["S3"] = s3_summary(fills, rng); out["S3"]["orders"] = orders; out["S3"]["orders_without_tape_or_result"] = no_tape
    out["S3"]["truncated_tapes"] = truncated
    def verdict(est, extra_kill=False):
        if not complete:
            return "INCOMPLETE"
        if est is None:
            return "INCOMPLETE"
        return "KILL" if est <= 0 or extra_kill else "PASS"
    out["S1"]["verdict"] = verdict(out["S1"]["est"])
    out["S2"]["verdict"] = verdict(out["S2"]["est"])
    out["S3"]["verdict"] = verdict(out["S3"]["est"], out["S3"]["fills"] < NEED_FILLS)
    # ---- reported, never used to rescue a kill ----
    ref = {}
    half, _, _ = s3_fills(rows, results, tapes, win, depth_mult=0.5)
    ref["S3_half_depth"] = s3_summary(half, rng)
    both, _, _ = s3_fills(rows, results, tapes, win, both_sides=True)
    ref["S3b_both_sides"] = s3_summary(both, rng)
    for lab, lo, hi in (("last_hour", 0, 1), ("1_6h", 1, 6), ("gt_6h", 6, MAX_H)):
        ref[f"S3_hours_{lab}"] = s3_summary([f for f in fills if lo < f["h"] <= hi], rng)
    ref["calibration_final_before_T_minus_1h"] = brier_logloss(rows, results, rng)
    for b in brackets:
        b["g"] = max(gap_sides(b))
    ref["KXBTC_bracket_gap"] = boot_ratio(by_day(brackets, lambda b: b["g"]), rng)
    ref["S1_with_fee_rounded_up_to_cent"] = boot_ratio(by_day(rows, lambda r: max(
        r["p"] - r["ask"] - math.ceil(fee(r["ask"]) * 100 - 1e-9) / 100,
        (1 - r["p"]) - (1 - r["bid"]) - math.ceil(fee(1 - r["bid"]) * 100 - 1e-9) / 100)), rng)
    out["reference"] = ref
    return out


def preflight(rep):
    """Runs the fair-value and row pipeline on the merged series and prints counts only: no prices, gaps, p_opt,
    outcomes or trades. Meant to catch format or fitting problems on real data before the one-shot run."""
    fitted, rows, dropped, books, brackets = collections.Counter(), collections.Counter(), collections.Counter(), [0, 0], 0
    for m in rep["pick"].values():
        if m is None:
            continue
        rs, bs, dr, k = snapshot_rows(m)
        fitted[k] += 1; brackets += len(bs)
        for r in rs:
            rows[r["event"]] += 1
            books[0] += 1; books[1] += r["yes_depth_book"] is not None
        for ev in dr:
            dropped[ev] += 1
    out = ["\n== preflight (counts only)", "   valid snapshots by number of fitted Deribit expiries: " +
           ", ".join(f"{k}: {v}" for k, v in sorted(fitted.items()))]
    for ev in sorted(set(rows) | set(dropped)):
        out.append(f"   {ev:22s} rows {rows[ev]:6d}  dropped for lack of a fair value {dropped[ev]}")
    out.append(f"   rows with a recorded order book {books[1]} of {books[0]}; KXBTC bracket rows {brackets}")
    return out


def fmt_est(x, pct=False):
    if not x or x.get("est") is None:
        return "n/a"
    s = (lambda v: f"{v * 100:+.2f}%") if pct else (lambda v: f"{v:+.4f}")
    return f"{s(x['est'])} [{s(x['lo'])}, {s(x['hi'])}] (days {x['days']}, n {x['n']:.0f})"


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("coverage", "preflight", "run"))
    ap.add_argument("--local", help="local Windows recorder data/ folder")
    ap.add_argument("--cloud", help="cloud recorder data/ folder (a checkout of the stage2-data branch, its data/)")
    ap.add_argument("--settlements", help="settlements.json from pull_after.py")
    ap.add_argument("--trades", help="trades/ folder from pull_after.py")
    ap.add_argument("--out", help="folder for results (run mode)")
    ap.add_argument("--end", default=os.path.join(here, "..", "stage2", "end_utc.txt"))
    ap.add_argument("--now", help="override the clock (synthetic fixtures only)")
    a = ap.parse_args(argv)
    dirs = [("local", a.local), ("cloud", a.cloud)]
    if not a.local and not a.cloud:
        ap.error("give --local and/or --cloud")
    metas, unreadable = load_meta(dirs)
    if not metas:
        raise SystemExit("no readable snapshots")
    synthetic = is_synthetic(dirs, metas)
    now = dt.datetime.now(UTC).timestamp()
    if a.now:
        if not synthetic:
            raise SystemExit("--now is only allowed on synthetic fixtures")
        now = dt.datetime.fromisoformat(a.now).timestamp()
    end = read_end(a.end)
    grid = Grid(metas)
    lines = [f"stage 2 analysis  {'SYNTHETIC FIXTURE' if synthetic else 'REAL DATA'}  now {fmt(now)}Z  end {fmt(end)}Z",
             f"snapshots: {collections.Counter(m['src'] for m in metas)}; unreadable {len(unreadable)}; slot phase {grid.phase:.1f}s"]
    for src in ("local", "cloud"):
        ph = [m["t"] % STEP for m in metas if m["src"] == src]
        if ph:
            lines.append(f"   {src} median phase {statistics.median(ph):.1f}s")
    bad_decl = sum(1 for m in metas if m["src"] == "cloud" and m["declared"] != "github-actions") + \
               sum(1 for m in metas if m["src"] == "local" and m["declared"] is not None)
    lines.append(f"   snapshots whose own source block disagrees with their folder: {bad_decl}")
    reps = {r: series_report(r, metas, grid, r, now) for r in ("merged", "local", "cloud")}
    for r in ("merged", "local", "cloud"):
        lines += coverage_text(reps[r], now, end)
        if r == "merged":
            lines.append("   (the merged series is the one the tests use; local and cloud are reference only)")

    if a.mode == "coverage":
        print("\n".join(lines)); return 0
    if a.mode == "preflight":
        lines += preflight(reps["merged"]); print("\n".join(lines)); return 0

    # ---------------- run: the one-shot test ----------------
    if not (a.settlements and a.trades and a.out):
        ap.error("run needs --settlements, --trades and --out")
    if not synthetic and end != dt.datetime.fromisoformat(END_UTC).timestamp():
        raise SystemExit(f"refusing: --end gives {fmt(end)}Z, but on real data the end is fixed at {END_UTC}")
    if not synthetic and now < end:
        raise SystemExit(f"refusing: recording ends {fmt(end)}Z; the test may not run before then")
    res_path = os.path.join(a.out, "stage2_results.json")
    if not synthetic and os.path.exists(res_path):
        raise SystemExit(f"refusing: {res_path} exists. The pre-registered test runs once.")
    results = load_results(a.settlements)
    open_q = [ev for ev, c in reps["merged"]["coverage"].items() if c["qualifies"] and c["close"] > now]
    if not synthetic and open_q:
        raise SystemExit(f"refusing: qualifying events not yet closed: {open_q}")

    cache = {}
    def row_cache(m):
        if m["path"] not in cache:
            cache[m["path"]] = snapshot_rows(m)
        return cache[m["path"]]

    out = {"synthetic": synthetic, "run_utc": fmt(now), "script_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(),
           "slot_phase_s": grid.phase}
    for r in ("merged", "local", "cloud"):
        if any(m["src"] == r for m in metas) or r == "merged":
            out[r] = run_tests(reps[r], grid, row_cache, results, a.trades, now, lines)
    m = out["merged"]
    lines.append("\n== THE TEST (merged series, deviation 4)")
    lines.append(f"qualifying settled events {m['n_events']} (need {NEED_EVENTS}): {'complete' if m['complete'] else 'INCOMPLETE'}")
    lines.append(f"rows {m['rows']} by source {m['row_sources']}; rows dropped for lack of a fair value {m['rows_dropped_no_fair_value']}")
    lines.append(f"S1 mean net gap at the touch     {fmt_est(m['S1'])}  -> {m['S1']['verdict']}")
    lines.append(f"S2 mean P&L per contract        {fmt_est(m['S2'])}  trades {m['S2']['trades']}  -> {m['S2']['verdict']}")
    lines.append(f"S3 maker return per dollar      {fmt_est(m['S3'], True)}  fills {m['S3']['fills']} of {m['S3']['orders']} orders  -> {m['S3']['verdict']}")
    lines.append(f"   S3 orders without a tape or result {m['S3']['orders_without_tape_or_result']}; truncated tapes {m['S3']['truncated_tapes']}")
    lines.append("\n== reported, never used to rescue a kill")
    for k, v in m["reference"].items():
        if k.startswith("calibration"):
            lines.append(f"{k}: markets {v['markets']}")
            for kk, vv in v.items():
                if kk != "markets":
                    lines.append(f"   {kk}: {fmt_est(vv)}")
        else:
            lines.append(f"{k}: {fmt_est(v, k.startswith('S3'))}" + (f" fills {v['fills']}" if "fills" in v else ""))
    for r in ("local", "cloud"):
        if r in out:
            x = out[r]
            lines.append(f"\n== {r} only (reference): events {x['n_events']}, rows {x['rows']}; S1 {fmt_est(x['S1'])}; "
                         f"S2 {fmt_est(x['S2'])}; S3 {fmt_est(x['S3'], True)} fills {x['S3']['fills']}")
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(res_path, "w"), indent=1, default=str)
    open(os.path.join(a.out, "stage2_results.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
