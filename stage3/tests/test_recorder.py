# Tests for the stage 3 recorder, loop and counts-only report. Synthetic responses only: no network, nothing pushed.
import os, sys, json, gzip, tempfile, unittest, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import record_snapshot as rs  # noqa: E402
import cloud_loop as cl  # noqa: E402
import counts_report as cr  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 20, 14, 2, 30, tzinfo=UTC)
BTC_INDEX, ETH_INDEX = 91234.56, 3123.45          # distinctive values that must never appear in a report


def mk_market(ticker, event, close, strike, bid, ask):
    return {"ticker": ticker, "event_ticker": event, "status": "active", "open_time": "2026-11-20T13:00:00Z",
            "close_time": close, "floor_strike": strike, "strike_type": "greater",
            "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}", "yes_bid_size_fp": "10.00", "yes_ask_size_fp": "12.00",
            "extra_field": "dropped"}


def kalshi_markets(series, close="2026-11-20T15:00:00Z"):
    ev_h = f"{series}-26NOV2010"        # 10:00 ET = 15:00 UTC, an hourly event
    ev_d = f"{series}-26NOV2017"        # the 5pm daily event
    ms = [mk_market(f"{ev_h}-T{k}", ev_h, close, k, b, a) for k, b, a in
          ((100, 0.40, 0.42), (200, 0.01, 0.02), (300, 0.50, 0.53), (400, 0.97, 0.99), (500, 0.10, 0.12))]
    ms += [mk_market(f"{ev_d}-T{k}", ev_d, "2026-11-20T22:00:00Z", k, 0.45, 0.47) for k in (1000, 1500)]
    return ms


class FakeFetcher:
    """Serves synthetic bodies; time advances 0.1 s per request. Records the call order."""
    def __init__(self, page_size=3, index_move=0.0, slow_kalshi=0.0, fail=()):
        self.errors, self.calls, self.t = [], [], NOW.timestamp()
        self.page_size, self.index_move, self.slow_kalshi, self.fail = page_size, index_move, slow_kalshi, fail
        self.index_reads = {}

    def clock(self):
        return self.t

    def get(self, url, tries=2):
        t0 = self.t
        self.t += 0.1
        self.calls.append(url)
        body = None
        if any(f in url for f in self.fail):
            self.errors.append(url[-40:] + ": fail")
        elif "get_book_summary_by_currency" in url:
            cur = "BTC" if "currency=BTC" in url else "ETH"
            F = BTC_INDEX if cur == "BTC" else ETH_INDEX
            opts = []
            for exp in ("21NOV26", "22NOV26", "30NOV26"):
                for k in (0.9, 0.95, 1.0, 1.05, 1.1):
                    for cp in ("C", "P"):
                        opts.append({"instrument_name": f"{cur}-{exp}-{int(F * k)}-{cp}", "bid_price": 0.01, "ask_price": 0.012,
                                     "mark_price": 0.011, "mark_iv": 50.0, "underlying_price": F, "open_interest": 1, "extra": 1})
            body = {"result": opts}
        elif "get_index_price" in url:
            base = BTC_INDEX if "btc_usd" in url else ETH_INDEX
            n = self.index_reads.get(url, 0)
            self.index_reads[url] = n + 1
            body = {"result": {"index_price": base * (1 + self.index_move * n)}, "usOut": int(self.t * 1e6)}
        elif "/series/" in url:
            body = {"series": {"frequency": "hourly", "fee_type": "quadratic", "fee_multiplier": 1}}
        elif "/orderbook" in url:
            body = {"orderbook_fp": {"yes_dollars": [["0.40", "10.00"]], "no_dollars": [["0.58", "12.00"]]}}
        elif "/markets?" in url:
            self.t += self.slow_kalshi
            series = url.split("series_ticker=")[1].split("&")[0]
            allm = kalshi_markets(series) if series in ("KXBTCD", "KXETHD") else [mk_market(f"{series}-B1", f"{series}-26NOV2010",
                                                                                            "2026-11-20T15:00:00Z", 1, 0.2, 0.3)]
            start = int(url.split("cursor=")[1].split("&")[0]) if "cursor=" in url else 0
            page = allm[start:start + self.page_size]
            nxt = start + self.page_size
            body = {"markets": page, "cursor": str(nxt) if nxt < len(allm) else ""}
        return {"t0": t0, "t1": self.t, "body": body}


def take(**kw):
    f = FakeFetcher(**kw)
    s = rs.snapshot(f, now=NOW, sleep=lambda x: None, clock=f.clock, env={"BOB_MODE": "pilot", "BOB_SLOT_TARGET": NOW.isoformat()})
    return f, s


