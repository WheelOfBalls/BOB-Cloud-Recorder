# Tests for analysis/analyze_stage3.py on synthetic fixtures only (tests/make_fixture_stage3.py). No real data.
import os, sys, json, gzip, math, random, tempfile, unittest, contextlib, io, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import analyze_stage3 as a3  # noqa: E402
import make_fixture_stage3 as mf  # noqa: E402

UTC = dt.timezone.utc
START = dt.datetime(2026, 11, 20, tzinfo=UTC).timestamp()
DAYS = 22
_cache = {}


def world(name):
    """Each 22-day world is built and analysed once per test run (about 40 s each)."""
    if name not in _cache:
        kw = {"null": dict(delta=0.0, seed=11), "edge": dict(delta=0.06, seed=12),
              "wrong_fair_value": dict(delta=0.0, seed=13, chain_vol_mult=0.7),
              "adverse": dict(delta=0.0, seed=14, adverse=True, fill_prob=0.5)}[name]
        w = mf.World(START, DAYS, **kw)
        snaps, polls, results, tapes = w.build()
        out = a3.analyse(snaps, polls, results, tapes, START, START + DAYS * 86400)
        _cache[name] = (w, snaps, polls, results, tapes, out)
    return _cache[name]


class TestPieces(unittest.TestCase):
    def test_fee(self):
        self.assertAlmostEqual(a3.fee(0.5), 0.0175)
        self.assertAlmostEqual(a3.fee(0.37), 0.0164)            # 0.016317 rounded up to the centicent
        self.assertAlmostEqual(a3.fee(0.10), 0.0063)
        self.assertAlmostEqual(a3.fee_cent(0.5), 0.02)
        self.assertAlmostEqual(a3.fee_cent(0.10), 0.01)

    def test_t_quantile(self):
        for df, q in ((1, 6.3138), (5, 2.0150), (20, 1.7247), (27, 1.7033), (200, 1.6525)):
            self.assertAlmostEqual(a3.t_quantile(0.95, df), q, places=3)

    def test_cluster_formula(self):
        items = [{"day": "a", "v": 1.0}, {"day": "a", "v": 3.0}, {"day": "b", "v": -1.0}, {"day": "c", "v": 2.0}, {"day": "c", "v": 0.0}]
        c = a3.cluster(items, lambda x: x["v"])
        mu = 5.0 / 5
        se = math.sqrt(3 / 2 * ((4 - 2 * mu) ** 2 + (-1 - mu) ** 2 + (2 - 2 * mu) ** 2)) / 5
        self.assertAlmostEqual(c["est"], mu); self.assertAlmostEqual(c["se"], se)
        self.assertAlmostEqual(c["lo"], mu - a3.t_quantile(0.95, 2) * se)
        self.assertEqual(c["days"], 3)

    def test_verdict_rules(self):
        h = lambda lo, hi: {"lo": lo, "hi": hi, "est": (lo + hi) / 2}
        self.assertEqual(a3.t1_verdict(h(0.001, 0.03), {"est": 0.01}, 500, True), "PASS")
        self.assertEqual(a3.t1_verdict(h(0.001, 0.03), {"est": -0.01}, 500, True), "INCONCLUSIVE")   # unhedged sign disagrees
        self.assertEqual(a3.t1_verdict(h(-0.02, 0.009), {"est": 0.01}, 500, True), "KILL")           # upper bound < 1 cent
        self.assertEqual(a3.t1_verdict(h(0.01, 0.05), {"est": 0.01}, 199, True), "KILL")             # under 200 trades
        self.assertEqual(a3.t1_verdict(h(-0.01, 0.02), {"est": 0.01}, 500, True), "INCONCLUSIVE")
        self.assertEqual(a3.t1_verdict(h(0.01, 0.05), {"est": 0.01}, 500, False), "INCOMPLETE")
        self.assertEqual(a3.t2_verdict(h(0.01, 0.05), 300, True), "PASS")
        self.assertEqual(a3.t2_verdict(h(-0.05, -0.01), 300, True), "KILL")
        self.assertEqual(a3.t2_verdict(h(0.01, 0.05), 150, True), "KILL")

    def test_p_opt_forward_and_step(self):
        """Close before the first expiry: forward = index_before, variance scaled by time; h capped and shrunk."""
        w = mf.World(START, 1, seed=1)
        t = START + 7 * 3600 + 150                     # 07:02:30, first expiry 08:00 today
        close = START + 8 * 3600
        for coin, K_off in (("BTC", 0.0), ("ETH", 10.0)):
            fits = a3.a2.fit_chain(w.chain(coin, t), t)
            S = w.S(coin, t)
            p, F, sd, wk = a3.p_above(coin, fits, S + K_off, close, t, S)
            self.assertEqual(F, S)
            self.assertAlmostEqual(p, w.truth(coin, S + K_off, t, close), delta=0.001)
            self.assertAlmostEqual(sd, mf.COIN[coin]["vol"] * math.sqrt((close - t) / mf.YEAR), delta=1e-4)
        # with a 5-minute horizon the step must shrink well below the $50 cap
        t2 = close - 300
        fits = a3.a2.fit_chain(w.chain("BTC", t2), t2)
        S = w.S("BTC", t2)
        p, F, sd, wk = a3.p_above("BTC", fits, S + 50, close, t2, S)
        self.assertAlmostEqual(p, w.truth("BTC", S + 50, t2, close), delta=0.002)
        self.assertLess(0.1 * F * sd, 50)

    def test_digital_delta(self):
        S, K, w = 100.0, 101.0, 0.0004
        f = lambda s: a3.a2.ncdf((math.log(s / K) - 0.5 * w) / math.sqrt(w))
        self.assertAlmostEqual(a3.digital_delta(S, K, w), (f(S + 1e-3) - f(S - 1e-3)) / 2e-3, places=5)

    def test_hedge_starts_after_the_quote(self):
        tr = {"coin": "BTC", "t_after": 1000.5, "i_after": 100.0, "close": 1200.0, "K": 100.0, "t_now": 1000.0,
              "wk": 1e-6, "side": "yes", "above": True}
        polls = {"BTC": [(960.0, 960.05, 99.0), (1020.0, 1020.05, 101.0), (1080.0, 1080.05, 102.0), (1200.0, 1200.05, 103.0),
                         (1260.0, 1260.05, 104.0)]}
        pts = a3.hedge_path(tr, polls)
        self.assertEqual(pts, [(1000.5, 100.0), (1020.0, 101.0), (1080.0, 102.0), (1200.0, 103.0)])   # not 960, not after close
        h, n = a3.hedge_term(tr, pts)
        exp = sum(a3.digital_delta(S, 100.0, 1e-6 * (1200 - t) / 200) * (S2 - S) for (t, S), (_, S2) in zip(pts, pts[1:]))
        self.assertAlmostEqual(h, exp)
        tr2 = dict(tr, side="no")
        self.assertAlmostEqual(a3.hedge_term(tr2, pts)[0], -exp)

    def test_hedge_is_mean_zero_control_variate(self):
        """Hedged P&L must estimate the same mean as unhedged P&L with less noise (planted edge world)."""
        out = world("edge")[5][0]
        hed, unh = out["T1"]["hedged"], out["T1"]["unhedged"]
        gap = out["reference"]["ex_ante_gap_on_traded_rows"]["est"]
        self.assertLess(hed["se"], unh["se"] / 3)
        self.assertLess(abs(hed["est"] - gap), 3 * hed["se"] + 0.002)     # p_opt is exact here, so gap = true edge
        self.assertLess(abs(unh["est"] - gap), 3 * unh["se"])


