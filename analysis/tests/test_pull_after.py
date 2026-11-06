# Tests for the settlement pull in pull_after.py, on mocked API responses only. Nothing here touches the network
# or reads a real outcome.
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pull_after as P
import analyze_stage2 as A


def mkt(ticker, result, ev="KXBTCD-26NOV0617"):
    return {"ticker": ticker, "event_ticker": ev, "status": "settled" if result else "closed", "result": result,
            "close_time": "2026-11-06T22:00:00Z", "floor_strike": 1.0, "strike_type": "greater", "extra": "dropped"}


class FakeAPI:
    """Serves /markets and /historical/markets from dicts {event: [pages of markets]} and records every call."""
    def __init__(self, live, hist, errors=None):
        self.data = {"/markets": live, "/historical/markets": hist}
        self.errors = errors or {}
        self.calls = []

    def __call__(self, path, q):
        self.calls.append((path, q.get("event_ticker"), q.get("cursor")))
        if (path, q["event_ticker"]) in self.errors:
            return {"_error": self.errors[(path, q["event_ticker"])]}
        pages = self.data[path].get(q["event_ticker"], [[]])
        i = int(q.get("cursor") or 0)
        return {"markets": pages[i], "cursor": str(i + 1) if i + 1 < len(pages) else ""}


class Settlements(unittest.TestCase):
    def test_live_settled_needs_no_historical_call(self):
        api = FakeAPI({"E1": [[mkt("E1-T1", "yes", "E1"), mkt("E1-T2", "no", "E1")]]}, {})
        m, errs = P.settlements({"E1"}, api)
        self.assertEqual({k: v["result"] for k, v in m.items()}, {"E1-T1": "yes", "E1-T2": "no"})
        self.assertEqual([c[0] for c in api.calls], ["/markets"])
        self.assertNotIn("extra", m["E1-T1"]); self.assertNotIn("source", m["E1-T1"]); self.assertEqual(errs, [])

    def test_event_moved_to_historical(self):
        # past the cutoff, /markets returns nothing for the event
        api = FakeAPI({}, {"E1": [[mkt("E1-T1", "no", "E1"), mkt("E1-T2", "yes", "E1")]]})
        m, errs = P.settlements({"E1"}, api)
        self.assertEqual({k: (v["result"], v["source"]) for k, v in m.items()},
                         {"E1-T1": ("no", "historical"), "E1-T2": ("yes", "historical")})

    def test_partly_unsettled_live_is_filled_from_historical(self):
        api = FakeAPI({"E1": [[mkt("E1-T1", "yes", "E1"), mkt("E1-T2", "", "E1")]]},
                      {"E1": [[mkt("E1-T1", "no", "E1"), mkt("E1-T2", "no", "E1")]]})
        m, _ = P.settlements({"E1"}, api)
        self.assertEqual((m["E1-T1"]["result"], m["E1-T1"].get("source")), ("yes", None))   # a live result is kept
        self.assertEqual((m["E1-T2"]["result"], m["E1-T2"]["source"]), ("no", "historical"))

    def test_pagination_on_both_endpoints(self):
        api = FakeAPI({"E1": [[mkt("E1-T1", "yes", "E1")], [mkt("E1-T2", "", "E1")]]},
                      {"E1": [[mkt("E1-T3", "no", "E1")], [mkt("E1-T2", "yes", "E1")]]})
        m, _ = P.settlements({"E1"}, api)
        self.assertEqual({k: v["result"] for k, v in m.items()}, {"E1-T1": "yes", "E1-T2": "yes", "E1-T3": "no"})
        self.assertEqual(sum(1 for c in api.calls if c[0] == "/historical/markets"), 2)

    def test_errors(self):
        api = FakeAPI({}, {}, errors={("/historical/markets", "E1"): 404})
        m, errs = P.settlements({"E1"}, api)
        self.assertEqual((m, errs), ({}, ["E1: 404"]))
        api = FakeAPI({}, {}, errors={("/markets", "E1"): "retries"})
        with self.assertRaises(SystemExit):
            P.settlements({"E1"}, api)

    def test_analysis_reads_the_written_file(self):
        api = FakeAPI({"KXBTCD-26NOV0617": [[mkt("KXBTCD-26NOV0617-T1", "yes")]]},
                      {"KXBTCD-26NOV0517": [[mkt("KXBTCD-26NOV0517-T1", "no", "KXBTCD-26NOV0517")]]})
        m, errs = P.settlements({"KXBTCD-26NOV0617", "KXBTCD-26NOV0517"}, api)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "settlements.json")
            json.dump({"pulled_utc": "x", "markets": m, "historical_errors": errs}, open(p, "w"))
            self.assertEqual(A.load_results(p), {"KXBTCD-26NOV0617-T1": "yes", "KXBTCD-26NOV0517-T1": "no"})


if __name__ == "__main__":
    unittest.main()
