#!/usr/bin/env python3
# Stage 3 analysis for the BOB crypto test, written to docs/stage3/PREREGISTRATION_stage3.md (frozen, sha256
# a62576a8...c515). Readings of points it leaves open are in analysis/NOTES_stage3.md. Research only: it reads
# recorded public data and simulates trades. It places no orders and needs no account.
#
#   coverage  slots and validity per UTC day and the 80% day rule. Counts only, safe while recording continues.
#   preflight runs the fair-value and row pipeline and prints counts only (no prices, gaps, p_opt, outcomes).
#             Both also accept the pilot's data, to check the format; `run` accepts live snapshots only.
#   run       the one-shot test: T1 and T2 and the pre-registered reported figures. Needs settlements and the trade
#             tape (pull_after_stage3.py). On real data it refuses to run before the recording end, refuses pilot or
#             test snapshots, and refuses to overwrite an earlier result.
#
# The fair-value fit is stage 2's (analysis/analyze_stage2.py, imported, not copied): a cubic in total variance on
# out-of-the-money Deribit mids. Stdlib only, Python 3.9+.
import os, sys, json, gzip, glob, math, random, bisect, argparse, hashlib, collections, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_stage2 as a2  # noqa: E402

UTC = dt.timezone.utc
# ---- fixed by the pre-registration ----
START_UTC = "2026-11-20T00:00:00+00:00"
END_UTC = "2026-12-18T00:00:00+00:00"       # 28 full UTC days
STEP = 300
SLOTS_PER_DAY = 288
NEED_FRAC = 0.80                           # a day counts with >= 80% of its 288 slots valid for both coins
NEED_DAYS = 21
NEED_TRADES = 200                          # T1 KILL below this
NEED_FILLS = 200                           # T2 KILL below this
MAX_GAP_S, MAX_MOVE_PCT = 5.0, 0.10        # validity, per coin
MID_LO, MID_HI = 0.06, 0.94
MIN_LO, MIN_HI = 2.0, 60.0                 # minutes to close
TAU = 0.01                                 # entry threshold
KILL_EDGE = 0.01                           # T1 KILL if hedged upper bound < 1 cent
H_CAP = {"BTC": 50.0, "ETH": 2.5}          # difference step cap; h = min(cap, 0.1 F sigma sqrt(tau))
H_FRAC = 0.1
SYNC_FRAC = 0.1                            # row-sync flag: |index_after - index_before| > 0.1 F sigma sqrt(tau).
                                           # Deviation 1: a reported split only, never a row filter (it reads the
                                           # index after the Kalshi quote; docs/stage3/REVIEW_code.md finding 1)
STALE_FRAC = 0.25                          # stale-quote split: index moved < 0.25 F sigma sqrt(tau) over 60 s before
FEE_RATE = 0.07
BOOT, SEED = 2000, 20261120
CALIB_MIN = 5.0                            # calibration on each market's last row >= 5 minutes before close
DAILY_SUFFIX = "17"
COINS = ("BTC", "ETH")
TOL = 1e-9


# =====================================================================================================
# Small helpers
# =====================================================================================================
def fee(q):
    """0.07 q (1 - q) rounded up to the next $0.0001 (pre-registration, 'Taker fee')."""
    return math.ceil(FEE_RATE * q * (1.0 - q) * 10000 - 1e-7) / 10000


def fee_cent(q):
    return math.ceil(FEE_RATE * q * (1.0 - q) * 100 - 1e-7) / 100


num, iso_ts = a2.num, a2.iso_ts


def utc_day(t):
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d")


def fmt(t):
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


def is_hourly(ev):
    return bool(ev) and not ev.endswith(DAILY_SUFFIX)


def npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


# ---- Student t quantile (stdlib only) ----
def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e-300
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-14:
            break
    return h


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return 1 - p if t > 0 else p


