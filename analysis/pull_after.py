#!/usr/bin/env python3
# After recording ends: pull settlement results and the public trade tape that analyze_stage2.py needs.
# Read-only, unauthenticated GETs against Kalshi's public API. No account, no orders.
#
#   python3 -I analysis/pull_after.py --local <local data/> --cloud <cloud data/> --out <folder>
#
# Writes <out>/settlements.json and <out>/trades/<ticker>.json.gz (same trade format as stage 1's pull_tape.py).
# Refuses to run before the recording end time, so no outcome is seen while recording is still going.
import os, sys, json, gzip, glob, time, argparse, datetime as dt, urllib.request, urllib.parse, urllib.error

K = "https://api.elections.kalshi.com/trade-api/v2"
UTC = dt.timezone.utc
_last = [0.0]
END_UTC = "2026-11-19T15:25:00+00:00"   # stage2/end_utc.txt; --end cannot move it


def get(path, params=None, min_gap=0.22):
    """Same retry policy as stage 1's scripts/kapi.py."""
    url = K + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(8):
        w = min_gap - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-probe/0.1", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (i + 1)); continue
            if e.code in (500, 502, 503, 504):
                time.sleep(2); continue
            return {"_error": e.code, "_body": e.read().decode()[:300]}
        except Exception as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                return {"_error": f"tls: {e}"}
            time.sleep(2 * (i + 1))
    return {"_error": "retries"}


SETTLE_FIELDS = ("event_ticker", "status", "result", "close_time", "expiration_value", "floor_strike", "cap_strike", "strike_type")


def settled(m):
    return (m or {}).get("result") in ("yes", "no")


def event_markets(path, ev, get_fn=None):
    """All markets of one event from /markets or /historical/markets, following the cursor. (list, error or None)"""
    get_fn = get_fn or get
    out, cur = [], None
    while True:
        q = {"event_ticker": ev, "limit": 1000}
        if cur:
            q["cursor"] = cur
        r = get_fn(path, q)
        if "_error" in r:
            return out, r["_error"]
        out += r.get("markets", []) or []
        cur = r.get("cursor")
        if not cur or not r.get("markets"):
            return out, None


def settlements(events, get_fn=None):
    """{ticker: fields} for every market of every event, plus a list of historical-endpoint errors.
    Kalshi moves markets settled before a moving cutoff out of GET /markets into GET /historical/markets
    (docs.kalshi.com, "Historical data"), so an event whose markets are missing or unsettled on the live endpoint
    is looked up there too. Same logic as settlements() in the stage 3 pull. A live-endpoint error stops the pull;
    a historical-endpoint error is recorded and those markets stay without a result (the analysis then treats the
    event as unsettled, and it does not count)."""
    markets, hist_errors = {}, []
    for ev in sorted(events):
        live, err = event_markets("/markets", ev, get_fn)
        if err is not None:
            sys.exit(f"stopping at {ev}: {err}")
        for m in live:
            markets[m["ticker"]] = {k: m.get(k) for k in SETTLE_FIELDS}
        if live and all(settled(m) for m in live):
            continue
        hist, err = event_markets("/historical/markets", ev, get_fn)
        if err is not None:
            hist_errors.append(f"{ev}: {err}")
        for m in hist:
            if not settled(markets.get(m["ticker"])):
                markets[m["ticker"]] = dict({k: m.get(k) for k in SETTLE_FIELDS}, source="historical")
    return markets, hist_errors


def seen_markets(dirs):
    """Event tickers and KXBTCD 5pm market tickers that ever had a two-sided quote in a snapshot."""
    events, tickers = set(), set()
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*", "*.json.gz"))):
            try:
                with gzip.open(p, "rt") as f:
                    s = json.load(f)
            except Exception:
                continue
            for key in ("kxbtcd", "kxbtc"):
                for m in (s.get(key) or {}).get("markets") or []:
                    ev = m.get("event_ticker") or ""
                    if not ev.endswith("17"):
                        continue
                    events.add(ev)
                    try:
                        b, a = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
                    except ValueError:
                        continue
                    if key == "kxbtcd" and 0 < b < a < 1:
                        tickers.add(m["ticker"])
    return events, tickers


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--local"); ap.add_argument("--cloud"); ap.add_argument("--out", required=True)
    ap.add_argument("--end", default=os.path.join(here, "..", "stage2", "end_utc.txt"))
    a = ap.parse_args()
    end = dt.datetime.fromisoformat(open(a.end).read().strip())
    if end != dt.datetime.fromisoformat(END_UTC):
        raise SystemExit(f"refusing: {a.end} gives {end.isoformat()}, but the recording end is fixed at {END_UTC}")
    if dt.datetime.now(UTC) < end:
        raise SystemExit(f"refusing: recording ends {end.isoformat()}; outcomes are pulled only after that")
    dirs = [d for d in (a.local, a.cloud) if d]
    events, tickers = seen_markets(dirs)
    print(len(events), "events,", len(tickers), "KXBTCD 5pm markets with a two-sided quote", flush=True)
    os.makedirs(os.path.join(a.out, "trades"), exist_ok=True)

    markets, hist_errors = settlements(events)
    json.dump({"pulled_utc": dt.datetime.now(UTC).isoformat(), "markets": markets, "historical_errors": hist_errors},
              open(os.path.join(a.out, "settlements.json"), "w"), indent=1)
    print("settlements", len(markets), "of which from /historical/markets", sum(1 for m in markets.values() if m.get("source") == "historical"),
          "; historical-endpoint errors", len(hist_errors), flush=True)

    for i, t in enumerate(sorted(tickers)):
        fn = os.path.join(a.out, "trades", t + ".json.gz")
        if os.path.exists(fn):
            continue
        seen, trades, trunc = set(), [], False
        for path in ("/historical/trades", "/markets/trades"):   # the historical cutoff moves daily, so pull both
            cur = None
            for _ in range(400):
                q = {"ticker": t, "limit": 1000}
                if cur:
                    q["cursor"] = cur
                r = get(path, q)
                if "_error" in r:
                    sys.exit(f"stopping at {t}: {r['_error']}")
                for x in r.get("trades", []):
                    if x["trade_id"] not in seen:
                        seen.add(x["trade_id"])
                        trades.append({k: x.get(k) for k in ("trade_id", "created_time", "yes_price_dollars", "count_fp", "taker_side")})
                cur = r.get("cursor")
                if not cur or not r.get("trades"):
                    cur = None; break
            trunc = trunc or bool(cur)
        with gzip.open(fn + ".tmp", "wt") as f:
            json.dump({"truncated": trunc, "trades": trades}, f)
        os.replace(fn + ".tmp", fn)
        if i % 50 == 0:
            print(i, t, len(trades), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
