# Stage 3 design check: which Kalshi crypto series and Deribit chains exist, and how often their events settle.
# Prints METADATA ONLY: tickers, titles, settlement frequency, open-event counts, close-time hours, strike counts and
# spacing. No price, quote, volume or outcome is printed or saved, so it cannot unblind stage 2.
# Public read-only GETs, no account. Run: python3 -I docs/stage3/discover_series.py
import json, sys, time, urllib.request, urllib.parse, collections, datetime as dt
K = "https://api.elections.kalshi.com/trade-api/v2"; DB = "https://www.deribit.com/api/v2/public"
CANDIDATES = ["KXBTCD", "KXBTC", "KXETHD", "KXETH", "KXBTCW", "KXETHW", "KXBTC15M", "KXETH15M", "KXSOLD", "KXXRPD",
              "KXBTCMAXW", "KXBTCMINW", "KXBTCY", "KXETHY"]
def get(url):
    r = urllib.request.Request(url, headers={"User-Agent": "research-probe/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as f: return json.loads(f.read().decode())
def safe(fn, *a):
    try: return fn(*a)
    except Exception as e: return {"error": str(e)[:120]}
report = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "kalshi": {}, "deribit": {}}
for s in CANDIDATES:
    meta = safe(get, f"{K}/series/{s}")
    ser = meta.get("series") if isinstance(meta, dict) else None
    row = {"exists": bool(ser)}
    if ser:
        row.update({k: ser.get(k) for k in ("title", "frequency", "fee_type", "fee_multiplier")})
        row["settlement_sources"] = [x.get("name") for x in (ser.get("settlement_sources") or [])]
        ev = safe(get, f"{K}/events?" + urllib.parse.urlencode({"series_ticker": s, "status": "open", "limit": 200}))
        events = ev.get("events") or [] if isinstance(ev, dict) else []
        row["open_events"] = len(events)
        hours = collections.Counter()
        for e in events:
            t = e.get("strike_date") or e.get("close_time")
            if t: hours[t[11:13] + "Z"] += 1
        row["close_hours_utc"] = dict(sorted(hours.items()))
        row["event_ticker_examples"] = [e.get("event_ticker") for e in events[:4]]
        # strike structure of up to 3 open events: counts and spacing only, every price field is discarded here
        st = []
        for e in events[:3]:
            m = safe(get, f"{K}/markets?" + urllib.parse.urlencode({"event_ticker": e.get("event_ticker"), "limit": 1000}))
            ms = m.get("markets") or [] if isinstance(m, dict) else []
            ks = sorted({float(x["floor_strike"]) for x in ms if x.get("floor_strike") is not None})
            gaps = sorted({round(b - a, 2) for a, b in zip(ks, ks[1:])})
            st.append({"event": e.get("event_ticker"), "markets": len(ms), "strike_types": sorted({str(x.get("strike_type")) for x in ms}),
                       "n_strikes": len(ks), "strike_gaps": gaps[:5]})
            time.sleep(0.3)
        row["strike_structure"] = st
    report["kalshi"][s] = row
    time.sleep(0.3)
for cur in ("BTC", "ETH"):
    d = safe(get, f"{DB}/get_instruments?currency={cur}&kind=option&expired=false")
    ins = d.get("result") or [] if isinstance(d, dict) else []
    now = time.time() * 1000
    exp = collections.Counter(dt.datetime.fromtimestamp(i["expiration_timestamp"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                              for i in ins if i["expiration_timestamp"] - now < 10 * 86400e3)
    report["deribit"][cur] = {"instruments": len(ins), "expiries_within_10d": dict(sorted(exp.items()))}
print(json.dumps(report, indent=1))
ok = report["kalshi"]["KXBTCD"]["exists"] and report["deribit"]["BTC"]["instruments"] > 0
sys.exit(0 if ok else "discovery incomplete: KXBTCD or the Deribit BTC chain did not answer")