def t_quantile(p, df):
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# =====================================================================================================
# Fair value (stage 2's fit, with the stage 3 forward and step)
# =====================================================================================================
def variance_fn(fits, t_close, t_now, F_index):
    """Returns (F, W) with W(k) the total variance to t_close at log-moneyness k = ln(K/F), or None.
    Close at or before the first fitted expiry: F = index_before, W = w_1(k) * tau_T / tau_1 (pre-registration,
    'No look-ahead'). Otherwise stage 2's interpolation in calendar time at fixed k."""
    tauT = (t_close - t_now) / a2.YEAR_S
    if tauT <= 0 or not fits:
        return None
    if tauT <= fits[0]["tau"] + 1e-12:
        if not F_index:
            return None
        f1 = fits[0]
        return F_index, (lambda k: a2.cubic(f1["co"], k) * tauT / f1["tau"])
    for x, y in zip(fits, fits[1:]):
        if x["tau"] <= tauT <= y["tau"]:
            u = (tauT - x["tau"]) / (y["tau"] - x["tau"])
            F = x["F"] + u * (y["F"] - x["F"])
            return F, (lambda k: a2.cubic(x["co"], k) + u * (a2.cubic(y["co"], k) - a2.cubic(x["co"], k)))
    return None


def p_above(coin, fits, K, t_close, t_now, F_index):
    """P(index > K at t_close) = (C(K - h) - C(K + h)) / 2h with h = min(cap, 0.1 F sigma sqrt(tau)).
    Returns (p, F, sd_atm, w_K) or None. sd_atm = sqrt(W(0)) is the at-the-money total sd to the close."""
    v = variance_fn(fits, t_close, t_now, F_index)
    if v is None:
        return None
    F, W = v
    w0 = W(0.0)
    if not w0 > 0:
        return None
    sd = math.sqrt(w0)
    h = min(H_CAP[coin], H_FRAC * F * sd)
    lo, hi = K - h, K + h
    if lo <= 0 or h <= 0:
        return None
    wl, wh, wk = W(math.log(lo / F)), W(math.log(hi / F)), W(math.log(K / F))
    if wl <= 0 or wh <= 0 or wk <= 0:
        return None
    p = (a2.black(F, lo, wl) - a2.black(F, hi, wh)) / (2 * h)
    if not (0.0 <= p <= 1.0):
        return None
    return p, F, sd, wk


def digital_delta(S, K, w):
    """d/dS of the lognormal digital N(d2), d2 = (ln(S/K) - w/2) / sqrt(w)."""
    if w <= 0 or S <= 0:
        return 0.0
    s = math.sqrt(w)
    return npdf((math.log(S / K) - 0.5 * w) / s) / (S * s)


# =====================================================================================================
# Snapshots, slots, validity, coverage
# =====================================================================================================
def idx(r):
    return (((r or {}).get("body") or {}).get("result") or {}).get("index_price")


def coin_valid(s, coin):
    c = (s.get("coins") or {}).get(coin) or {}
    ch, kd = c.get("chain") or {}, c.get("kalshi") or {}
    if not ch.get("options") or not kd.get("markets") or not kd.get("complete", True):
        return False
    if ch.get("t1") is None or kd.get("t1") is None:
        return False
    i0, i1 = idx(c.get("index_before")), idx(c.get("index_after"))
    if not i0 or not i1:
        return False
    return abs(kd["t1"] - ch["t1"]) <= MAX_GAP_S and abs(i1 - i0) / i0 * 100 < MAX_MOVE_PCT


def slot_of(s):
    tgt = (s.get("source") or {}).get("slot_target")
    t = iso_ts(tgt) if tgt else iso_ts(s["utc"])
    return int(round((t - 150) / STEP))


def slot_t(i):
    return i * STEP + 150


def read_snapshot(p):
    try:
        with gzip.open(p, "rt") as f:
            return json.load(f)
    except Exception:
        return None


def load_snapshots(data):
    """Snapshots from <data>/<YYYY-MM-DD>/*.json.gz, the first one in each slot (stage 2's rule)."""
    out, bad, dup = {}, 0, 0
    for p in sorted(glob.glob(os.path.join(data, "*", "*.json.gz"))):
        s = read_snapshot(p)
        if s is None or s.get("stage") != 3:
            bad += 1
            continue
        i = slot_of(s)
        if i in out:
            dup += 1
            if iso_ts(s["utc"]) >= iso_ts(out[i]["utc"]):
                continue
        out[i] = s
    return out, bad, dup


def load_polls(data):
    """{coin: sorted [(target_ts, t0, price)]} from <data>/index_1m/*.csv; failed polls are left out."""
    polls = {c: [] for c in COINS}
    for p in sorted(glob.glob(os.path.join(data, "index_1m", "*.csv"))):
        with open(p) as f:
            for ln in f:
                x = ln.rstrip("\n").split(",")
                if len(x) < 5 or x[0] == "target_utc" or not x[4]:
                    continue
                if x[1] in polls:
                    polls[x[1]].append((iso_ts(x[0]), float(x[2]), float(x[4])))
    for c in polls:
        polls[c] = sorted(set(polls[c]))
    return polls