class TestSnapshot(unittest.TestCase):
    def test_request_order_per_coin(self):
        f, s = take()
        kinds = []
        for u in f.calls:
            kinds.append("chain" if "book_summary" in u else "index" if "index_price" in u else "book" if "orderbook" in u
                         else "list:" + u.split("series_ticker=")[1].split("&")[0])
        # BTC: chain, index, list pages, index; then ETH the same; then books; then the bracket lists
        first_eth = kinds.index("chain", 1)
        btc = kinds[:first_eth]
        self.assertEqual(btc[0], "chain"); self.assertEqual(btc[1], "index"); self.assertEqual(btc[-1], "index")
        self.assertTrue(all(k == "list:KXBTCD" for k in btc[2:-1]))
        self.assertGreater(kinds.index("book"), max(i for i, k in enumerate(kinds) if k == "list:KXETHD"))
        self.assertLess(max(i for i, k in enumerate(kinds) if k == "book"), kinds.index("list:KXBTC"))
        for c in ("BTC", "ETH"):
            cc = s["coins"][c]
            self.assertLessEqual(cc["chain"]["t1"], cc["index_before"]["t0"])
            self.assertLessEqual(cc["index_before"]["t1"], cc["kalshi"]["t0"])     # p_opt inputs end before Kalshi starts
            self.assertLessEqual(cc["kalshi"]["t1"], cc["index_after"]["t0"])      # hedge starts after the response

    def test_pagination_and_trim(self):
        _, s = take(page_size=3)
        k = s["coins"]["BTC"]["kalshi"]
        self.assertEqual(len(k["markets"]), 7)
        self.assertEqual(k["pages"], 3)
        self.assertTrue(k["complete"])
        self.assertNotIn("extra_field", k["markets"][0])
        self.assertNotIn("extra", s["coins"]["BTC"]["chain"]["options"][0])

    def test_books_only_hourly_inside_3_97(self):
        _, s = take()
        books = sorted(s["books"])
        # strikes 100 (0.40/0.42), 300 (0.50/0.53), 500 (0.10/0.12) qualify; 200 (bid 0.01) and 400 (ask 0.99) don't; 5pm never
        self.assertEqual(books, sorted(f"{c}-26NOV2010-T{k}" for c in ("KXBTCD", "KXETHD") for k in (100, 300, 500)))
        self.assertFalse(s["books_truncated"])
        self.assertIn("yes_dollars", s["books"][books[0]]["book"])

    def test_book_budget(self):
        f = FakeFetcher()
        clock = iter(range(0, 10000, 60))           # each clock() call jumps a minute
        s = rs.snapshot(f, now=NOW, sleep=lambda x: None, clock=lambda: next(clock), env={})
        self.assertTrue(s["books_truncated"])
        self.assertLess(len(s["books"]), 6)

    def test_chain_three_days(self):
        _, s = take()
        exps = {o["instrument_name"].split("-")[1] for o in s["coins"]["ETH"]["chain"]["options"]}
        self.assertEqual(exps, {"21NOV26", "22NOV26"})          # 30NOV is beyond 3 days

    def test_validity(self):
        _, s = take()
        self.assertTrue(rs.validity(s, "BTC")[0])
        self.assertTrue(rs.validity(s, "ETH")[0])
        _, s = take(index_move=0.0011)
        self.assertFalse(rs.validity(s, "BTC")[0])
        _, s = take(slow_kalshi=6.0)
        ok, gap = rs.validity(s, "BTC")
        self.assertFalse(ok); self.assertGreater(gap, 5)
        _, s = take(fail=("cursor=3",))
        self.assertFalse(s["coins"]["BTC"]["kalshi"]["complete"])
        self.assertFalse(rs.validity(s, "BTC")[0])
        self.assertTrue(s["errors"])

    def test_hourly(self):
        self.assertTrue(rs.is_hourly("KXBTCD-26NOV2010"))
        self.assertFalse(rs.is_hourly("KXBTCD-26NOV2017"))
        self.assertFalse(rs.is_hourly(""))
        self.assertFalse(rs.is_hourly(None))

    def test_write_and_log(self):
        _, s = take()
        with tempfile.TemporaryDirectory() as d:
            fn = rs.write(s, d)
            self.assertTrue(fn.endswith(os.path.join("2026-11-20", "140230.json.gz")))
            back = json.load(gzip.open(fn, "rt"))
            self.assertEqual(back["stage"], 3); self.assertEqual(back["mode"], "pilot")
            with open(os.path.join(d, "run_log.csv")) as fh:
                log = fh.read().splitlines()
            self.assertEqual(len(log), 2); self.assertTrue(log[0].startswith("utc,"))
            self.assertEqual(log[1].split(",")[9:11], ["1", "1"])


