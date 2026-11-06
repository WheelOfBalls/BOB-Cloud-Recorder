#!/usr/bin/env python3
# Synthetic stage 2 data in the recorder's exact file format, for testing analyze_stage2.py without touching any
# real recorded data or outcomes. Everything here is made up: a simulated BTC path, a Deribit chain priced from a
# known smile, Kalshi quotes set from the known probability (optionally biased), a made-up tape and made-up results.
#
# The true smile is w(k, tau) = tau * (A + B k + C k^2). It is a cubic in k at every expiry and proportional to tau,
# so the pre-registered fit, interpolation and scaling are exact on it; any error in p_opt is a bug.
import os, sys, json, gzip, math, random, argparse, datetime as dt

UTC = dt.timezone.utc
A, B, C = 0.25, -0.08, 0.30          # 50% ATM vol, mild skew
PHASE = 182
YEAR_S = 365.0 * 86400


def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def true_w(k, tau):
    return tau * (A + B * k + C * k * k)


def black(F, K, w, call=True):
    s = math.sqrt(w); d1 = (math.log(F / K) + 0.5 * w) / s
    c = F * ncdf(d1) - K * ncdf(d1 - s)
    return c if call else c - F + K


def true_p(F, K, tau, h=0.5):
    """P(S_T > K) under the true smile, by a fine central difference (independent of the analysis code)."""
    c = lambda x: black(F, x, true_w(math.log(x / F), tau))
    return (c(K - h) - c(K + h)) / (2 * h)


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat()


def ev_ticker(series, close):
    d = dt.datetime.fromtimestamp(close, UTC) - dt.timedelta(hours=5)   # 22:00 UTC = 17:00 ET in November
    return f"{series}-{d.strftime('%y%b%d').upper()}{d.hour:02d}"


