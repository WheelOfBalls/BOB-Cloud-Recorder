#!/usr/bin/env python3
# Stage 3 snapshot: Kalshi KXBTCD + KXETHD (hourly and daily) and the Deribit BTC and ETH option chains, as
# docs/stage3/PREREGISTRATION_stage3.md ("Recording") fixes. Forked from stage2/record_snapshot.py; stage 2's
# recorder is not touched. Public read-only GETs, TLS verified, no account, no orders. A failed request is
# logged as failed and never filled in. Outcomes and trades are never pulled here.
#
# Order within a snapshot, per coin (pre-registration, "Order within a snapshot"):
#   Deribit chain -> index_before -> Kalshi market list (top of book, all pages) -> index_after
# then, after both coins, the order books for hourly markets quoted inside 3 to 97 cents, then the KXBTC/KXETH
# bracket lists (reference only). Every request stores its own t0 (start) and t1 (end).
import os, sys, json, gzip, time, faulthandler, datetime as dt, urllib.request, urllib.parse

UTC = dt.timezone.utc
K = "https://api.elections.kalshi.com/trade-api/v2"
DB = "https://www.deribit.com/api/v2/public"
VERSION = 1
COINS = (("BTC", "KXBTCD", "KXBTC", "btc_usd"), ("ETH", "KXETHD", "KXETH", "eth_usd"))
DAILY_SUFFIX = "17"             # 5pm ET daily events; every other KXBTCD/KXETHD event is an hourly one
CHAIN_DAYS = 3                  # Deribit expiries within 3 days
EXPIRY_HOUR = 8                 # Deribit expiries are at 08:00 UTC
BOOK_LO, BOOK_HI = 0.03, 0.97   # order books for hourly markets with a two-sided quote inside 3 to 97 cents
BOOK_SPACING = 0.15             # seconds between order-book requests, as stage 2
BOOK_BUDGET_S = 110             # stop fetching books after this long (the watchdog fires at 170 s)
MAX_PAGES = 10
WATCHDOG_S = 170


def is_hourly(event_ticker):
    return bool(event_ticker) and not event_ticker.endswith(DAILY_SUFFIX)


class Fetcher:
    """Plain urllib GETs that record t0/t1 and collect errors. Replaced by a fake in the tests."""
    def __init__(self):
        self.errors = []

    def get(self, url, tries=2):
        t0 = time.time()
        for i in range(tries):
            try:
                r = urllib.request.Request(url, headers={"User-Agent": "research-probe/0.1", "Accept": "application/json"})
                with urllib.request.urlopen(r, timeout=20) as f:
                    d = json.loads(f.read().decode())
                return {"t0": t0, "t1": time.time(), "body": d}
            except Exception as e:
                if i == tries - 1:
                    self.errors.append(f"{url.split('?')[0][-48:]}: {str(e)[:120]}")
                else:
                    time.sleep(1.5)
        return {"t0": t0, "t1": time.time(), "body": None}


MARKET_FIELDS = ("ticker", "event_ticker", "status", "open_time", "close_time", "floor_strike", "cap_strike", "strike_type",
                 "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars", "yes_bid_size_fp", "yes_ask_size_fp",
                 "last_price_dollars", "volume_fp", "open_interest_fp")
OPTION_FIELDS = ("instrument_name", "bid_price", "ask_price", "mark_price", "mark_iv", "underlying_price", "open_interest",
                 "creation_timestamp")


def trim(d, fields):
    return {k: d.get(k) for k in fields}


def expiry_ts(instrument):
    """BTC-8NOV26-88000-P -> 08:00 UTC on 8 Nov 2026 (timestamp)."""
    e = dt.datetime.strptime(instrument.split("-")[1], "%d%b%y")
    return e.replace(hour=EXPIRY_HOUR, tzinfo=UTC).timestamp()


def near(instrument, now_ts):
    try:
        return expiry_ts(instrument) - now_ts <= CHAIN_DAYS * 86400
    except (ValueError, IndexError):
        return False


def index_read(f, name):
    return f.get(f"{DB}/get_index_price?index_name={name}")


