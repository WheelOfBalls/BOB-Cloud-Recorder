# One public-data snapshot of Kalshi KXBTCD/KXBTC and the Deribit BTC chain. Cloud copy, run every 5 minutes by cloud_loop.py
# in GitHub Actions. Identical to the Windows recorder except: BOB_DATA_DIR can move data/, and each snapshot carries a "source" block.
# Read-only GETs, TLS verified, no account, no orders. A failed request is logged as failed and never filled in.
import os, sys, json, gzip, time, faulthandler, datetime as dt, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.environ.get("BOB_DATA_DIR") or os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
# a run killed by the scheduler leaves nothing, so dump the stack first and leave a trace of each step
_hang = open(os.path.join(DATA, "hang_log.txt"), "a")
faulthandler.dump_traceback_later(170, file=_hang, exit=True)
def trace(step):
    with open(os.path.join(DATA, "trace.log"), "a") as f: print(dt.datetime.now(dt.timezone.utc).isoformat(), "pid", os.getpid(), step, file=f)
trace("start")
END_FILE = os.path.join(HERE, "end_utc.txt")
K = "https://api.elections.kalshi.com/trade-api/v2"; DB = "https://www.deribit.com/api/v2/public"
errors = []
def fetch(url, tries=2):
    t0 = time.time()
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "research-probe/0.1", "Accept": "application/json"})
            with urllib.request.urlopen(r, timeout=20) as f: d = json.loads(f.read().decode())
            return {"t0": t0, "t1": time.time(), "body": d}
        except Exception as e:
            err = f"{url.split('?')[0][-40:]}: {str(e)[:120]}"
            if i == tries - 1: errors.append(err)
            else: time.sleep(1.5)
    return {"t0": t0, "t1": time.time(), "body": None}
def kalshi(path, **q): return fetch(K + path + ("?" + urllib.parse.urlencode(q) if q else ""))
def index(): return fetch(DB + "/get_index_price?index_name=btc_usd")
def trim_market(m):
    return {k: m.get(k) for k in ("ticker", "event_ticker", "close_time", "floor_strike", "cap_strike", "strike_type", "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars", "yes_bid_size_fp", "yes_ask_size_fp", "last_price_dollars", "volume_fp", "open_interest_fp")}
def trim_option(o):
    return {k: o.get(k) for k in ("instrument_name", "bid_price", "ask_price", "mark_price", "mark_iv", "underlying_price", "open_interest", "creation_timestamp")}
def near(name, now):
    e = dt.datetime.strptime(name.split("-")[1], "%d%b%y").replace(tzinfo=dt.timezone.utc)
    return (e - now).days <= 10
def main():
    now = dt.datetime.now(dt.timezone.utc)
    if os.path.exists(END_FILE) and now >= dt.datetime.fromisoformat(open(END_FILE).read().strip()): return
    day = now.strftime("%Y-%m-%d"); out = os.path.join(DATA, day); os.makedirs(out, exist_ok=True)
    snap = {"utc": now.isoformat(), "version": 1, "source": {k: os.environ.get(v) for k, v in (("host", "BOB_SOURCE"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("event", "GITHUB_EVENT_NAME"), ("slot_target", "BOB_SLOT_TARGET"))}}
    trace("main"); snap["index_before"] = index()
    chain = fetch(DB + "/get_book_summary_by_currency?currency=BTC&kind=option")
    trace("chain done"); kd = kalshi("/markets", series_ticker="KXBTCD", status="open", limit=1000)
    snap["index_after"] = index()
    kb = kalshi("/markets", series_ticker="KXBTC", status="open", limit=1000)
    res = (chain["body"] or {}).get("result") or []
    snap["deribit"] = {"t0": chain["t0"], "t1": chain["t1"], "options": [trim_option(o) for o in res if near(o["instrument_name"], now)]}
    md = (kd["body"] or {}).get("markets") or []
    snap["kxbtcd"] = {"t0": kd["t0"], "t1": kd["t1"], "markets": [trim_market(m) for m in md]}
    snap["kxbtc"] = {"t0": kb["t0"], "t1": kb["t1"], "markets": [trim_market(m) for m in (kb["body"] or {}).get("markets") or []]}
    trace("markets done"); books = {}
    for m in md:
        if not m["event_ticker"].endswith("17"): continue
        b, a = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
        if 0.03 <= b and 0 < a <= 0.97:
            r = kalshi(f"/markets/{m['ticker']}/orderbook")
            if r["body"]: books[m["ticker"]] = {"t0": r["t0"], "t1": r["t1"], "book": r["body"].get("orderbook_fp")}
            time.sleep(0.15)
    trace("books done"); snap["books"] = books; snap["errors"] = errors
    fn = os.path.join(out, now.strftime("%H%M%S") + ".json.gz")
    with gzip.open(fn + ".tmp", "wt") as f: json.dump(snap, f, separators=(",", ":"))
    os.replace(fn + ".tmp", fn)
    gap = abs(kd["t1"] - chain["t1"])
    with open(os.path.join(DATA, "run_log.csv"), "a") as f:
        trace("written"); f.write(f"{now.isoformat()},{len(snap['deribit']['options'])},{len(md)},{len(snap['kxbtc']['markets'])},{len(books)},{gap:.2f},{round(time.time()-now.timestamp(),1)},{len(errors)},{' | '.join(errors)[:300].replace(',',';')}\n")
if __name__ == "__main__":
    try: main()
    except Exception as e:
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "crash_log.txt"), "a") as f: f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat()} {type(e).__name__}: {e}\n")
