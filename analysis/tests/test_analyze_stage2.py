# Tests for analyze_stage2.py on synthetic data only. No real recorded data or outcome is read.
# Run: python3 -m unittest discover -s analysis/tests -v
import os, sys, json, gzip, math, random, shutil, tempfile, unittest, contextlib, io

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import analyze_stage2 as A
import make_fixture as MF

T0 = 1793895782.0          # 2026-11-05 15:23:02 UTC, a slot at phase 182


def meta(t, src, valid, events=None, kd_t0=None):
    return {"path": None, "src": src, "t": t, "valid": valid, "gap": 1.0, "move": 0.01, "events": events or {},
            "kd_t0": kd_t0 if kd_t0 is not None else t + 1, "kd_t1": t + 1.5, "chain_t1": t + 1, "declared": None}


def snap(gap=1.0, move_pct=0.01, opts=True, md=True, idx=True):
    F = 76000.0
    return {"utc": "2026-11-05T16:23:02+00:00",
            "index_before": {"body": {"result": {"index_price": F}}} if idx else {"body": None},
            "index_after": {"body": {"result": {"index_price": F * (1 + move_pct / 100)}}},
            "deribit": {"t0": 0, "t1": 100.0, "options": [{"x": 1}] if opts else []},
            "kxbtcd": {"t0": 99.0, "t1": 100.0 + gap, "markets": [{"event_ticker": "KXBTCD-26NOV0617", "close_time": "2026-11-06T22:00:00Z"}] if md else []}}


