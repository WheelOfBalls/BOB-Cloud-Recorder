# Tests for stage2/status.py on small synthetic recordings. Run: python3 -m unittest discover -s tests
import os, sys, io, json, gzip, shutil, tempfile, unittest, contextlib, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stage2"))
import status

UTC = dt.timezone.utc
PHASE = 182  # hh:m3:02, like both recorders
def slot_time(day_hour, k):
    """k-th 5-minute slot after a whole UTC hour, at the recorders' phase."""
    return dt.datetime.fromisoformat(day_hour).replace(tzinfo=UTC).timestamp() + k * 300 + PHASE

def write_snapshot(D, t, valid=True, event="KXBTCD-26NOV0717", close="2026-11-07T22:00:00Z", source=None):
    u = dt.datetime.fromtimestamp(t, UTC)
    gap = 0.3 if valid else 9.0  # over 5 s makes the snapshot invalid
    snap = {"utc": u.isoformat(), "version": 1,
            "index_before": {"t0": t, "t1": t + 0.1, "body": {"result": {"index_price": 100000.0}}},
            "index_after": {"t0": t + 2, "t1": t + 2.1, "body": {"result": {"index_price": 100010.0}}},
            "deribit": {"t0": t, "t1": t + 1.0, "options": [{"instrument_name": "BTC-7NOV26-100000-C", "bid_price": 0.01, "ask_price": 0.012,
                                                              "mark_price": 0.011, "creation_timestamp": (t + 0.5) * 1000}]},
            "kxbtcd": {"t0": t + 1.0, "t1": t + 1.0 + gap, "markets": [{"ticker": event + "-T100000", "event_ticker": event, "close_time": close,
                                                                       "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.45", "volume_fp": str(t)}]},
            "kxbtc": {"t0": t, "t1": t, "markets": []}, "books": {event + "-T100000": {"t0": t, "t1": t, "book": {}}}, "errors": []}
    if source: snap["source"] = {"host": source}
    d = os.path.join(D, u.strftime("%Y-%m-%d")); os.makedirs(d, exist_ok=True)
    with gzip.open(os.path.join(d, u.strftime("%H%M%S") + ".json.gz"), "wt") as fh: json.dump(snap, fh)
    with open(os.path.join(D, "run_log.csv"), "a") as fh: fh.write(f"{u.isoformat()},1,1,0,1,{gap:.2f},3.0,0,\n")

def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out): status.main(list(args))
    return out.getvalue()

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.L = os.path.join(self.tmp, "local"); self.C = os.path.join(self.tmp, "cloud", "data")
        os.makedirs(self.L); os.makedirs(self.C)
    def tearDown(self): shutil.rmtree(self.tmp)
    def series(self, now):
        L = status.load_source("local", self.L, os.path.join(self.tmp, "cl.json")); C = status.load_source("cloud", self.C, os.path.join(self.tmp, "cc.json"))
        g = status.Grid(L["S"], dt.datetime.fromisoformat(now).timestamp(), None)
        Ls, Cs = status.source_series(L, g), status.source_series(C, g)
        return g, Ls, Cs, status.merged_series(Ls, Cs, g)

class MergeRule(Base):
    def test_per_slot_choice(self):
        H = "2026-11-06T10:00:00"; s = lambda k: slot_time(H, k)
        write_snapshot(self.L, s(0)); write_snapshot(self.C, s(0) + 4)                   # 0: both valid -> local
        write_snapshot(self.L, s(1), valid=False); write_snapshot(self.C, s(1) + 3)      # 1: local invalid -> cloud
        write_snapshot(self.C, s(2) + 2, valid=False); write_snapshot(self.C, s(2) + 40)  # 2: no local -> first VALID cloud
        write_snapshot(self.L, s(3), valid=False); write_snapshot(self.C, s(3) + 1, valid=False)  # 3: neither valid -> invalid
        with open(os.path.join(self.L, "trace.log"), "w") as fh:                           # 4: local run died, no cloud -> died
            fh.write(f"{dt.datetime.fromtimestamp(s(4), UTC).isoformat()} pid 42 start\n")
        write_snapshot(self.L, s(6)); write_snapshot(self.C, s(6) + 2)                   # 5: nothing at all -> none
        g, L, C, M = self.series("2026-11-06T11:00:00+00:00")
        i0 = g.slot(s(0))
        self.assertEqual([M["st"][i0 + k] for k in range(7)], ["valid", "valid", "valid", "invalid", "died", "none", "valid"])
        self.assertEqual([M["pick"][i0 + k]["src"] for k in (0, 1, 2, 6)], ["local", "cloud", "cloud", "local"])
        self.assertAlmostEqual(M["pick"][i0 + 2]["t"], s(2) + 40)  # the later, valid cloud snapshot, not the first one
        self.assertEqual(M["from"], {"local": 2, "cloud": 2})
        # the per-source series keep status.py's own rule: the first snapshot in a slot counts
        self.assertEqual(C["st"][i0 + 2], "invalid"); self.assertEqual(L["st"][i0 + 1], "invalid")

    def test_local_invalid_duplicate_does_not_rescue(self):
        # "the local snapshot" is the one the local report counts (the first); a later valid local duplicate is not used
        H = "2026-11-06T10:00:00"; t = slot_time(H, 0)
        write_snapshot(self.L, t, valid=False); write_snapshot(self.L, t + 30); write_snapshot(self.C, t + 5)
        g, L, C, M = self.series("2026-11-06T11:00:00+00:00")
        self.assertEqual(M["pick"][g.slot(t)]["src"], "cloud")