def coverage(snaps, start, end):
    """Per UTC day in [start, end): valid-both slots out of 288, and whether the day counts."""
    days = collections.OrderedDict()
    t = start
    while t < end:
        days[utc_day(t)] = {"slots": 0, "recorded": 0, "valid_btc": 0, "valid_eth": 0, "valid_both": 0}
        t += 86400
    for i, s in snaps.items():
        t = slot_t(i)
        if not (start <= t < end):
            continue
        d = days[utc_day(t)]
        d["recorded"] += 1
        vb, ve = coin_valid(s, "BTC"), coin_valid(s, "ETH")
        d["valid_btc"] += vb; d["valid_eth"] += ve; d["valid_both"] += vb and ve
    for d in days.values():
        d["slots"] = SLOTS_PER_DAY
        d["counts"] = d["valid_both"] >= NEED_FRAC * SLOTS_PER_DAY
    return days


# =====================================================================================================
# Rows
# =====================================================================================================
def snapshot_rows(s, i, coin):
    """Candidate rows of one valid coin in one snapshot, plus counts of rows dropped and why."""
    c = s["coins"][coin]
    ch, kd = c["chain"], c["kalshi"]
    ib, ia = c["index_before"], c["index_after"]
    F_idx, F_after = idx(ib), idx(ia)
    t_now = ib["t1"]                       # latest p_opt input; chain and index_before both end before Kalshi starts
    fits = a2.fit_chain(ch["options"], t_now)
    rows, drop = [], collections.Counter()
    books = s.get("books") or {}
    for m in kd["markets"]:
        ev = m.get("event_ticker") or ""
        if not is_hourly(ev) or not m.get("close_time"):
            continue
        st = m.get("strike_type")
        K = num(m.get("floor_strike")) if st == "greater" else num(m.get("cap_strike")) if st == "less" else None
        if not K:
            drop["not a single-strike market"] += 1
            continue
        bid, ask = num(m.get("yes_bid_dollars")), num(m.get("yes_ask_dollars"))
        if bid is None or ask is None or not (0 < bid < ask < 1):
            continue
        mid = 0.5 * (bid + ask)
        close = iso_ts(m["close_time"])
        mins = (close - kd["t1"]) / 60
        if not (MID_LO - TOL <= mid <= MID_HI + TOL) or not (MIN_LO <= mins <= MIN_HI):
            continue
        fv = p_above(coin, fits, K, close, t_now, F_idx)
        if fv is None:
            drop["no fair value"] += 1
            continue
        pa, F, sd, wk = fv
        sync_ok = abs(F_after - F_idx) <= SYNC_FRAC * F * sd   # deviation 1: flagged, not dropped
        if not sync_ok:
            drop["row-sync flag (kept; deviation 1)"] += 1
        p = pa if st == "greater" else 1 - pa
        book = (books.get(m["ticker"]) or {}).get("book")
        rows.append({"coin": coin, "event": ev, "ticker": m["ticker"], "K": K, "above": st == "greater", "close": close,
                     "slot": i, "t": slot_t(i), "t_q0": kd["t0"], "t_q": kd["t1"], "t_now": t_now, "mins": mins,
                     "bid": bid, "ask": ask, "mid": mid, "p": p, "F": F, "sd": sd, "wk": wk,
                     "i_before": F_idx, "i_after": F_after, "sync_ok": sync_ok, "t_after": ia["t1"], "t_before0": ib["t0"],
                     "day": utc_day(close), "snap_day": utc_day(slot_t(i)),
                     "yes_depth_book": a2.book_depth(book, "yes", bid), "no_depth_book": a2.book_depth(book, "no", 1 - ask),
                     "yes_depth_top": num(m.get("yes_bid_size_fp")), "no_depth_top": num(m.get("yes_ask_size_fp"))})
    return rows, drop, len(fits)