class TestLoop(unittest.TestCase):
    W = {"pilot_until": dt.datetime(2026, 11, 8, 6, tzinfo=UTC).timestamp(),
         "start": dt.datetime(2026, 11, 20, tzinfo=UTC).timestamp(), "end": dt.datetime(2026, 12, 18, tzinfo=UTC).timestamp()}

    def test_modes(self):
        ts = lambda *a: dt.datetime(*a, tzinfo=UTC).timestamp()
        self.assertEqual(cl.mode_at(ts(2026, 11, 6, 12), self.W), "pilot")
        self.assertEqual(cl.mode_at(ts(2026, 11, 8, 6), self.W), "off")
        self.assertEqual(cl.mode_at(ts(2026, 11, 19, 23, 20), self.W), "off")
        self.assertEqual(cl.mode_at(ts(2026, 11, 19, 23, 40), self.W), "live")    # may start 30 min early and wait
        self.assertEqual(cl.mode_at(ts(2026, 12, 17, 23, 59), self.W), "live")
        self.assertEqual(cl.mode_at(ts(2026, 12, 18), self.W), "off")
        self.assertEqual(cl.slot_range("live", self.W), (self.W["start"], self.W["end"]))

    def test_files_match(self):
        w = cl.windows()
        self.assertEqual(w["start"], self.W["start"])
        self.assertEqual(w["end"] - w["start"], 28 * 86400)                     # 28 full UTC days
        self.assertLessEqual(w["pilot_until"], w["start"])

    def test_slot_phase(self):
        t = cl.next_slot(dt.datetime(2026, 11, 20, 0, 0, 0, tzinfo=UTC).timestamp())
        self.assertEqual(dt.datetime.fromtimestamp(t, UTC).strftime("%H:%M:%S"), "00:02:30")
        mins = sorted({(3600 - (cl.next_slot(x) % 3600)) / 60 for x in range(0, 3600, 60)})
        self.assertEqual(mins[0], 2.5); self.assertEqual(mins[-1], 57.5); self.assertEqual(len(mins), 12)

    def test_minute_poller(self):
        f = FakeFetcher()
        clock = {"t": dt.datetime(2026, 11, 20, 14, 58, 30, tzinfo=UTC).timestamp()}
        def sleep(x):
            clock["t"] += x
        with tempfile.TemporaryDirectory() as d:
            p = cl.MinutePoller(d, 0, clock["t"] + 200, fetch=f.get, clock=lambda: clock["t"], sleep=sleep)
            p.run()
            rows = cr.read_csv(os.path.join(d, "index_1m", "2026-11-20.csv"))
            self.assertEqual([r["target_utc"][11:19] for r in rows], ["14:59:00"] * 2 + ["15:00:00"] * 2 + ["15:01:00"] * 2)
            self.assertEqual({r["coin"] for r in rows}, {"BTC", "ETH"})
            self.assertTrue(all(r["index_price"] for r in rows))

    def test_series_meta(self):
        f = FakeFetcher()
        with tempfile.TemporaryDirectory() as d:
            cl.series_meta(d, fetch=f.get)
            rows = cr.read_csv(os.path.join(d, "series_meta.csv"))
            self.assertEqual([r["series"] for r in rows], ["KXBTCD", "KXETHD"])
            self.assertEqual(rows[0]["fee_multiplier"], "1")


class TestCountsReport(unittest.TestCase):
    def build(self, d, mode="pilot", n=4):
        for i in range(n):
            now = NOW + dt.timedelta(minutes=5 * i)
            f = FakeFetcher()
            f.t = now.timestamp()
            s = rs.snapshot(f, now=now, sleep=lambda x: None, clock=f.clock, env={"BOB_MODE": mode, "BOB_SLOT_TARGET": now.isoformat()})
            rs.write(s, d)
        p = cl.MinutePoller(d, 0, 0, fetch=FakeFetcher().get)
        for i in range(20):
            p.poll(NOW.timestamp() - 150 + 60 * i)

    def test_report_counts_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d)
            text, js = cr.report(d)
            self.assertEqual(js["snapshots"], 4)
            self.assertEqual(js["rows"], {"BTC": 4 * 3, "ETH": 4 * 3})     # strikes 100, 300, 500 pass the mid band; 200 and 400 don't
            self.assertEqual(js["spreads"]["2"], 16); self.assertEqual(js["spreads"]["3"], 8)
            self.assertEqual(js["events_BTC"]["hourly"], 1)
            self.assertEqual(js["index_BTC"]["ok"], 20)
            for secret in ("91234", "3123.4", "0.41", "0.515", "0.11", "0.4200", "0.5300"):  # index levels, mids, asks
                self.assertNotIn(secret, text)

    def test_no_spreads_on_live(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d, mode="live", n=2)
            text, js = cr.report(d)
            self.assertNotIn("spreads", js)
            self.assertIn("not shown on live data", text)


if __name__ == "__main__":
    unittest.main()