def market_list(f, series):
    """All open markets of a series, following the cursor. t0 = first request's start, t1 = last request's end."""
    markets, pages, cursor, t0, t1 = [], 0, None, None, None
    while pages < MAX_PAGES:
        q = {"series_ticker": series, "status": "open", "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        r = f.get(K + "/markets?" + urllib.parse.urlencode(q))
        pages += 1
        t0 = r["t0"] if t0 is None else t0
        t1 = r["t1"]
        if r["body"] is None:
            return {"t0": t0, "t1": t1, "pages": pages, "complete": False, "markets": [trim(m, MARKET_FIELDS) for m in markets]}
        markets += r["body"].get("markets") or []
        cursor = r["body"].get("cursor")
        if not cursor:
            break
    return {"t0": t0, "t1": t1, "pages": pages, "complete": not cursor, "markets": [trim(m, MARKET_FIELDS) for m in markets]}


def wants_book(m):
    if not is_hourly(m.get("event_ticker")):
        return False
    try:
        b, a = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
    except (TypeError, ValueError):
        return False
    return BOOK_LO <= b < a <= BOOK_HI


def snapshot(f, now=None, sleep=time.sleep, clock=time.time, env=None):
    """Takes one snapshot with fetcher f. Returns the snapshot dict (not yet written)."""
    env = os.environ if env is None else env
    now = now or dt.datetime.now(UTC)
    snap = {"utc": now.isoformat(), "stage": 3, "version": VERSION, "mode": env.get("BOB_MODE", "manual"),
            "source": {k: env.get(v) for k, v in (("host", "BOB_SOURCE"), ("run_id", "GITHUB_RUN_ID"),
                                                  ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("event", "GITHUB_EVENT_NAME"),
                                                  ("slot_target", "BOB_SLOT_TARGET"))},
            "coins": {}}
    for coin, series, _, idx in COINS:
        chain = f.get(f"{DB}/get_book_summary_by_currency?currency={coin}&kind=option")
        res = (chain["body"] or {}).get("result") or []
        c = {"chain": {"t0": chain["t0"], "t1": chain["t1"], "ok": chain["body"] is not None,
                       "options": [trim(o, OPTION_FIELDS) for o in res if near(o.get("instrument_name", ""), now.timestamp())]}}
        c["index_before"] = index_read(f, idx)
        c["kalshi"] = dict(market_list(f, series), series=series)
        c["index_after"] = index_read(f, idx)
        snap["coins"][coin] = c
    books, started, truncated = {}, clock(), False
    for coin, *_ in COINS:
        for m in snap["coins"][coin]["kalshi"]["markets"]:
            if not wants_book(m):
                continue
            if clock() - started > BOOK_BUDGET_S:
                truncated = True
                break
            r = f.get(f"{K}/markets/{m['ticker']}/orderbook")
            if r["body"] is not None:
                b = r["body"].get("orderbook_fp")
                books[m["ticker"]] = {"t0": r["t0"], "t1": r["t1"], "book": b if b is not None else r["body"].get("orderbook")}
            sleep(BOOK_SPACING)
    snap["books"] = books
    snap["books_truncated"] = truncated
    snap["brackets"] = {}
    for coin, _, bracket, _ in COINS:
        snap["brackets"][bracket] = market_list(f, bracket)
    snap["errors"] = list(f.errors)
    snap["t_end"] = clock()
    return snap


def idx_price(r):
    return (((r or {}).get("body") or {}).get("result") or {}).get("index_price")


def validity(snap, coin, max_gap=5.0, max_move_pct=0.10):
    """Per-coin validity as the pre-registration fixes it (stage 2's rule): chain and Kalshi top-of-book requests
    finished within 5 s of each other, and the index moved under 0.10% across the Kalshi pull."""
    c = (snap.get("coins") or {}).get(coin) or {}
    ch, kd = c.get("chain") or {}, c.get("kalshi") or {}
    if not ch.get("options") or not kd.get("markets") or not kd.get("complete", True):
        return False, None
    gap = abs(kd["t1"] - ch["t1"])
    i0, i1 = idx_price(c.get("index_before")), idx_price(c.get("index_after"))
    if not i0 or not i1:
        return False, gap
    return gap <= max_gap and abs(i1 - i0) / i0 * 100 < max_move_pct, gap


def write(snap, data):
    t = dt.datetime.fromisoformat(snap["utc"])
    out = os.path.join(data, t.strftime("%Y-%m-%d"))
    os.makedirs(out, exist_ok=True)
    fn = os.path.join(out, t.strftime("%H%M%S") + ".json.gz")
    with gzip.open(fn + ".tmp", "wt") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    os.replace(fn + ".tmp", fn)
    vb, gb = validity(snap, "BTC")
    ve, ge = validity(snap, "ETH")
    cs = snap["coins"]
    row = [snap["utc"], len(cs["BTC"]["chain"]["options"]), len(cs["ETH"]["chain"]["options"]),
           len(cs["BTC"]["kalshi"]["markets"]), len(cs["ETH"]["kalshi"]["markets"]), len(snap["books"]),
           int(snap["books_truncated"]), "" if gb is None else f"{gb:.2f}", "" if ge is None else f"{ge:.2f}", int(vb), int(ve),
           round(snap["t_end"] - t.timestamp(), 1), os.path.getsize(fn), len(snap["errors"]),
           " | ".join(snap["errors"])[:300].replace(",", ";").replace("\n", " ")]
    log = os.path.join(data, "run_log.csv")
    new = not os.path.exists(log)
    with open(log, "a") as fh:
        if new:
            fh.write("utc,btc_options,eth_options,kxbtcd_markets,kxethd_markets,books,books_truncated,btc_gap_s,eth_gap_s,"
                     "btc_valid,eth_valid,duration_s,bytes,n_errors,errors\n")
        fh.write(",".join(str(x) for x in row) + "\n")
    return fn


def main():
    data = os.environ.get("BOB_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data, exist_ok=True)
    hang = open(os.path.join(data, "hang_log.txt"), "a")       # a run killed by the watchdog leaves a stack here
    faulthandler.dump_traceback_later(WATCHDOG_S, file=hang, exit=True)
    try:
        write(snapshot(Fetcher()), data)
    except Exception as e:
        with open(os.path.join(data, "crash_log.txt"), "a") as fh:
            fh.write(f"{dt.datetime.now(UTC).isoformat()} {type(e).__name__}: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
