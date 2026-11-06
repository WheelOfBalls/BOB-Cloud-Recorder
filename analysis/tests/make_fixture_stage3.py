#!/usr/bin/env python3
# Synthetic stage 3 recordings for the tests of analyze_stage3.py. No real data is read or written.
#
# World: BTC and ETH follow driftless GBM (in price) on a 30 s grid with flat volatility. Deribit chains are Black-76
# prices at that volatility with the forward = spot, so p_opt should reproduce the truth N(d2). Each hourly event
# lists 11 'greater' strikes around spot for the hour before its close. Kalshi's mid is the truth shifted by
# +-delta (sign drawn per event), rounded to the cent, quoted +-1 cent. Settlement: the index at the close > strike.
# The trade tape gives maker fills at the touch at random. Snapshots carry "synthetic": true.
import os, sys, json, gzip, math, random, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import analyze_stage2 as a2  # noqa: E402

UTC = dt.timezone.utc
STEP, PHASE = 300, 150
YEAR = 365.0 * 86400
COIN = {"BTC": {"series": "KXBTCD", "S0": 90000.0, "vol": 0.50, "step": 100.0, "idx": "btc_usd"},
        "ETH": {"series": "KXETHD", "S0": 3000.0, "vol": 0.60, "step": 5.0, "idx": "eth_usd"}}
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def event_ticker(series, close):
    et = dt.datetime.fromtimestamp(close, UTC) - dt.timedelta(hours=5)       # November: ET = UTC - 5
    return f"{series}-{et:%y}{MON[et.month - 1]}{et:%d}{et:%H}"


def instrument(coin, expiry, K, cp):
    e = dt.datetime.fromtimestamp(expiry, UTC)
    return f"{coin}-{e.day}{MON[e.month - 1]}{e:%y}-{int(round(K))}-{cp}"