def all_rows(snaps, days):
    """Rows from valid coins, in snapshots on counted days, of events closing on counted days."""
    rows, drop, fits = [], collections.Counter(), collections.Counter()
    counted = {d for d, v in days.items() if v["counts"]}
    for i in sorted(snaps):
        s = snaps[i]
        if utc_day(slot_t(i)) not in counted:
            continue
        for coin in COINS:
            if not coin_valid(s, coin):
                continue
            rs, dr, nf = snapshot_rows(s, i, coin)
            fits[(coin, nf)] += 1
            drop.update(dr)
            for r in rs:
                if r["day"] in counted:
                    rows.append(r)
                else:
                    drop["close on a day that does not count"] += 1
    rows.sort(key=lambda r: (r["t"], r["coin"], r["ticker"]))
    return rows, drop, fits


# =====================================================================================================
# T1: taker trades, realised and hedged P&L
# =====================================================================================================
def gaps(r, feefn=fee):
    gy = r["p"] - r["ask"] - feefn(r["ask"])
    gn = (1 - r["p"]) - (1 - r["bid"]) - feefn(1 - r["bid"])
    return gy, gn


def taker_trades(rows, results, tau=TAU, feefn=fee):
    """First row per market with g > tau buys 1 contract of the better side at the touch (ties go to YES)."""
    seen, out, unsettled = set(), [], 0
    for r in rows:
        if r["ticker"] in seen:
            continue
        gy, gn = gaps(r, feefn)
        g = max(gy, gn)
        if not g > tau:
            continue
        seen.add(r["ticker"])
        res = results.get(r["ticker"])
        if res not in ("yes", "no"):
            unsettled += 1
            continue
        side = "yes" if gy >= gn else "no"
        price = r["ask"] if side == "yes" else 1 - r["bid"]
        pnl = (1.0 if res == side else 0.0) - price - feefn(price)
        out.append(dict(r, side=side, price=price, g=g, pnl=pnl, result=res))
    return out, unsettled


def hedge_path(tr, polls, snaps_index=None):
    """Points (t, S) from index_after at the trade's snapshot to the close.
    1-minute grid: polls whose request started after index_after's request ended, with target <= close.
    snaps_index: alternative 5-minute grid [(t_after, index_after)] of later snapshots of the coin, then the close poll."""
    pts = [(tr["t_after"], tr["i_after"])]
    grid = polls.get(tr["coin"]) or []
    lo = bisect.bisect_left(grid, (tr["t_after"] - 120,))          # polls are sorted by target; t0 is a few s after it
    window = []
    for tgt, t0, S in grid[lo:]:
        if tgt > tr["close"] + 1e-6:
            break
        if t0 >= tr["t_after"]:
            window.append((tgt, S))
    if snaps_index is None:
        pts += window
    else:
        si = snaps_index.get(tr["coin"], [])
        j = bisect.bisect_right(si, (tr["t_after"], float("inf")))
        for t, S in si[j:]:
            if t >= tr["close"]:
                break
            pts.append((t, S))
        pts += [(tgt, S) for tgt, S in window if abs(tgt - tr["close"]) < 1e-6]
    return pts


def hedge_term(tr, pts):
    """sum_i Delta_i (S_{i+1} - S_i); Delta_i = +-dN(d2)/dS at point i with the trade snapshot's variance scaled to
    the time left; + for YES on an 'above' market, sign flipped for NO (and for a 'below' market)."""
    if len(pts) < 2:
        return 0.0, len(pts)
    T, K = tr["close"], tr["K"]
    tau0 = T - tr["t_now"]
    sign = (1 if tr["side"] == "yes" else -1) * (1 if tr["above"] else -1)
    h = 0.0
    for (t, S), (_, S2) in zip(pts, pts[1:]):
        w = tr["wk"] * max(T - t, 0.0) / tau0
        h += sign * digital_delta(S, K, w) * (S2 - S)
    return h, len(pts)


def add_hedges(trades, polls, snaps_index=None, key="hedged"):
    for tr in trades:
        h, n = hedge_term(tr, hedge_path(tr, polls, snaps_index))
        tr[key] = tr["pnl"] - h
        tr[key + "_points"] = n
    return trades


def cluster(items, f_num, f_den=lambda x: 1.0):
    """Ratio estimate and day-clustered se (pre-registration, 'Tests and gates'), one-sided 95% t bounds."""
    g = collections.defaultdict(lambda: [0.0, 0.0])
    for x in items:
        g[x["day"]][0] += f_num(x); g[x["day"]][1] += f_den(x)
    D = len(g)
    N = sum(v[1] for v in g.values())
    if D < 2 or N <= 0:
        return {"est": (sum(v[0] for v in g.values()) / N) if N else None, "se": None, "lo": None, "hi": None, "days": D, "n": N}
    mu = sum(v[0] for v in g.values()) / N
    se = math.sqrt(D / (D - 1) * sum((x - mu * n) ** 2 for x, n in g.values())) / N
    t = t_quantile(0.95, D - 1)
    return {"est": mu, "se": se, "lo": mu - t * se, "hi": mu + t * se, "t": t, "days": D, "n": N}