class FairValue(unittest.TestCase):
    def test_black_put_call_parity_and_iv_roundtrip(self):
        for x in (0.8, 0.95, 1.0, 1.07, 1.3):
            for w in (1e-5, 0.002, 0.03):
                c, p = A.black(1.0, x, w, True), A.black(1.0, x, w, False)
                self.assertAlmostEqual(c - p, 1 - x, places=12)
                for call, px in ((True, c), (False, p)):
                    if px > 1e-9 + (max(1 - x, 0) if call else max(x - 1, 0)):
                        self.assertAlmostEqual(A.implied_w(px, x, call), w, delta=w * 1e-6 + 1e-12)

    def test_iv_rejects_impossible_prices(self):
        self.assertIsNone(A.implied_w(0.05, 0.9, True))     # below intrinsic 0.1
        self.assertIsNone(A.implied_w(1.2, 0.9, True))      # above the forward
        self.assertIsNone(A.implied_w(0.0, 1.1, False))

    def test_deribit_mark_matches_inverse_black(self):
        # From the recorder's format: BTC-8NOV26-88000-P priced in BTC, mark_iv 58.34, underlying 76846.62 at 16:23:03Z on Nov 5.
        e, K, call = A.parse_instrument("BTC-8NOV26-88000-P")
        tau = (e - A.iso_ts("2026-11-05T16:23:01Z")) / A.YEAR_S
        px = A.black(76846.62, K, 0.5834 ** 2 * tau, call) / 76846.62
        self.assertAlmostEqual(px, 0.14499, delta=3e-4)
        self.assertEqual(A.parse_instrument("BTC-13NOV26-70000-C")[1:], (70000.0, True))

    def test_cubic_fit_is_exact_on_a_cubic(self):
        co = (0.002, -0.001, 0.01, 0.02)
        ks = [-0.2 + 0.05 * i for i in range(9)]
        got = A.lstsq_cubic(ks, [A.cubic(co, k) for k in ks])
        for a, b in zip(got, co):
            self.assertAlmostEqual(a, b, places=10)
        self.assertIsNone(A.lstsq_cubic([0.0, 0.1, 0.2], [1, 2, 3]))

    def chain(self, F, t, expiries):
        opts = []
        for e in expiries:
            tau = (e - t) / A.YEAR_S
            if tau <= 0:
                continue                                  # the exchange no longer lists an expired expiry
            d = A.dt.datetime.fromtimestamp(e, A.UTC).strftime("%d%b%y").upper().lstrip("0")
            for K in range(int(F) - 8000, int(F) + 8001, 1000):
                for cp in "CP":
                    px = MF.black(F, K, MF.true_w(math.log(K / F), tau), cp == "C") / F
                    if px > 2e-4:
                        opts.append({"instrument_name": f"BTC-{d}-{K}-{cp}", "bid_price": px - 1e-4, "ask_price": px + 1e-4,
                                     "mark_iv": 50, "underlying_price": F})
        d = A.dt.datetime.fromtimestamp(expiries[-1], A.UTC).strftime("%d%b%y").upper().lstrip("0")
        opts.append({"instrument_name": f"BTC-{d}-{int(F)}-C", "bid_price": 0.01, "ask_price": 0.02, "mark_iv": None, "underlying_price": F})
        opts.append({"instrument_name": f"BTC-{d}-{int(F)}-P", "bid_price": None, "ask_price": 0.02, "mark_iv": 50, "underlying_price": F})
        return opts

    def test_p_opt_between_expiries_and_before_first(self):
        F, t = 76000.0, A.iso_ts("2026-11-06T02:00:00Z")
        e1, e2 = A.iso_ts("2026-11-06T08:00:00Z"), A.iso_ts("2026-11-07T08:00:00Z")
        fits = A.fit_chain(self.chain(F, t, [e1, e2]), t)
        self.assertEqual(len(fits), 2)
        close = A.iso_ts("2026-11-06T22:00:00Z")                 # between e1 and e2: interpolation
        for K in (73000, 75500, 76000, 77250, 79000):
            self.assertAlmostEqual(A.p_above(fits, K, close, t), MF.true_p(F, K, (close - t) / A.YEAR_S), delta=2e-4)
        t2 = A.iso_ts("2026-11-06T10:00:00Z")                    # e1 has expired: close is before the first expiry
        fits2 = A.fit_chain(self.chain(F, t2, [e1, e2]), t2)
        self.assertEqual(len(fits2), 1)
        for K in (74000, 76000, 78000):
            self.assertAlmostEqual(A.p_above(fits2, K, close, t2), MF.true_p(F, K, (close - t2) / A.YEAR_S), delta=2e-4)
        self.assertIsNone(A.p_above(fits2, 76000, e2 + 3600, t2))   # beyond the last expiry: no value
        self.assertIsNone(A.p_above(fits2, 76000, t2 - 1, t2))      # already closed

    def test_bracket_probability(self):
        F, t = 76000.0, A.iso_ts("2026-11-06T02:00:00Z")
        fits = A.fit_chain(self.chain(F, t, [A.iso_ts("2026-11-06T08:00:00Z"), A.iso_ts("2026-11-07T08:00:00Z")]), t)
        close = A.iso_ts("2026-11-06T22:00:00Z")
        m = {"strike_type": "between", "floor_strike": 75750, "cap_strike": 76250}
        self.assertAlmostEqual(A.market_prob(fits, m, close, t), A.p_above(fits, 75750, close, t) - A.p_above(fits, 76250, close, t))
        self.assertAlmostEqual(A.market_prob(fits, {"strike_type": "less", "cap_strike": 76000}, close, t),
                               1 - A.p_above(fits, 76000, close, t))


class Validity(unittest.TestCase):
    def test_edges(self):
        v = lambda **k: A.snapshot_meta(snap(**k), "p", "local")["valid"]
        self.assertTrue(v(gap=5.0)); self.assertFalse(v(gap=5.01))
        self.assertTrue(v(move_pct=0.0999)); self.assertFalse(v(move_pct=0.1001))
        self.assertFalse(v(opts=False)); self.assertFalse(v(md=False)); self.assertFalse(v(idx=False))