class World:
    def __init__(self, start, days, delta=0.0, seed=1, bad_day=None, bad_frac=0.0, invalid_frac=0.02, fill_prob=0.3,
                 half_spread=0.01, extra_days=0, chain_vol_mult=1.0, adverse=False):
        self.rng = random.Random(seed)
        self.start, self.days, self.delta = start, days, delta
        self.end = start + (days + extra_days) * 86400
        self.chain_vol_mult, self.adverse = chain_vol_mult, adverse
        self.bad_day, self.bad_frac, self.invalid_frac, self.fill_prob, self.hs = bad_day, bad_frac, invalid_frac, fill_prob, half_spread
        self.t0 = start - 3600                                  # path starts an hour early so the first event can list
        n = int((self.end + 3600 - self.t0) // 30) + 2
        self.path = {}
        for c, p in COIN.items():
            s, xs, sd = p["S0"], [], p["vol"] * math.sqrt(30 / YEAR)
            for _ in range(n):
                xs.append(s)
                s *= math.exp(sd * self.rng.gauss(0, 1) - 0.5 * sd * sd)
            self.path[c] = xs
        self.sign, self.strikes = {}, {}

    def S(self, c, t):
        return self.path[c][int(round((t - self.t0) / 30))]

    def truth(self, c, K, t, close):
        w = COIN[c]["vol"] ** 2 * (close - t) / YEAR
        S = self.S(c, t)
        return ncdf((math.log(S / K) - 0.5 * w) / math.sqrt(w))

    def chain(self, c, t):
        F, vol = self.S(c, t), COIN[c]["vol"] * self.chain_vol_mult      # a wrong fair value when mult != 1
        day0 = dt.datetime.fromtimestamp(t, UTC).replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
        exps = [e for e in (day0, day0 + 86400, day0 + 2 * 86400) if e > t][:2]
        out = []
        for e in exps:
            w = vol * vol * (e - t) / YEAR
            for z in (-1.5, -0.8, -0.3, 0.3, 0.8, 1.5):
                K = float(round(F * math.exp(z * math.sqrt(w))))   # listed strikes are whole numbers
                call = K >= F
                usd = a2.black(F, K, w, call)
                mid = usd / F
                out.append({"instrument_name": instrument(c, e, K, "C" if call else "P"), "bid_price": mid * 0.9995,
                            "ask_price": mid * 1.0005, "mark_price": mid, "mark_iv": vol * 100, "underlying_price": F,
                            "open_interest": 1, "creation_timestamp": int(t * 1000)})
        return out

    def markets(self, c, t):
        """Markets of the next hourly event (listed for the hour before its close) and, before 22:00, the 5pm one."""
        close = (int(t // 3600) + 1) * 3600
        p = COIN[c]
        ev = event_ticker(p["series"], close)
        out = []
        if ev not in self.strikes:
            s0 = self.S(c, close - 3600)
            self.strikes[ev] = [round(s0 / p["step"]) * p["step"] + p["step"] * j for j in range(-5, 6)]
            self.sign[ev] = self.rng.choice((-1, 1))
        if not ev.endswith("17"):
            for K in self.strikes[ev]:
                q = self.truth(c, K, t, close) + self.sign[ev] * self.delta
                mid = min(max(round(q * 100), 1), 99) / 100
                bid, ask = round(mid - self.hs, 2), round(mid + self.hs, 2)
                bid, ask = max(bid, 0.0), min(ask, 1.0)          # one-sided at the edges, as Kalshi reports it
                out.append({"ticker": f"{ev}-T{K:g}", "event_ticker": ev, "status": "active", "close_time": iso(close),
                            "floor_strike": K, "cap_strike": None, "strike_type": "greater",
                            "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}",
                            "yes_bid_size_fp": "10.00", "yes_ask_size_fp": "10.00"})
        d17 = dt.datetime.fromtimestamp(t, UTC).replace(hour=22, minute=0, second=0, microsecond=0).timestamp()
        if t < d17:
            ev17 = event_ticker(p["series"], d17)
            out.append({"ticker": f"{ev17}-T1", "event_ticker": ev17, "close_time": iso(d17), "floor_strike": 1.0,
                        "strike_type": "greater", "yes_bid_dollars": "0.4500", "yes_ask_dollars": "0.4700"})
        return out

    def snapshot(self, i):
        t = i * STEP + PHASE
        day = int((t - self.start) // 86400)
        bad = (day == self.bad_day and self.rng.random() < self.bad_frac) or self.rng.random() < self.invalid_frac
        s = {"utc": iso(t), "stage": 3, "version": 1, "mode": "synthetic", "synthetic": True,
             "source": {"host": "fixture", "slot_target": iso(t)}, "coins": {}, "books": {}, "errors": []}
        tt = t
        for c, p in COIN.items():
            ch = {"t0": tt, "t1": tt + 0.2, "ok": True, "options": self.chain(c, t)}
            ib = {"t0": tt + 0.2, "t1": tt + 0.3, "body": {"result": {"index_price": self.S(c, t)}}}
            kd_t0 = tt + 0.3
            kd_t1 = kd_t0 + (6.0 if bad else 0.2)
            kd = {"t0": kd_t0, "t1": kd_t1, "pages": 1, "complete": True, "markets": self.markets(c, t), "series": p["series"]}
            ia = {"t0": kd_t1, "t1": kd_t1 + 0.1, "body": {"result": {"index_price": self.S(c, t)}}}
            s["coins"][c] = {"chain": ch, "index_before": ib, "kalshi": kd, "index_after": ia}
            tt = kd_t1 + 0.1
        s["t_end"] = tt
        return s

    def build(self):
        first = int(math.ceil((self.start - PHASE) / STEP))
        last = int((self.end - PHASE - 1) // STEP)
        snaps = {i: self.snapshot(i) for i in range(first, last + 1)}
        polls = {c: [] for c in COIN}
        t = self.start
        while t <= self.end + 3600:
            for c in COIN:
                if self.rng.random() > 0.01:
                    polls[c].append((t, t + 0.05, self.S(c, t)))
            t += 60
        results, tapes = {}, {}
        for c in COIN:
            for ev, ks in self.strikes.items():
                if not ev.startswith(COIN[c]["series"] + "-"):
                    continue
                close = None
                for s in snaps.values():
                    for m in s["coins"][c]["kalshi"]["markets"]:
                        if m["event_ticker"] == ev:
                            close = a2.iso_ts(m["close_time"]); break
                    if close:
                        break
                if close is None:
                    continue
                for K in ks:
                    results[f"{ev}-T{K:g}"] = "yes" if self.S(c, close) > K else "no"
        # maker tape: at random, a taker hits each quoted bid (both sides) with more than the top-of-book size
        for i, s in snaps.items():
            for c in COIN:
                kd = s["coins"][c]["kalshi"]
                for m in kd["markets"]:
                    if m["event_ticker"].endswith("17"):
                        continue
                    b, a = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
                    if not (0 < b < a < 1):
                        continue
                    tp = tapes.setdefault(m["ticker"], [])
                    res = results.get(m["ticker"])
                    # adverse: a resting YES bid is hit only when YES loses, a NO bid only when NO loses
                    if self.rng.random() < self.fill_prob and (not self.adverse or res == "no"):
                        tp.append((kd["t1"] + 30, b, 15.0, "no"))
                    if self.rng.random() < self.fill_prob and (not self.adverse or res == "yes"):
                        tp.append((kd["t1"] + 40, a, 15.0, "yes"))
        for v in tapes.values():
            v.sort()
        return snaps, polls, results, tapes


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat()


def write(world, out):
    """Writes the fixture as a recorder data folder plus settlements.json and trades/ as pull_after_stage3.py does."""
    snaps, polls, results, tapes = world.build()
    data = os.path.join(out, "data")
    os.makedirs(os.path.join(data, "index_1m"), exist_ok=True)
    open(os.path.join(data, "SYNTHETIC_FIXTURE"), "w").close()
    for s in snaps.values():
        t = dt.datetime.fromisoformat(s["utc"])
        d = os.path.join(data, t.strftime("%Y-%m-%d"))
        os.makedirs(d, exist_ok=True)
        with gzip.open(os.path.join(d, t.strftime("%H%M%S") + ".json.gz"), "wt") as f:
            json.dump(s, f)
    rows = collections_rows(polls)
    for day, lines in rows.items():
        with open(os.path.join(data, "index_1m", day + ".csv"), "w") as f:
            f.write("target_utc,coin,t0,t1,index_price,us_out,error\n" + "\n".join(lines) + "\n")
    with open(os.path.join(out, "settlements.json"), "w") as f:
        json.dump({"markets": {k: {"result": v} for k, v in results.items()}}, f)
    os.makedirs(os.path.join(out, "trades"), exist_ok=True)
    for k, v in tapes.items():
        with gzip.open(os.path.join(out, "trades", k + ".json.gz"), "wt") as f:
            json.dump({"truncated": False, "trades": [{"created_time": iso(t), "yes_price_dollars": f"{p:.4f}", "count_fp": f"{n:.2f}",
                                                       "taker_side": side} for t, p, n, side in v]}, f)
    return data


def collections_rows(polls):
    out = {}
    for c, xs in polls.items():
        for tgt, t0, S in xs:
            out.setdefault(dt.datetime.fromtimestamp(tgt, UTC).strftime("%Y-%m-%d"), []).append(
                f"{iso(tgt)},{c},{t0:.3f},{t0 + 0.1:.3f},{S},,")
    return out