class EightyPercentRule(Base):
    def setUp(self):
        super().setUp()
        # Event closing 11-07 22:00Z: its 360 slots run from 11-06 16:03 to 11-07 21:58. Local misses 7 h (84 slots);
        # the cloud covers that hole, so local alone has 276 valid (< 288) and the merged series has all 360.
        H = "2026-11-06T16:00:00"
        self.hole = range(96, 180)
        for k in range(360):
            if k not in self.hole: write_snapshot(self.L, slot_time(H, k))
        for k in range(90, 186): write_snapshot(self.C, slot_time(H, k) + 3, source="github-actions")
        self.now = "2026-11-07T23:00:00+00:00"

    def test_merged_qualifies_local_fails(self):
        g, L, C, M = self.series(self.now)
        ev = {"KXBTCD-26NOV0717": dt.datetime.fromisoformat("2026-11-07T22:00:00+00:00").timestamp()}
        (l,), (c,), (m,) = (status.event_table(x, g, ev) for x in (L, C, M))
        self.assertEqual((l["ws"], l["good"], l["need"]), (360, 276, 288))
        self.assertFalse(l["qualifies"]); self.assertEqual(l["tag"], "FAILED")
        self.assertEqual(c["good"], 96); self.assertFalse(c["qualifies"])
        self.assertEqual(m["good"], 360); self.assertTrue(m["qualifies"]); self.assertEqual(m["tag"], "QUALIFIES")

    def test_gaps_over_six_hours(self):
        g, L, C, M = self.series(self.now)
        over = lambda s: [(w["a"], w["b"]) for w in status.outage_windows(s) if w["b"] - w["a"] + 1 > status.GAP_LIMIT]
        self.assertEqual(len(over(L)), 1); self.assertEqual(over(L)[0][1] - over(L)[0][0] + 1, 84)
        self.assertEqual(over(M), [])

    def test_report_output(self):
        out = run("--now", self.now, "--data", self.L, "--cloud", os.path.dirname(self.C), "--cache-dir", self.tmp)
        self.assertIn("=== detailed report on the merged series", out)
        self.assertIn("KXBTCD-26NOV0717                 close 11-07 22:00Z  valid 360/360  future 0  QUALIFIES", out)
        self.assertIn("valid slots taken from local 276, from cloud 84", out)
        cmp = out.split("== Sources compared")[1]
        self.assertIn("local   first snapshot 11-06 16:03Z", cmp); self.assertIn("gaps over 6 h 1", cmp.splitlines()[2])
        self.assertIn("gap over 6 h: 11-07 00:03Z to 11-07 07:03Z  84 slots (7.0 h)", cmp)
        self.assertRegex(cmp, r"KXBTCD-26NOV0717\s+276\s+96\s+360\s+QUALIFIES")
        # the detailed sections can describe one source instead, without changing which series the rule uses
        out = run("--now", self.now, "--data", self.L, "--cloud", self.C, "--cache-dir", self.tmp, "--source", "local")
        self.assertIn("detailed report on the local series (reference only", out)
        self.assertIn("valid 276/360  future 0  FAILED", out)
        self.assertRegex(out.split("== Sources compared")[1], r"KXBTCD-26NOV0717\s+276\s+96\s+360\s+FAILED")

    def test_local_only_mode_unchanged(self):
        out = run("--now", self.now, "--data", self.L, "--cache-dir", self.tmp)
        self.assertTrue(out.startswith("snapshots 276 of about"))
        self.assertNotIn("Sources compared", out); self.assertNotIn("cloud", out)
        self.assertIn("valid 276/360  future 0  FAILED", out)
        self.assertIn("84 slots (7.0 h)  none 84  BTC +0.00% across it  OVER 6 H", out)
        with self.assertRaises(SystemExit): run("--now", self.now, "--data", self.L, "--cache-dir", self.tmp, "--source", "merged")

class CloudDir(Base):
    def test_accepts_checkout_or_data_folder(self):
        write_snapshot(self.C, slot_time("2026-11-06T10:00:00", 0))
        root = os.path.dirname(self.C)
        self.assertEqual(status.cloud_data_dir(root), self.C)
        self.assertEqual(status.cloud_data_dir(self.C), self.C)

    def test_cloud_only(self):
        write_snapshot(self.C, slot_time("2026-11-06T10:00:00", 0))
        out = run("--now", "2026-11-06T11:00:00+00:00", "--data", self.L, "--cloud", self.C, "--cache-dir", self.tmp)
        self.assertIn("no local run log", out); self.assertIn("detailed report on the cloud series", out)

if __name__ == "__main__":
    unittest.main()