def t1_verdict(hedged, unhedged, n_trades, complete):
    if not complete:
        return "INCOMPLETE"
    if n_trades < NEED_TRADES or (hedged["hi"] is not None and hedged["hi"] < KILL_EDGE):
        return "KILL"
    if hedged["lo"] is not None and hedged["lo"] > 0 and unhedged["est"] is not None and unhedged["est"] > 0:
        return "PASS"
    return "INCONCLUSIVE"


def t2_verdict(st, n_fills, complete):
    if not complete:
        return "INCOMPLETE"
    if n_fills < NEED_FILLS or (st["hi"] is not None and st["hi"] < 0):
        return "KILL"
    if st["lo"] is not None and st["lo"] > 0:
        return "PASS"
    return "INCONCLUSIVE"


def boot_days(items, f_num, rng, f_den=lambda x: 1.0, block=1, reps=BOOT):
    """Percentile bootstrap of the ratio estimate over days (block=1) or blocks of `block` consecutive days."""
    g = collections.defaultdict(lambda: [0.0, 0.0])
    for x in items:
        g[x["day"]][0] += f_num(x); g[x["day"]][1] += f_den(x)
    keys = sorted(g)
    if not keys:
        return {"est": None, "lo": None, "hi": None, "units": 0}
    if block > 1:
        d0 = dt.date.fromisoformat(keys[0])
        b = collections.defaultdict(lambda: [0.0, 0.0])
        for k in keys:
            j = (dt.date.fromisoformat(k) - d0).days // block
            b[j][0] += g[k][0]; b[j][1] += g[k][1]
        g, keys = b, sorted(b)
    nums, dens = [g[k][0] for k in keys], [g[k][1] for k in keys]
    est = sum(nums) / sum(dens) if sum(dens) else None
    bs = []
    for _ in range(reps):
        a = c = 0.0
        for _ in keys:
            j = rng.randrange(len(keys)); a += nums[j]; c += dens[j]
        if c:
            bs.append(a / c)
    bs.sort()
    return {"est": est, "lo": bs[int(0.025 * len(bs))] if bs else None,
            "hi": bs[min(len(bs) - 1, int(0.975 * len(bs)))] if bs else None, "units": len(keys)}


# =====================================================================================================
# T2: stage 2's S3 maker rule on hourly rows
# =====================================================================================================
def order_windows(snaps):
    """Order life per (slot, coin): from that coin's Kalshi list end to the next recorded snapshot's list start for the
    same coin (valid or not), at most 300 s (stage 2's rule, NOTES.md item 17)."""
    slots = sorted(snaps)
    win = {}
    for a, b in zip(slots, slots[1:] + [None]):
        for coin in COINS:
            kd = ((snaps[a].get("coins") or {}).get(coin) or {}).get("kalshi") or {}
            if kd.get("t1") is None:
                continue
            t0, t1 = kd["t1"], kd["t1"] + STEP
            if b is not None:
                nk = ((snaps[b].get("coins") or {}).get(coin) or {}).get("kalshi") or {}
                if nk.get("t0") is not None:
                    t1 = min(t1, nk["t0"])
            win[(a, coin)] = (t0, t1)
    return win


def maker_fills(rows, results, tapes, win):
    fills, orders, missing = [], 0, 0
    for r in rows:
        res, tape = results.get(r["ticker"]), tapes.get(r["ticker"])
        t0, t1 = win[(r["slot"], r["coin"])]
        for side, price, fair, dbook, dtop in (("yes", r["bid"], r["p"], r["yes_depth_book"], r["yes_depth_top"]),
                                               ("no", 1 - r["ask"], 1 - r["p"], r["no_depth_book"], r["no_depth_top"])):
            if not fair > price:
                continue
            orders += 1
            if tape is None or res not in ("yes", "no"):
                missing += 1
                continue
            depth = max(x for x in (dbook, dtop, 0.0) if x is not None)
            if a2.tape_volume(tape, side, price, t0, t1) > depth:
                fills.append(dict(r, side=side, price=price, pnl=(1.0 if res == side else 0.0) - price))
    return fills, orders, missing