class Merge(unittest.TestCase):
    def setUp(self):
        self.ms = [meta(T0, "local", True), meta(T0 + 0.4, "cloud", True),               # slot 0: local valid -> local
                   meta(T0 + 300, "local", False), meta(T0 + 301, "cloud", False), meta(T0 + 302, "cloud", True),  # slot 1: first valid cloud
                   meta(T0 + 600, "local", False),                                         # slot 2: invalid
                   meta(T0 + 900.5, "cloud", True),                                        # slot 3: cloud only
                   meta(T0 + 1200, "local", False), meta(T0 + 1210, "local", True)]       # slot 4: first local counts -> invalid
        self.g = A.Grid(self.ms)

    def test_merged_rule(self):
        pick, rec = A.build_series(self.ms, self.g, "merged")
        s = lambda k: self.g.slot(T0 + 300 * k)
        self.assertEqual((pick[s(0)]["src"], pick[s(0)]["t"]), ("local", T0))
        self.assertEqual((pick[s(1)]["src"], pick[s(1)]["t"]), ("cloud", T0 + 302))
        self.assertIsNone(pick[s(2)])
        self.assertEqual(pick[s(3)]["src"], "cloud")
        self.assertIsNone(pick[s(4)])
        self.assertEqual(rec[s(2)]["t"], T0 + 600)

    def test_single_source_rules(self):
        pl, _ = A.build_series(self.ms, self.g, "local")
        pc, _ = A.build_series(self.ms, self.g, "cloud")
        s = lambda k: self.g.slot(T0 + 300 * k)
        self.assertEqual(sum(1 for v in pl.values() if v), 1)
        self.assertIsNone(pc[s(1)])               # status.py rule on cloud alone: its first snapshot was invalid
        self.assertNotIn(s(2), pc)

    def test_coverage_threshold(self):
        close = A.iso_ts("2026-11-07T22:00:00Z")
        for n_valid, ok in ((288, True), (287, False)):
            ms = [meta(close - 30 * 3600 + 182 - 182 % 300 + 300 * i + (close % 300), "local", i < n_valid, {"KXBTCD-26NOV0717": close})
                  for i in range(360)]
            g = A.Grid(ms); pick, _ = A.build_series(ms, g, "merged")
            cov = A.event_coverage(pick, g, {"KXBTCD-26NOV0717": close})["KXBTCD-26NOV0717"]
            self.assertEqual((cov["possible"], cov["valid"], cov["qualifies"]), (360, n_valid, ok))


def row(**k):
    r = {"event": "E1", "ticker": "E1-T1", "t": T0, "t_q": T0 + 1.5, "h": 10.0, "bid": 0.40, "ask": 0.42, "mid": 0.41,
         "p": 0.50, "src": "local", "yes_depth_book": 40.0, "no_depth_book": 60.0, "yes_depth_top": 40.0, "no_depth_top": 60.0}
    r.update(k); return r


