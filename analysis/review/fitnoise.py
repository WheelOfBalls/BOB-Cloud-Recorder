# Review experiment (synthetic only): p_opt error with realistic Deribit ticks, all options vs out-of-the-money only.
# Run from a git checkout: python3 analysis/review/fitnoise.py
# "all" uses the pre-review fit_chain (commit afe5e4c, in-the-money included), "otm" the current one.
import sys, math, random, datetime as dt
import os; R = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."); sys.path[:0] = [R, os.path.join(R, "tests")]
import analyze_stage2 as A, make_fixture as MF, subprocess, types
OLD = types.ModuleType("old"); exec(subprocess.check_output(["git", "-C", R, "show", "afe5e4c:analysis/analyze_stage2.py"]), OLD.__dict__)
def tick(p): return 0.0001 if p < 0.005 else 0.0005
def rnd(p, t, up): return (math.ceil if up else math.floor)(p / t - 1e-9 * (1 if up else -1)) * t
def chain(F, t, exps, rng, sp_abs, sp_rel):
    out = []
    for e in exps:
        tau = (e - t) / A.YEAR_S
        if tau <= 0: continue
        d = dt.datetime.fromtimestamp(e, A.UTC).strftime("%d%b%y").upper().lstrip("0")
        for K in range(int(round(F / 1000) * 1000) - 10000, int(round(F / 1000) * 1000) + 10001, 1000):
            for cp in "CP":
                px = MF.black(F, K, MF.true_w(math.log(K / F), tau), cp == "C") / F
                if px < 0.0001: continue
                s = max(tick(px), sp_abs + sp_rel * px)
                u = rng.random()
                b, a = rnd(px - u * s, tick(px), False), rnd(px + (1 - u) * s, tick(px), True)
                if b <= 0: continue
                out.append({"instrument_name": f"BTC-{d}-{K}-{cp}", "bid_price": b, "ask_price": a, "mark_iv": 50, "underlying_price": F})
    return out
def otm(opts):
    r = []
    for o in opts:
        _, K, call = A.parse_instrument(o["instrument_name"])
        if (call and K >= o["underlying_price"]) or (not call and K < o["underlying_price"]): r.append(o)
    return r
rng = random.Random(5)
F = 76000.0
for sp_abs, sp_rel in ((0.0002, 0.0), (0.0005, 0.01), (0.0005, 0.03)):
    for hhmm in ("02:00", "07:30", "07:55", "12:00", "21:00"):
        for flt in ("all", "otm"):
            errs = []
            for rep in range(15):
                t = A.iso_ts(f"2026-11-06T{hhmm}:00Z")
                e1, e2, e3 = (A.iso_ts(f"2026-11-0{d}T08:00:00Z") for d in (6, 7, 8))
                opts = chain(F, t, [e1, e2, e3], rng, sp_abs, sp_rel)
                fits = (A if flt == "otm" else OLD).fit_chain(opts, t)
                close = A.iso_ts("2026-11-06T22:00:00Z") if hhmm < "22" else None
                tauT = (close - t) / A.YEAR_S
                sd = math.sqrt(0.25 * tauT) * F
                for z in (-1.5, -0.75, 0, 0.75, 1.5):
                    K = F + z * sd
                    p = A.p_above(fits, K, close, t)
                    errs.append(abs(p - MF.true_p(F, K, tauT)) if p is not None else 9)
            errs.sort()
            print(f"spread {sp_abs}+{sp_rel:.0%}  t {hhmm}  {flt:3s}  median |err| {errs[len(errs)//2]*100:.2f}c  p90 {errs[int(.9*len(errs))]*100:.2f}c  max {errs[-1]*100:.2f}c")