# =====================================================================================================
# Reported figures
# =====================================================================================================
def stale_split(trades, polls):
    """Index move over the 60 s before the snapshot: latest 1-minute poll at or before index_before's start - 60 s."""
    quiet, moved, unknown = [], [], 0
    for tr in trades:
        grid = polls.get(tr["coin"]) or []
        ref = [S for tgt, t0, S in grid if t0 <= tr["t_before0"] - 60]
        if not ref:
            unknown += 1
            continue
        (quiet if abs(tr["i_before"] - ref[-1]) < STALE_FRAC * tr["F"] * tr["sd"] else moved).append(tr)
    return quiet, moved, unknown


def calibration(rows, results):
    last = {}
    for r in rows:
        if r["mins"] >= CALIB_MIN and results.get(r["ticker"]) in ("yes", "no"):
            if r["ticker"] not in last or r["t"] > last[r["ticker"]]["t"]:
                last[r["ticker"]] = r
    xs = list(last.values())
    clip = lambda p: min(max(p, 1e-6), 1 - 1e-6)
    y = lambda r: 1.0 if results[r["ticker"]] == "yes" else 0.0
    out = {"markets": len(xs)}
    for who, key in (("p_opt", "p"), ("mid", "mid")):
        out[f"brier_{who}"] = cluster(xs, lambda r: (r[key] - y(r)) ** 2)
        out[f"logloss_{who}"] = cluster(xs, lambda r: -(y(r) * math.log(clip(r[key])) + (1 - y(r)) * math.log(1 - clip(r[key]))))
    return out


# =====================================================================================================
# Driver
# =====================================================================================================
def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def is_synthetic(data, snaps):
    return os.path.exists(os.path.join(data, "SYNTHETIC_FIXTURE")) and bool(snaps) and all(s.get("synthetic") is True for s in snaps.values())


def load_results(path):
    with open(path) as f:
        d = json.load(f)
    return {k: (v.get("result") if isinstance(v, dict) else v) for k, v in d["markets"].items()}


def analyse(snaps, polls, results, tapes, start, end):
    """Everything the pre-registration asks for, as one dict. Pure: no files, no clock."""
    days = coverage(snaps, start, end)
    n_days = sum(1 for d in days.values() if d["counts"])
    complete = n_days >= NEED_DAYS
    rows, drop, fits = all_rows(snaps, days)
    snaps_index = {c: sorted((s["coins"][c]["index_after"]["t1"], idx(s["coins"][c]["index_after"]))
                             for s in snaps.values() if (s.get("coins") or {}).get(c) and idx(s["coins"][c].get("index_after")))
                   for c in COINS}
    rng = random.Random(SEED)
    out = {"counted_days": n_days, "need_days": NEED_DAYS, "complete": complete, "rows": len(rows), "rows_dropped": dict(drop),
           "rows_by_coin": dict(collections.Counter(r["coin"] for r in rows)),
           "days": {k: dict(v) for k, v in days.items()}}

    def t1_block(trs):
        add_hedges(trs, polls)
        hed, unh = cluster(trs, lambda x: x["hedged"]), cluster(trs, lambda x: x["pnl"])
        return {"trades": len(trs), "hedged": hed, "unhedged": unh}

    trades, unsettled = taker_trades(rows, results)
    T1 = t1_block(trades)
    T1["unsettled_trades_dropped"] = unsettled
    T1["verdict"] = t1_verdict(T1["hedged"], T1["unhedged"], len(trades), complete)
    out["T1"] = T1

    win = order_windows(snaps)
    fills, orders, missing = maker_fills(rows, results, tapes, win)
    T2 = cluster(fills, lambda f: f["pnl"], lambda f: f["price"])
    T2.update({"fills": len(fills), "orders": orders, "orders_without_tape_or_result": missing})
    T2["verdict"] = t2_verdict(T2, len(fills), complete)
    out["T2"] = T2

    ref = collections.OrderedDict()
    for c in COINS:
        ref[f"T1_coin_{c}"] = t1_block([dict(t) for t in trades if t["coin"] == c])
    for lab, lo, hi in (("2-15", 2, 15), ("15-30", 15, 30), ("30-60", 30, 60.0001)):
        ref[f"T1_minutes_{lab}"] = t1_block([dict(t) for t in trades if lo <= t["mins"] < hi])
    for tau in (0.0, 0.02):
        ref[f"T1_tau_{tau:.2f}"] = t1_block(taker_trades(rows, results, tau=tau)[0])
    # deviation 1: the pre-registered row-sync rule, applied as a row filter, for reference only (biased; see REVIEW_code.md)
    ref["T1_with_preregistered_row_sync_rule"] = t1_block(taker_trades([r for r in rows if r["sync_ok"]], results)[0])
    ref["T1_fee_rounded_up_to_cent"] = t1_block(taker_trades(rows, results, feefn=fee_cent)[0])
    ref["ex_ante_gap_on_traded_rows"] = cluster(trades, lambda x: x["g"])
    ref["T1_hedged_bootstrap_days"] = boot_days(trades, lambda x: x["hedged"], rng)
    ref["T1_hedged_bootstrap_7day_blocks"] = boot_days(trades, lambda x: x["hedged"], rng, block=7)
    quiet, moved, unknown = stale_split(trades, polls)
    ref["T1_stale_split_quiet"] = {"trades": len(quiet), "hedged": cluster(quiet, lambda x: x["hedged"])}
    ref["T1_stale_split_after_move"] = {"trades": len(moved), "hedged": cluster(moved, lambda x: x["hedged"]), "unknown": unknown}
    five = [dict(t) for t in trades]
    add_hedges(five, polls, snaps_index, key="hedged5")
    ref["T1_hedge_5min_snapshots"] = {"trades": len(five), "hedged": cluster(five, lambda x: x["hedged5"])}
    ref["calibration_last_row_ge_5min"] = calibration(rows, results)
    out["reference"] = ref
    out["fits_by_coin_and_expiries"] = {f"{c} {n}": v for (c, n), v in sorted(fits.items())}
    return out, rows, trades, fills