class Tests(unittest.TestCase):
    def test_s1_gap(self):
        gy, gn = A.gap_sides(row())
        self.assertAlmostEqual(gy, 0.50 - 0.42 - 0.07 * 0.42 * 0.58)
        self.assertAlmostEqual(gn, 0.50 - 0.60 - 0.07 * 0.60 * 0.40)
        res = A.s1([row(), row(event="E2", p=0.30)], random.Random(1))
        self.assertAlmostEqual(res["est"], (max(A.gap_sides(row())) + max(A.gap_sides(row(p=0.30)))) / 2)

    def test_s2_first_positive_row_and_side(self):
        rs = [row(t=T0, p=0.42), row(t=T0 + 300, p=0.50), row(t=T0 + 600, p=0.60),   # first g>0 at T0+300, YES at 0.42
              row(ticker="E1-T2", t=T0, p=0.20)]                                     # NO side: (0.8) - 0.6 - fee
        for r in rs:
            r["g"] = max(A.gap_sides(r))
        tr = A.s2_trades(rs, {"E1-T1": "no", "E1-T2": "no"})
        self.assertEqual(len(tr), 2)
        a = [x for x in tr if x["ticker"] == "E1-T1"][0]
        self.assertEqual((a["t"], a["side"]), (T0 + 300, "yes"))
        self.assertAlmostEqual(a["pnl"], -0.42 - A.fee(0.42))
        b = [x for x in tr if x["ticker"] == "E1-T2"][0]
        self.assertEqual(b["side"], "no"); self.assertAlmostEqual(b["pnl"], 1 - 0.60 - A.fee(0.60))

    def test_s3_fill_rule(self):
        r = row(p=0.50)                         # YES bid 0.40 < 0.50: rests; NO bid 0.58 > 0.50: does not rest
        win = {(T0, "local"): (T0 + 1.5, T0 + 301)}
        def tape(*trades):
            return {"E1-T1": sorted((T0 + dtt, yp, c, side) for dtt, yp, c, side in trades)}
        res = {"E1-T1": "yes"}
        f = lambda tp, **k: A.s3_fills([r], res, tp, win, **k)
        self.assertEqual(len(f(tape((10, 0.40, 40, "no")))[0]), 0)            # equal to depth: no fill
        fills, orders, _ = f(tape((10, 0.40, 25, "no"), (20, 0.40, 16, "no")))
        self.assertEqual((len(fills), orders), (1, 1))
        self.assertAlmostEqual(fills[0]["pnl"], 0.60)
        self.assertEqual(len(f(tape((10, 0.40, 50, "yes")))[0]), 0)           # a taker buying YES does not hit a YES bid
        self.assertEqual(len(f(tape((10, 0.41, 50, "no")))[0]), 0)            # other price
        self.assertEqual(len(f(tape((400, 0.40, 50, "no")))[0]), 0)           # after the cancel
        self.assertEqual(len(f(tape((1.0, 0.40, 50, "no")))[0]), 0)           # before the order existed
        self.assertEqual(len(f(tape((10, 0.40, 25, "no")), depth_mult=0.5)[0]), 1)   # half depth
        # NO side: resting NO bid at 1 - ask = 0.58 is hit by takers buying YES at 0.42
        r2 = row(p=0.30)
        fills, orders, _ = A.s3_fills([r2], {"E1-T1": "no"}, tape((10, 0.42, 61, "yes")), win)
        self.assertEqual((len(fills), orders, fills[0]["side"]), (1, 1, "no"))
        self.assertAlmostEqual(fills[0]["pnl"], 1 - 0.58)
        # depth: the larger of the book level and the top-of-book size
        r3 = row(yes_depth_book=100.0)
        self.assertEqual(len(A.s3_fills([r3], res, tape((10, 0.40, 80, "no")), win)[0]), 0)
        # S3b rests both sides
        self.assertEqual(A.s3_fills([r], res, tape(), win, both_sides=True)[1], 2)

    def test_tape_side_mapping(self):
        tp = [(T0 + 10, 0.40, 5.0, "no"), (T0 + 11, 0.40, 7.0, "yes"), (T0 + 12, 0.60, 3.0, "yes")]
        self.assertEqual(A.tape_volume(tp, "yes", 0.40, T0, T0 + 300), 5.0)
        self.assertEqual(A.tape_volume(tp, "no", 0.60, T0, T0 + 300), 7.0)
        self.assertEqual(A.tape_volume(tp, "no", 0.40, T0, T0 + 300), 3.0)

    def test_bootstrap_resamples_days(self):
        g = {f"E{i}": (float(i), 1.0) for i in range(10)}
        b = A.boot_ratio(g, random.Random(3))
        self.assertAlmostEqual(b["est"], 4.5); self.assertLess(b["lo"], 4.5); self.assertGreater(b["hi"], 4.5)
        self.assertEqual(b["days"], 10)