def make(root, start="2026-11-05T15:23:02+00:00", days=12.0, bias=0.0, seed=1, local_outages=(), cloud_outages=(),
         local_invalid_every=0, cloud_start_h=4.0, half_spread=0.01):
    """local_outages / cloud_outages: (start_hour, length_hours) offsets from `start` with no snapshot at all."""
    rng = random.Random(seed)
    t_start = dt.datetime.fromisoformat(start).timestamp()
    t_end = t_start + days * 86400
    n = int((t_end - t_start) // 300)
    # BTC path, 5-minute steps, 50% vol, no drift
    S, path = 76000.0, []
    for i in range(n + 400):
        path.append(S); S *= math.exp(0.5 * math.sqrt(300 / YEAR_S) * rng.gauss(0, 1) - 0.5 * 0.25 * 300 / YEAR_S)
    def spot(t):
        return path[max(0, min(len(path) - 1, int((t - t_start) // 300)))]
    # 5pm closes: 22:00 UTC each day from the start day
    d0 = dt.datetime.fromtimestamp(t_start, UTC).replace(hour=22, minute=0, second=0, microsecond=0).timestamp()
    closes = [d0 + 86400 * j for j in range(int(days) + 3)]
    strikes = {}
    for c in closes:                                             # strikes fixed around the spot 30 h before close
        s0 = spot(max(t_start, c - 30 * 3600)); base = round(s0 / 250) * 250
        strikes[c] = [base + 250 * j - 0.01 for j in range(-8, 9)]
    os.makedirs(root, exist_ok=True)
    loc, cld, trd = os.path.join(root, "local"), os.path.join(root, "cloud"), os.path.join(root, "trades")
    for d in (loc, cld, trd):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "SYNTHETIC_FIXTURE"), "w").write("synthetic test data, not real\n")
    open(os.path.join(root, "end_utc.txt"), "w").write(iso(t_end) + "\n")
    tapes, truth = {}, {}

    def in_out(h, outs):
        return any(a <= h < a + L for a, L in outs)

    for i in range(n):
        slot_t = t_start + 300 * i
        h_off = (slot_t - t_start) / 3600
        F = spot(slot_t)
        # Deribit chain: daily 08:00 expiries for the next 3 days
        opts = []
        e0 = dt.datetime.fromtimestamp(slot_t, UTC).replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
        exps = [e for e in (e0 + 86400 * j for j in range(0, 4)) if e > slot_t + 600][:3]
        for e in exps:
            tau = (e - slot_t - 1.0) / YEAR_S          # priced at the chain finish time (snapshot t + 1 s)
            dname = dt.datetime.fromtimestamp(e, UTC).strftime("%d%b%y").upper().lstrip("0")
            for K in [round(F / 1000) * 1000 + 1000 * j for j in range(-5, 6)]:
                for cp in ("C", "P"):
                    px = black(F, K, true_w(math.log(K / F), tau), cp == "C") / F
                    if px < 0.0003:
                        continue
                    opts.append({"instrument_name": f"BTC-{dname}-{K}-{cp}", "bid_price": px - 0.0002, "ask_price": px + 0.0002,
                                 "mark_price": px, "mark_iv": 50.0, "underlying_price": F, "open_interest": 1.0,
                                 "creation_timestamp": int((slot_t + 0.5) * 1000)})
        opts.append({"instrument_name": f"BTC-{dname}-200000-C", "bid_price": None, "ask_price": 0.0001, "mark_price": 0.0,
                     "mark_iv": 50.0, "underlying_price": F, "open_interest": 0.0, "creation_timestamp": 0})   # one-sided: dropped
        mk, mkb, books = [], [], {}
        for c in closes:
            if not (c - 34 * 3600 <= slot_t < c):
                continue
            ev = ev_ticker("KXBTCD", c)
            tauc = (c - slot_t - 1.0) / YEAR_S
            for K in strikes[c]:
                p = true_p(F, K, tauc)
                m = min(max(p - bias, 0.02), 0.98)
                bid = max(round(m * 100) / 100 - half_spread, 0.0); ask = min(bid + 2 * half_spread, 1.0)
                bid, ask = round(bid, 2), round(ask, 2)
                tk = f"{ev}-T{K:.2f}"
                truth[(slot_t, tk)] = p
                mk.append({"ticker": tk, "event_ticker": ev, "close_time": iso(c).replace("+00:00", "Z"), "floor_strike": K,
                           "cap_strike": None, "strike_type": "greater", "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}",
                           "no_bid_dollars": f"{1 - ask:.4f}", "no_ask_dollars": f"{1 - bid:.4f}", "yes_bid_size_fp": "40.00",
                           "yes_ask_size_fp": "60.00", "last_price_dollars": f"{bid:.4f}", "volume_fp": "100.00", "open_interest_fp": "10.00"})
                if 0.03 <= bid and 0 < ask <= 0.97:
                    books[tk] = {"t0": slot_t + 3, "t1": slot_t + 3.2, "book": {"yes_dollars": [[f"{bid - 0.01:.4f}", "500.00"], [f"{bid:.4f}", "40.00"]],
                                                                               "no_dollars": [[f"{0.99 - ask:.4f}", "500.00"], [f"{1 - ask:.4f}", "60.00"]]}}
                # made-up tape: takers hitting both sides of the touch during the next 5 minutes
                tape = tapes.setdefault(tk, [])
                for _ in range(rng.randint(0, 3)):
                    tape.append({"trade_id": f"{tk}-{i}-{len(tape)}", "created_time": iso(slot_t + rng.uniform(5, 290)).replace("+00:00", "Z"),
                                 "yes_price_dollars": f"{bid:.4f}", "count_fp": f"{rng.choice([5, 30, 45, 80]):.2f}", "taker_side": "no"})
                for _ in range(rng.randint(0, 3)):
                    tape.append({"trade_id": f"{tk}-{i}-{len(tape)}", "created_time": iso(slot_t + rng.uniform(5, 290)).replace("+00:00", "Z"),
                                 "yes_price_dollars": f"{ask:.4f}", "count_fp": f"{rng.choice([5, 30, 65, 90]):.2f}", "taker_side": "yes"})
            # a noon event and an hourly market that must be ignored
            mk.append({"ticker": ev[:-2] + "12-T1", "event_ticker": ev[:-2] + "12", "close_time": iso(c - 36000).replace("+00:00", "Z"),
                       "floor_strike": F, "cap_strike": None, "strike_type": "greater", "yes_bid_dollars": "0.4000", "yes_ask_dollars": "0.4200"})
            evb = ev_ticker("KXBTC", c)
            for K in strikes[c][::4]:
                mkb.append({"ticker": f"{evb}-B{K + 125.01:.0f}", "event_ticker": evb, "close_time": iso(c).replace("+00:00", "Z"),
                            "floor_strike": K, "cap_strike": K + 250, "strike_type": "between", "yes_bid_dollars": "0.0500", "yes_ask_dollars": "0.0800"})
        for src, d, outs, jit in (("local", loc, local_outages, 0.0), ("cloud", cld, cloud_outages, 0.4)):
            if in_out(h_off, outs) or (src == "cloud" and h_off < cloud_start_h):
                continue
            t = slot_t + jit
            gap_bad = src == "local" and local_invalid_every and i % local_invalid_every == 0
            snap = {"utc": iso(t), "version": 1,
                    "index_before": {"t0": t, "t1": t + 0.2, "body": {"result": {"index_price": F}}},
                    "index_after": {"t0": t + 2, "t1": t + 2.2, "body": {"result": {"index_price": F * (1.0001)}}},
                    "deribit": {"t0": t + 0.3, "t1": t + 1.0, "options": opts},
                    "kxbtcd": {"t0": t + 1.1, "t1": t + (8.0 if gap_bad else 1.6), "markets": mk},
                    "kxbtc": {"t0": t + 2.3, "t1": t + 2.6, "markets": mkb}, "books": books, "errors": []}
            if src == "cloud":
                snap["source"] = {"host": "github-actions", "run_id": "1", "run_attempt": "1", "event": "schedule", "slot_target": iso(slot_t)}
            day = dt.datetime.fromtimestamp(t, UTC)
            os.makedirs(os.path.join(d, day.strftime("%Y-%m-%d")), exist_ok=True)
            with gzip.open(os.path.join(d, day.strftime("%Y-%m-%d"), day.strftime("%H%M%S") + ".json.gz"), "wt") as f:
                json.dump(snap, f, separators=(",", ":"))
    for tk, tr in tapes.items():
        with gzip.open(os.path.join(trd, tk + ".json.gz"), "wt") as f:
            json.dump({"truncated": False, "trades": tr}, f)
    res = {}
    for c in closes:
        ev = ev_ticker("KXBTCD", c)
        for K in strikes[c]:
            res[f"{ev}-T{K:.2f}"] = {"event_ticker": ev, "result": "yes" if spot(c) > K else "no"}
    json.dump({"synthetic": True, "markets": res}, open(os.path.join(root, "settlements.json"), "w"))
    json.dump({f"{t}|{k}": v for (t, k), v in truth.items()}, open(os.path.join(root, "truth.json"), "w"))
    return root


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--days", type=float, default=12.0); ap.add_argument("--bias", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    make(a.root, days=a.days, bias=a.bias, seed=a.seed, local_outages=((30, 8),), local_invalid_every=7)
    print("written", a.root)