def fmt_ci(x, cents=True, plain=False):
    if not x or x.get("est") is None:
        return "n/a"
    s = (lambda v: f"{v:.4f}") if plain else (lambda v: f"{v * 100:+.2f}c") if cents else (lambda v: f"{v * 100:+.2f}%")
    lo = "" if x.get("lo") is None else f" [{s(x['lo'])}, {s(x['hi'])}]"
    if "units" in x:
        return f"{s(x['est'])}{lo} (bootstrap units {x['units']})"
    return f"{s(x['est'])}{lo} (days {x['days']}, n {x['n']:.0f})"


def text_report(out, synthetic, sha):
    L = [f"stage 3 analysis  {'SYNTHETIC FIXTURE' if synthetic else 'REAL DATA'}  script sha256 {sha}",
         f"counted days {out['counted_days']} (need {NEED_DAYS}): {'complete' if out['complete'] else 'INCOMPLETE'}",
         f"rows {out['rows']} {out['rows_by_coin']}; dropped {out['rows_dropped']}", "",
         "== THE TEST (one-sided 95% t bounds, clustered by the close's UTC day)"]
    t1 = out["T1"]
    L.append(f"T1 hedged P&L per contract   {fmt_ci(t1['hedged'])}")
    L.append(f"   unhedged P&L per contract {fmt_ci(t1['unhedged'])}   trades {t1['trades']}  -> {t1['verdict']}")
    t2 = out["T2"]
    L.append(f"T2 maker return per dollar   {fmt_ci(t2, cents=False)}  fills {t2['fills']} of {t2['orders']} orders  -> {t2['verdict']}")
    L += ["   (only T1 can justify a next stage)", "", "== reported, never used to rescue a verdict"]
    for k, v in out["reference"].items():
        if k.startswith("calibration"):
            L.append(f"{k}: markets {v['markets']}")
            L += [f"   {kk}: {fmt_ci(vv, plain=True)}" for kk, vv in v.items() if kk != "markets"]
        elif "hedged" in v and isinstance(v["hedged"], dict):
            L.append(f"{k}: trades {v['trades']}, hedged {fmt_ci(v['hedged'])}" + (f", unhedged {fmt_ci(v['unhedged'])}" if "unhedged" in v else ""))
        else:
            L.append(f"{k}: {fmt_ci(v)}")
    return "\n".join(L) + "\n"


