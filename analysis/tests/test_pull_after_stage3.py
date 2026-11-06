# Settlement pull: markets that Kalshi has moved to /historical/markets are still found. Fake HTTP only.
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pull_after_stage3 as p3  # noqa: E402


def fake(live, hist, hist_error=None):
    calls = []

    def get(path, q):
        calls.append((path, q.get("event_ticker")))
        if path == "/historical/markets" and hist_error:
            return {"_error": hist_error}
        src = live if path == "/markets" else hist
        return {"markets": src.get(q["event_ticker"], []), "cursor": ""}
    return get, calls


class TestSettlements(unittest.TestCase):
    def test_live_settled_needs_no_historical_call(self):
        get, calls = fake({"E1": [{"ticker": "E1-T1", "result": "yes"}]}, {})
        m, errs = p3.settlements({"E1"}, get)
        self.assertEqual(m["E1-T1"]["result"], "yes"); self.assertEqual(errs, [])
        self.assertEqual([c[0] for c in calls], ["/markets"])

    def test_archived_event_comes_from_historical(self):
        get, _ = fake({}, {"E1": [{"ticker": "E1-T1", "result": "no"}, {"ticker": "E1-T2", "result": "yes"}]})
        m, errs = p3.settlements({"E1"}, get)
        self.assertEqual({k: v["result"] for k, v in m.items()}, {"E1-T1": "no", "E1-T2": "yes"})
        self.assertEqual(m["E1-T1"]["source"], "historical")

    def test_live_result_is_not_overwritten(self):
        get, _ = fake({"E1": [{"ticker": "E1-T1", "result": "yes"}, {"ticker": "E1-T2", "result": ""}]},
                      {"E1": [{"ticker": "E1-T1", "result": "no"}, {"ticker": "E1-T2", "result": "no"}]})
        m, _ = p3.settlements({"E1"}, get)
        self.assertEqual(m["E1-T1"]["result"], "yes"); self.assertEqual(m["E1-T2"]["result"], "no")

    def test_historical_error_is_recorded_not_filled(self):
        get, _ = fake({"E1": [{"ticker": "E1-T1", "result": ""}]}, {}, hist_error=404)
        m, errs = p3.settlements({"E1"}, get)
        self.assertEqual(m["E1-T1"]["result"], ""); self.assertEqual(errs, ["E1: 404"])


if __name__ == "__main__":
    unittest.main()