def run_cli(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = A.main(list(args))
        except SystemExit as e:
            return str(e.code), buf.getvalue()
    return rc, buf.getvalue()


class Guards(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        MF.make(self.d, days=0.5, cloud_start_h=0)
        for sub in ("local", "cloud"):
            os.remove(os.path.join(self.d, sub, "SYNTHETIC_FIXTURE"))        # pretend this is real data
        self.end = os.path.join(self.d, "far_end.txt")
        open(self.end, "w").write("2099-01-01T00:00:00+00:00\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra):
        d = self.d
        return ["run", "--local", f"{d}/local", "--cloud", f"{d}/cloud", "--settlements", f"{d}/settlements.json",
                "--trades", f"{d}/trades", "--out", f"{d}/out", "--end", self.end, *extra]

    def test_refuses_before_end_on_real_data(self):
        rc, _ = run_cli(*self.args())
        self.assertIn("refusing", rc)

    def test_refuses_clock_override_on_real_data(self):
        rc, _ = run_cli(*self.args("--now", "2099-02-01T00:00:00+00:00"))
        self.assertIn("only allowed on synthetic", rc)

    def test_refuses_second_run(self):
        os.makedirs(f"{self.d}/out"); open(f"{self.d}/out/stage2_results.json", "w").write("{}")
        open(self.end, "w").write("2026-11-05T00:00:00+00:00\n")
        rc, _ = run_cli(*self.args())
        self.assertIn("runs once", rc)

    def test_coverage_mode_never_needs_outcomes(self):
        rc, out = run_cli("coverage", "--local", f"{self.d}/local", "--cloud", f"{self.d}/cloud", "--end", self.end)
        self.assertEqual(rc, 0); self.assertIn("coverage, merged", out)

    def test_preflight_prints_counts_only(self):
        rc, out = run_cli("preflight", "--local", f"{self.d}/local", "--cloud", f"{self.d}/cloud", "--end", self.end)
        self.assertEqual(rc, 0); self.assertIn("preflight (counts only)", out)
        self.assertNotIn("S1", out); self.assertNotIn("p_opt", out)


class EndToEnd(unittest.TestCase):
    """Full fixtures: 10.4 days, an 8 h local outage the cloud covers, and every 7th local snapshot invalid."""
    @classmethod
    def setUpClass(cls):
        cls.dirs = {}
        for name, bias in (("fair", 0.0), ("edge", 0.06)):
            d = tempfile.mkdtemp()
            MF.make(d, days=10.45, bias=bias, seed=7, local_outages=((40, 8), (100, 7)), local_invalid_every=7)
            rc, out = run_cli("run", "--local", f"{d}/local", "--cloud", f"{d}/cloud", "--settlements", f"{d}/settlements.json",
                              "--trades", f"{d}/trades", "--out", f"{d}/out", "--end", f"{d}/end_utc.txt", "--now", "2026-11-17T00:00:00+00:00")
            assert rc == 0, (rc, out[-2000:])
            cls.dirs[name] = (d, json.load(open(f"{d}/out/stage2_results.json")), out)

    @classmethod
    def tearDownClass(cls):
        for d, _, _ in cls.dirs.values():
            shutil.rmtree(d)

    def test_merge_rescues_coverage(self):
        _, r, _ = self.dirs["fair"]
        self.assertGreaterEqual(r["merged"]["n_events"], 10)
        self.assertTrue(r["merged"]["complete"])
        self.assertLess(r["local"]["n_events"], r["merged"]["n_events"])
        self.assertIn("cloud", r["merged"]["row_sources"]); self.assertIn("local", r["merged"]["row_sources"])
        self.assertEqual(r["merged"]["rows_dropped_no_fair_value"], 0)

    def test_fair_quotes_kill_s1(self):
        _, r, _ = self.dirs["fair"]
        # quotes centred on the true probability: the best side's gap is about -(half spread + fee)
        self.assertEqual(r["merged"]["S1"]["verdict"], "KILL")
        self.assertLess(r["merged"]["S1"]["est"], -0.01)

    def test_biased_quotes_pass_s1(self):
        _, r, _ = self.dirs["edge"]
        self.assertEqual(r["merged"]["S1"]["verdict"], "PASS")
        self.assertGreater(r["merged"]["S2"]["trades"], 50)

    def test_noon_events_and_other_series_ignored(self):
        _, r, _ = self.dirs["fair"]
        self.assertTrue(all(e.endswith("17") and e.startswith("KXBTCD-") for e in r["merged"]["qualifying_settled_events"]))

    def test_p_opt_matches_truth(self):
        d, _, _ = self.dirs["fair"]
        truth = json.load(open(f"{d}/truth.json"))
        metas, _ = A.load_meta([("local", f"{d}/local")])
        errs = []
        for m in metas[::40]:
            if m["valid"]:
                for x in A.snapshot_rows(m)[0]:
                    k = f"{m['t']}|{x['ticker']}"
                    if k in truth and x["h"] > 2:
                        errs.append(abs(truth[k] - x["p"]))
        self.assertGreater(len(errs), 100)
        self.assertLess(max(errs), 1e-3)


if __name__ == "__main__":
    unittest.main()
