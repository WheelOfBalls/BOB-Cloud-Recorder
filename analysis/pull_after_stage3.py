#!/usr/bin/env python3
# After the stage 3 recording ends: pull settlement results and the public trade tape that analyze_stage3.py needs.
# Read-only, unauthenticated GETs against Kalshi's public API (stage 2's pull_after.py helpers). No account, no orders.
#
#   python3 -I analysis/pull_after_stage3.py --data <stage3-data checkout>/data --out <folder>
#
# Writes <out>/settlements.json (every market of every hourly KXBTCD/KXETHD event seen in a live snapshot) and
# <out>/trades/<ticker>.json.gz for each hourly market that ever had a two-sided quote within 60 minutes of its close.
# Refuses to run before the recording end, and on pilot or test snapshots.
import os, sys, json, gzip, glob, argparse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pull_after as pa  # noqa: E402  (get() with stage 1's retry policy)
import analyze_stage3 as a3  # noqa: E402

UTC = dt.timezone.utc


def seen(data):
    events, tickers, modes = set(), set(), set()
    for p in sorted(glob.glob(os.path.join(data, "*", "*.json.gz"))):
        s = a3.read_snapshot(p)
        if s is None or s.get("stage") != 3:
            continue
        modes.add(s.get("mode"))
        for c in a3.COINS:
            kd = ((s.get("coins") or {}).get(c) or {}).get("kalshi") or {}
            for m in kd.get("markets") or []:
                ev = m.get("event_ticker") or ""
                if not a3.is_hourly(ev) or not m.get("close_time"):
                    continue
                events.add(ev)
                b, a = a3.num(m.get("yes_bid_dollars")), a3.num(m.get("yes_ask_dollars"))
                if b is not None and a is not None and 0 < b < a < 1 and kd.get("t1") and \
                        a3.iso_ts(m["close_time"]) - kd["t1"] <= 3600:
                    tickers.add(m["ticker"])
    return events, tickers, modes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    end = dt.datetime.fromisoformat(a3.END_UTC)
    if dt.datetime.now(UTC) < end:
        raise SystemExit(f"refusing: recording ends {a3.END_UTC}; outcomes are pulled only after that")
    events, tickers, modes = seen(a.data)
    if modes != {"live"}:
        raise SystemExit(f"refusing: expected live snapshots only, found {sorted(map(str, modes))}")
    print(len(events), "hourly events,", len(tickers), "markets with a two-sided quote in the last hour", flush=True)
    os.makedirs(os.path.join(a.out, "trades"), exist_ok=True)
    markets = {}
    for ev in sorted(events):
        cur = None
        while True:
            q = {"event_ticker": ev, "limit": 1000}
            if cur:
                q["cursor"] = cur
            r = pa.get("/markets", q)
            if "_error" in r:
                sys.exit(f"stopping at {ev}: {r['_error']}")
            for m in r.get("markets", []):
                markets[m["ticker"]] = {k: m.get(k) for k in ("event_ticker", "status", "result", "close_time", "expiration_value",
                                                               "floor_strike", "cap_strike", "strike_type")}
            cur = r.get("cursor")
            if not cur or not r.get("markets"):
                break
    with open(os.path.join(a.out, "settlements.json"), "w") as f:
        json.dump({"pulled_utc": dt.datetime.now(UTC).isoformat(), "markets": markets}, f, indent=1)
    print("settlements", len(markets), flush=True)
    for i, t in enumerate(sorted(tickers)):
        fn = os.path.join(a.out, "trades", t + ".json.gz")
        if os.path.exists(fn):
            continue
        ids, trades, trunc = set(), [], False
        for path in ("/historical/trades", "/markets/trades"):
            cur = None
            for _ in range(400):
                q = {"ticker": t, "limit": 1000}
                if cur:
                    q["cursor"] = cur
                r = pa.get(path, q)
                if "_error" in r:
                    sys.exit(f"stopping at {t}: {r['_error']}")
                for x in r.get("trades", []):
                    if x["trade_id"] not in ids:
                        ids.add(x["trade_id"])
                        trades.append({k: x.get(k) for k in ("trade_id", "created_time", "yes_price_dollars", "count_fp", "taker_side")})
                cur = r.get("cursor")
                if not cur or not r.get("trades"):
                    cur = None
                    break
            trunc = trunc or bool(cur)
        with gzip.open(fn + ".tmp", "wt") as f:
            json.dump({"truncated": trunc, "trades": trades}, f)
        os.replace(fn + ".tmp", fn)
        if i % 200 == 0:
            print(i, t, len(trades), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