class TestWorlds(unittest.TestCase):
    def test_planted_edge_passes(self):
        out = world("edge")[5][0]
        self.assertTrue(out["complete"])
        self.assertEqual(out["T1"]["verdict"], "PASS")
        self.assertGreater(out["T1"]["trades"], 1000)
        self.assertGreater(out["T1"]["hedged"]["est"], 0.025)              # 6c mispricing - 1c half spread - fee
        self.assertLess(out["T1"]["hedged"]["est"], 0.05)

    def test_null_kills(self):
        out = world("null")[5][0]
        self.assertEqual(out["T1"]["verdict"], "KILL")

    def test_wrong_fair_value_cannot_pass(self):
        """Kalshi = truth, p_opt from a 30% too low volatility: the ex-ante gap is positive, realised P&L is not."""
        out = world("wrong_fair_value")[5][0]
        self.assertGreater(out["T1"]["trades"], a3.NEED_TRADES)
        self.assertGreater(out["reference"]["ex_ante_gap_on_traded_rows"]["est"], 0.01)
        self.assertEqual(out["T1"]["verdict"], "KILL")
        self.assertLess(out["T1"]["hedged"]["hi"], a3.KILL_EDGE)

    def test_adverse_maker_fills_kill_t2(self):
        out = world("adverse")[5][0]
        self.assertEqual(out["T2"]["verdict"], "KILL")
        self.assertLess(out["T2"]["est"], 0)

    def test_row_sync_flags_but_keeps_rows(self):
        """Deviation 1: a move between index_before and index_after (read after the quote) flags rows, never drops them."""
        import copy
        w, snaps, polls, results, tapes, _ = world("null")
        i = next(k for k, s in snaps.items() if a3.coin_valid(s, "BTC") and a3.snapshot_rows(s, k, "BTC")[0])
        base, _, _ = a3.snapshot_rows(snaps[i], i, "BTC")
        s2 = copy.deepcopy(snaps[i])
        s2["coins"]["BTC"]["index_after"]["body"]["result"]["index_price"] *= 1.0009   # inside the 0.10% validity rule
        self.assertTrue(a3.coin_valid(s2, "BTC"))
        moved, drop, _ = a3.snapshot_rows(s2, i, "BTC")
        self.assertEqual([r["ticker"] for r in moved], [r["ticker"] for r in base])
        self.assertTrue(all(r["sync_ok"] for r in base))
        self.assertFalse(any(r["sync_ok"] for r in moved))
        self.assertEqual(drop["row-sync flag (kept; deviation 1)"], len(moved))

    def test_rows_respect_filters(self):
        w, snaps, polls, results, tapes, (out, rows, trades, fills) = world("edge")
        self.assertTrue(rows)
        for r in rows[:5000]:
            self.assertFalse(r["event"].endswith("17"))
            self.assertTrue(0.06 - 1e-9 <= r["mid"] <= 0.94 + 1e-9)
            self.assertTrue(2 <= r["mins"] <= 60)
        self.assertEqual(len({t["ticker"] for t in trades}), len(trades))   # one trade per market
        for k in ("T1_coin_BTC", "T1_coin_ETH", "T1_minutes_2-15", "T1_tau_0.00", "T1_tau_0.02", "T1_fee_rounded_up_to_cent",
                  "T1_hedged_bootstrap_days", "T1_hedged_bootstrap_7day_blocks", "T1_stale_split_quiet", "T1_hedge_5min_snapshots",
                  "calibration_last_row_ge_5min", "T1_with_preregistered_row_sync_rule"):
            self.assertIn(k, out["reference"])
        self.assertEqual(out["reference"]["T1_hedged_bootstrap_7day_blocks"]["units"], 4)
        # whole-cent fee makes T1 worse, never better
        self.assertLess(out["reference"]["T1_fee_rounded_up_to_cent"]["unhedged"]["est"], out["T1"]["unhedged"]["est"])

    def test_invalid_slots_and_uncounted_day(self):
        w = mf.World(START, 3, delta=0.06, seed=5, bad_day=1, bad_frac=0.4)
        snaps, polls, results, tapes = w.build()
        days = a3.coverage(snaps, START, START + 3 * 86400)
        self.assertEqual([d["counts"] for d in days.values()], [True, False, True])
        out, rows, trades, fills = a3.analyse(snaps, polls, results, tapes, START, START + 3 * 86400)
        self.assertEqual(out["T1"]["verdict"], "INCOMPLETE")
        self.assertNotIn("2026-11-21", {r["day"] for r in rows})
        self.assertNotIn("2026-11-21", {r["snap_day"] for r in rows})
        # an invalid coin-snapshot (6 s gap) contributes no rows
        bad = {i for i, s in snaps.items() if not a3.coin_valid(s, "BTC")}
        self.assertTrue(bad)
        self.assertFalse({r["slot"] for r in rows if r["coin"] == "BTC"} & bad)


class TestDriverAndGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        cls.data = mf.write(mf.World(START, 2, delta=0.06, seed=7), cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_main(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = a3.main(list(args))
        return rc, buf.getvalue()

    def test_coverage_and_preflight_print_no_prices(self):
        rc, text = self.run_main("coverage", "--data", self.data)
        self.assertEqual(rc, 0); self.assertIn("counted days 2", text)
        rc, text = self.run_main("preflight", "--data", self.data)
        self.assertIn("rows (counts only, all days)", text)
        for bad in ("0.4", "9000", "300"):
            self.assertNotIn(bad + ".", text)

    def test_run_on_fixture(self):
        res = os.path.join(self.out, "res")
        rc, text = self.run_main("run", "--data", self.data, "--settlements", os.path.join(self.out, "settlements.json"),
                                 "--trades", os.path.join(self.out, "trades"), "--out", res, "--now", "2026-12-20T00:00:00+00:00")
        self.assertEqual(rc, 0)
        self.assertIn("INCOMPLETE", text)                         # 2 days < 21
        with open(os.path.join(res, "stage3_results.json")) as f:
            js = json.load(f)
        self.assertTrue(js["synthetic"]); self.assertEqual(len(js["script_sha256"]), 64)
        self.assertGreater(js["T2"]["fills"], 0)

    def real_copy(self, mode="live"):
        """A copy of the fixture that looks real: no marker, no synthetic flag."""
        d = tempfile.mkdtemp(dir=self.out)
        p = os.path.join(d, "2026-11-20"); os.makedirs(p)
        with gzip.open(os.path.join(self.data, "2026-11-20", "000230.json.gz"), "rt") as f:
            s = json.load(f)
        s.pop("synthetic"); s["mode"] = mode
        with gzip.open(os.path.join(p, "000230.json.gz"), "wt") as f:
            json.dump(s, f)
        return d

    def test_guards_on_real_data(self):
        st, tr = os.path.join(self.out, "settlements.json"), os.path.join(self.out, "trades")
        live = self.real_copy("live")
        with self.assertRaises(SystemExit) as e:
            self.run_main("run", "--data", live, "--settlements", st, "--trades", tr, "--out", os.path.join(self.out, "x"))
        self.assertIn("recording ends", str(e.exception))
        with self.assertRaises(SystemExit) as e:
            self.run_main("coverage", "--data", live, "--now", "2027-01-01T00:00:00+00:00")
        self.assertIn("only allowed on synthetic", str(e.exception))
        with self.assertRaises(SystemExit) as e:
            self.run_main("run", "--data", live, "--settlements", st, "--trades", tr, "--out", os.path.join(self.out, "w"),
                          "--end", "2026-11-21T00:00:00+00:00")
        self.assertIn("fixed", str(e.exception))
        pilot = self.real_copy("pilot")
        rc, _ = self.run_main("preflight", "--data", pilot)          # counts only: allowed on pilot data
        self.assertEqual(rc, 0)
        with self.assertRaises(SystemExit) as e:
            self.run_main("run", "--data", pilot, "--settlements", st, "--trades", tr, "--out", os.path.join(self.out, "z"))
        self.assertIn("pilot data never enters", str(e.exception))
        # a marker file alone does not make real snapshots synthetic
        open(os.path.join(live, "SYNTHETIC_FIXTURE"), "w").close()
        with self.assertRaises(SystemExit):
            self.run_main("run", "--data", live, "--settlements", st, "--trades", tr, "--out", os.path.join(self.out, "y"),
                          "--now", "2027-01-01T00:00:00+00:00")

    def test_pull_after_refuses_before_end(self):
        import subprocess
        r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(HERE), "pull_after_stage3.py"), "--data", self.data,
                            "--out", os.path.join(self.out, "pull")], capture_output=True, text=True)
        if dt.datetime.now(UTC).timestamp() < a3.iso_ts(a3.END_UTC):
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("refusing", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(self.out, "pull", "settlements.json")))

    def test_dates_match_recorder(self):
        root = os.path.dirname(os.path.dirname(HERE))
        for name, val in (("start_utc.txt", a3.START_UTC), ("end_utc.txt", a3.END_UTC)):
            with open(os.path.join(root, "stage3", name)) as f:
                self.assertEqual(f.read().strip(), val)


if __name__ == "__main__":
    unittest.main()
