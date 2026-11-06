# End-to-end check of the row-sync selection effect with the frozen analyze_stage3.analyse() on synthetic data.
# World = the test fixture, plus a spot move inside each snapshot: index_before -> Kalshi quote (dq s) -> index_after
# (da s). Kalshi's mid is the truth at the quote instant (a frictionless null, delta = 0). The path after the snapshot
# continues from index_after, so the index is a martingale through every read. After deviation 1: T1 (no row filter) against the
# reference figure that applies the pre-registered row-sync rule. Synthetic only.
import sys, os, math, bisect, random
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "analysis")); sys.path.insert(0, os.path.join(REPO, "analysis", "tests"))
import analyze_stage3 as a3, make_fixture_stage3 as mf

class World2(mf.World):
    def __init__(self, *a, lag=(0.3, 1.5), **k):
        super().__init__(*a, **k)
        self.lag = lag; self.jt = {c: [] for c in mf.COIN}; self.jf = {c: [1.0] for c in mf.COIN}
        self.inside = None
    def S(self, c, t):
        if self.inside and self.inside[0] == c:
            return self.inside[1]
        base = self.path[c][int(round((t - self.t0) / 30))]
        j = bisect.bisect_left(self.jt[c], t)       # jumps strictly before t
        return base * self.jf[c][j]
    def snapshot(self, i):
        t = i * mf.STEP + mf.PHASE
        s = super().snapshot(i)                      # chain, index_before, markets at S(t) for now; redo below
        for c, p in mf.COIN.items():
            sd = p["vol"] / math.sqrt(mf.YEAR)
            Sb = self.S(c, t)
            dq, da = self.rng.uniform(*self.lag), self.rng.uniform(*self.lag)
            Sq = Sb * math.exp(sd * math.sqrt(dq) * self.rng.gauss(0, 1))
            Sa = Sq * math.exp(sd * math.sqrt(da) * self.rng.gauss(0, 1))
            cc = s["coins"][c]
            self.inside = (c, Sq)
            cc["kalshi"]["markets"] = self.markets(c, t + dq)        # truth at the quote instant
            self.inside = None
            cc["kalshi"]["t1"] = cc["kalshi"]["t0"] + dq
            cc["index_after"] = {"t0": cc["kalshi"]["t1"], "t1": cc["kalshi"]["t1"] + da,
                                 "body": {"result": {"index_price": Sa}}}
            self.jt[c].append(t); self.jf[c].append(self.jf[c][-1] * Sa / Sb)
        return s
    def truth(self, c, K, t, close):
        w = mf.COIN[c]["vol"] ** 2 * (close - t) / mf.YEAR
        S = self.S(c, t)
        return mf.ncdf((math.log(S / K) - 0.5 * w) / math.sqrt(w))

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
start = a3.iso_ts(a3.START_UTC)
w = World2(start, 28, delta=0.0, seed=seed, invalid_frac=0.0)
snaps, polls, results, tapes = w.build()
pol = {c: sorted((tg, t0, S) for tg, t0, S in v) for c, v in polls.items()}
o, rows, trades, fills = a3.analyse(snaps, pol, results, tapes, start, start + 28 * 86400)
t1, ref = o["T1"], o["reference"]["T1_with_preregistered_row_sync_rule"]
f = lambda x: f"{x['est']*100:+.2f}c [{x['lo']*100:+.2f}, {x['hi']*100:+.2f}]"
print(f"seed {seed} T1 (deviation 1, no row filter) trades {t1['trades']:5d} hedged {f(t1['hedged'])} "
      f"unhedged {t1['unhedged']['est']*100:+.2f}c -> {t1['verdict']} | reference with the pre-registered row-sync rule: "
      f"trades {ref['trades']:5d} hedged {f(ref['hedged'])}", flush=True)