def coverage_text(days):
    L = ["day         recorded  valid BTC  valid ETH  valid both  counts"]
    for k, d in days.items():
        L.append(f"{k}  {d['recorded']:8d}  {d['valid_btc']:9d}  {d['valid_eth']:9d}  {d['valid_both']:10d}  {'yes' if d['counts'] else 'no'}")
    n = sum(1 for d in days.values() if d["counts"])
    L.append(f"counted days {n} (need {NEED_DAYS})")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description="BOB stage 3 analysis")
    ap.add_argument("mode", choices=("coverage", "preflight", "run"))
    ap.add_argument("--data", required=True, help="the data/ folder of a stage3-data checkout")
    ap.add_argument("--settlements"); ap.add_argument("--trades"); ap.add_argument("--out")
    ap.add_argument("--now", help="override the clock (synthetic fixtures only)")
    ap.add_argument("--start", default=START_UTC); ap.add_argument("--end", default=END_UTC)
    a = ap.parse_args(argv)
    snaps, bad, dup = load_snapshots(a.data)
    if not snaps:
        raise SystemExit("no readable stage 3 snapshots")
    synthetic = is_synthetic(a.data, snaps)
    if not synthetic:
        if a.mode == "run" and (a.start, a.end) != (START_UTC, END_UTC):
            raise SystemExit("refusing: on real data the window is fixed at the pre-registered dates")
        modes = collections.Counter(s.get("mode") for s in snaps.values())
        if a.mode == "run" and set(modes) != {"live"}:
            raise SystemExit(f"refusing: real data must be live snapshots only, found {dict(modes)} (pilot data never enters the test)")
    start, end = iso_ts(a.start), iso_ts(a.end)
    now = dt.datetime.now(UTC).timestamp()
    if a.now:
        if not synthetic:
            raise SystemExit("--now is only allowed on synthetic fixtures")
        now = iso_ts(a.now)
    head = [f"stage 3  {'SYNTHETIC FIXTURE' if synthetic else 'REAL DATA'}  snapshots {len(snaps)} (unreadable {bad}, duplicates {dup})"]
    days = coverage(snaps, start, end)
    if a.mode == "coverage":
        print("\n".join(head + coverage_text(days)))
        return 0
    if a.mode == "preflight":
        # counts only, on every day in the window (the 80% day rule is not applied here)
        rows, drop, fits = all_rows(snaps, {k: dict(v, counts=True) for k, v in days.items()})
        polls = load_polls(a.data)
        print("\n".join(head + coverage_text(days) + [
            f"rows (counts only, all days): {dict(collections.Counter(r['coin'] for r in rows))}; dropped {dict(drop)}",
            f"rows by minutes to close: {dict(collections.Counter('2-15' if r['mins'] < 15 else '15-30' if r['mins'] < 30 else '30-60' for r in rows))}",
            f"valid coin-snapshots by fitted expiries: {dict((f'{c} {n}', v) for (c, n), v in sorted(fits.items()))}",
            f"rows with a recorded order book: {sum(1 for r in rows if r['yes_depth_book'] is not None)} of {len(rows)}",
            f"1-minute polls: {dict((c, len(v)) for c, v in polls.items())}"]))
        return 0
    if not (a.settlements and a.trades and a.out):
        ap.error("run needs --settlements, --trades and --out")
    if not synthetic and now < end:
        raise SystemExit(f"refusing: recording ends {fmt(end)}Z; the test may not run before then")
    res_path = os.path.join(a.out, "stage3_results.json")
    if not synthetic and os.path.exists(res_path):
        raise SystemExit(f"refusing: {res_path} exists. The pre-registered test runs once.")
    results = load_results(a.settlements)
    polls = load_polls(a.data)
    tickers = set()
    for s in snaps.values():
        for c in COINS:
            for m in (((s.get("coins") or {}).get(c) or {}).get("kalshi") or {}).get("markets") or []:
                if is_hourly(m.get("event_ticker")):
                    tickers.add(m["ticker"])
    tapes, truncated = {}, 0
    for t in tickers:
        tp, tr = a2.load_tape(a.trades, t)
        if tp is not None:
            tapes[t] = tp
        truncated += bool(tr)
    out, rows, trades, fills = analyse(snaps, polls, results, tapes, start, end)
    sha, sha2 = file_sha(__file__), file_sha(a2.__file__)
    out.update({"synthetic": synthetic, "run_utc": fmt(now), "script_sha256": sha, "stage2_fitter_sha256": sha2,
                "truncated_tapes": truncated})
    text = text_report(out, synthetic, sha)
    os.makedirs(a.out, exist_ok=True)
    with open(res_path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(a.out, "stage3_results.txt"), "w") as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
