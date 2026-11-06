# Stage 3 red-team power simulation. SYNTHETIC DATA ONLY: no snapshot, price or outcome from stage 2 (or anything
# real) is read. Companion to power_sim.py; see REVIEW.md for what it found.
#
#   python3 docs/stage3/power_sim_redteam.py --out docs/stage3/power_results_redteam.json   # full run, ~15 min / 4 cores
#   python3 docs/stage3/power_sim_redteam.py --quick                                         # CI smoke test
#
# What it adds to power_sim.py's world, one switch each (all parameters are assumptions, none fitted to data):
#   ASYNC   The recorder pulls Deribit before Kalshi (as stage 2's record_snapshot.py does), so p_opt's spot is up to
#           ASYNC seconds older than the Kalshi quote. power_sim.py evaluates both at the same instant.
#   HEDGE   Where the hedge starts:
#             "kalshi"  exactly at the Kalshi quote's instant (unattainable, power_sim.py's implicit choice)
#             "before"  the index read just before the Kalshi pull, i.e. the same information p_opt used
#             "grid"    the 1-minute index poll at or before the snapshot (the draft pre-registration's wording)
#             "after"   the index read just after the Kalshi response, with p_opt using only earlier data (the fix)
#   AVG     Kalshi settles on a 60-second average (CF Benchmarks), not the index at the close. The truth knows; p_opt
#           and the hedge don't.
#   BASIS   p_opt's forward is off by a per-day, per-coin log error (Deribit index and the 08:00 expiry's forward
#           against the CF settlement index), sd BASIS. The truth (Kalshi's information) has no such error.
#   INTRA   Intraday volatility: a UTC-hour seasonal profile times an hourly lognormal factor, shared by both coins.
#           The truth knows it; p_opt uses the day's level (it scales a daily expiry's variance, no intraday clock).
#   JUMPS   Jumps at common times for BTC and ETH, sizes correlated 0.8 (power_sim.py draws them independently).
#   HALF    Half spread (power_sim.py fixes 1c). STALE: Kalshi's quote reflects spot STALE seconds earlier (a real
#           but latency-dependent edge: a slow quote that a fast taker could pick off).
#   P_OPT   Lognormal digital from a central difference of Black calls with h = $50 (BTC) / $2.50 (ETH), as stage 2's
#           fitter does, so the smoothing bias of a fixed h at minutes-to-close is included.
#
# The truth is exact for this generator: settlement = geometric mean of the path's last minute (a Brownian bridge
# average), jumps only before the last minute, so P(settle > K) is a Poisson mixture of normals (checked by Monte Carlo
# in --quick). With delta = 0, Kalshi's mid equals the truth at its own instant, so there is no edge at all.
#
# Test (the draft pre-registration's T1): ratio estimate with a day-clustered SE, one-sided 95% t with days-1 df.
#   PASS = hedged lower bound > 0 AND unhedged mean > 0.   KILL = fewer than 200 trades OR hedged upper bound < 1c.
import argparse, math, os, json
import numpy as np
from concurrent.futures import ProcessPoolExecutor

MIN_Y = 1 / (365 * 1440)                       # one minute in years
SEC_Y = MIN_Y / 60
VOL0, VOL_SD_LOG, RHO = 0.50, 0.30, 0.80
S0 = {"BTC": 76000.0, "ETH": 2600.0}
VOLX = {"BTC": 1.0, "ETH": 1.25}
STEP = {"BTC": 100 / 76000, "ETH": 5 / 2600}   # real hourly strike spacing (discover_series.py: $100 and $5)
H_DIFF = {"BTC": 50 / 76000, "ETH": 2.5 / 2600}
NOISE = 0.005
JUMP_LAM, JUMP_SD = 6.0, 0.006                 # per day; jump sd for BTC (ETH scaled by VOLX)
MIN_TRADES, E_MIN = 200, 0.01
# variance multiplier by UTC hour (mean 1): quiet Asia, busy US open and data hours. An assumption, not measured.
SEASON = np.array([0.8, 0.75, 0.7, 0.7, 0.7, 0.75, 0.8, 0.85, 0.9, 0.9, 0.95, 1.0,
                   1.15, 1.6, 1.7, 1.5, 1.3, 1.2, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85])
SEASON = SEASON / SEASON.mean()
INTRA_SD = 0.30                                # hourly lognormal factor on variance


def erf(x):
    # Abramowitz-Stegun 7.1.26, max error 1.5e-7 (numpy has no erf; scipy is not a dependency here)
    s = np.sign(x); x = np.abs(x); t = 1 / (1 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return s * y


def ncdf(x): return 0.5 * (1 + erf(np.asarray(x) / math.sqrt(2)))
def npdf(x): return np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def p_true(S, K, tau_min, sd_rate, lam_min, sj, avg):
    """Exact P(settlement > K) for this generator. tau_min: minutes to close; sd_rate: diffusion vol per sqrt(minute);
    lam_min: jumps per minute; jumps happen only before the last minute. avg: settlement = bridge average of the
    last minute (variance 1/3 minute instead of 1, drift likewise) instead of the point at the close."""
    v2 = sd_rate * sd_rate
    if avg:
        var0, mu0 = v2 * (tau_min - 1 + 1 / 3), -0.5 * v2 * (tau_min - 1) - 0.25 * v2
    else:
        var0, mu0 = v2 * tau_min, -0.5 * v2 * tau_min
    m = lam_min * max(tau_min - 1, 0); x = np.log(S / K)
    if m == 0:
        return ncdf((x + mu0) / math.sqrt(var0))
    out = 0.0; w = math.exp(-m)
    for j in range(int(m + 8 * math.sqrt(m) + 6)):
        v = var0 + j * sj * sj
        out = out + w * ncdf((x + mu0 - 0.5 * j * sj * sj) / math.sqrt(v))
        w *= m / (j + 1)
    return out


def black_call(F, K, w):
    sd = np.sqrt(w); d1 = (np.log(F / K) + 0.5 * w) / sd
    return F * ncdf(d1) - K * ncdf(d1 - sd)


def p_opt_fn(F, K, w, hfrac):
    h = hfrac * F
    return (black_call(F, K - h, w) - black_call(F, K + h, w)) / (2 * h)


def sim_day(args):
    seed, c = args
    rng = np.random.default_rng(seed)
    coins = c["coins"]; jumps = c["jumps"]; avg = c["avg"]
    sigd = VOL0 * math.exp(rng.normal(-0.5 * VOL_SD_LOG ** 2, VOL_SD_LOG))      # annual vol, BTC
    err = math.exp(rng.normal(0, c["volerr"])) if c["volerr"] else 1.0
    if c["intra"]:
        mult = SEASON * np.exp(rng.normal(-0.5 * INTRA_SD ** 2, INTRA_SD, 24))
    else:
        mult = np.ones(24)
    lam_min = JUMP_LAM / 1440 if jumps else 0.0
    # shared random drivers: diffusion (correlated), jump times (common), jump sizes (correlated)
    zb = rng.normal(size=(24, 60)); ze = RHO * zb + math.sqrt(1 - RHO ** 2) * rng.normal(size=(24, 60))
    nj = rng.poisson(lam_min, (24, 60)) if jumps else np.zeros((24, 60), int)
    nj[:, 59] = 0                                             # no jumps in the last minute of an hour (exact truth)
    jb = rng.normal(size=(24, 60)); je = 0.8 * jb + 0.6 * rng.normal(size=(24, 60))
    tot = {"n": 0, "p": 0.0, "h": 0.0, "g": 0.0, "ev": 0.0}
    for coin, z, jz in (("BTC", zb, jb), ("ETH", ze, je)):
        if coin not in coins: continue
        sig_ann = sigd * VOLX[coin]; sj = JUMP_SD * VOLX[coin] if jumps else 0.0
        efwd = rng.normal(0, c["basis"]) if c["basis"] else 0.0       # p_opt's forward error, this coin, this day
        sig_opt = sig_ann * err                                         # p_opt's vol: the day's level, no clock
        S = S0[coin] * math.exp(rng.normal(0, 0.02))
        for hr in range(24):
            var_rate = sig_ann ** 2 * mult[hr] * MIN_Y                  # total variance per minute this hour
            dvar = max(var_rate - lam_min * sj * sj, 0.05 * var_rate)   # diffusion part (total kept where possible)
            sd = math.sqrt(dvar)
            inc = sd * z[hr] - 0.5 * dvar + nj[hr] * (-0.5 * sj * sj) + np.sqrt(nj[hr]) * sj * jz[hr]
            path = S * np.exp(np.concatenate([[0.0], np.cumsum(inc)]))  # minutes 0..60 of this hour
            S = path[-1]
            if avg:
                settle = math.exp(0.5 * (math.log(path[59]) + math.log(path[60])) + sd * math.sqrt(1 / 12) * rng.normal())
            else:
                settle = path[60]
            ref = path[0]; step = STEP[coin] * ref
            K = np.round(ref / step) * step + step * np.arange(-70, 71) - 1e-6 * step
            sgn = rng.choice((-1.0, 1.0)); taken = np.zeros(len(K), bool)
            for i in range(0, 60, 5):                                   # snapshots at 60, 55, ..., 5 minutes to close
                tau = 60 - i
                SK = path[i]
                if c["stale"]:                                          # Kalshi's quote reflects an earlier spot
                    SQ = SK * math.exp(sd * math.sqrt(c["stale"] / 60) * rng.normal())
                else:
                    SQ = SK
                pt_now = p_true(SK, K, tau, sd, lam_min, sj, avg)
                pq = p_true(SQ, K, tau, sd, lam_min, sj, avg) if c["stale"] else pt_now
                if c["taper"]:   # full delta for 0.1 <= p <= 0.9, tapering linearly to 0 at p = 0 and p = 1
                    raw = pq + sgn * c["delta"] * np.minimum(1.0, np.minimum(pq, 1 - pq) / 0.1)
                else:            # power_sim.py's constant offset (puts a 99.9% contract at 94c: near-riskless trades)
                    raw = pq + sgn * c["delta"]
                mid = np.clip(np.round(raw * 100) / 100 if c["round"] else raw, 0.02, 0.98)
                ok = (mid >= 0.06) & (mid <= 0.94) & ~taken
                if not ok.any(): continue
                bid, ask = mid - c["half"], mid + c["half"]
                # p_opt's spot: read d_D seconds before the Kalshi quote (chain and index pulled first)
                dD = rng.uniform(0, c["async"]) if c["async"] else 0.0
                SD = SK * math.exp(-sd * math.sqrt(dD / 60) * rng.normal()) if dD else SK
                w = sig_opt ** 2 * tau * MIN_Y
                po = p_opt_fn(SD * math.exp(efwd), K, w, H_DIFF[coin])
                po = np.clip(po + rng.normal(0, NOISE) + rng.normal(0, NOISE, len(K)), 0, 1)
                fee_a = c["fee"](ask); fee_b = c["fee"](1 - bid)
                gy = po - ask - fee_a; gn = (1 - po) - (1 - bid) - fee_b
                g = np.maximum(gy, gn); hit = np.nonzero(ok & (g > c["tau"]))[0]
                if not len(hit): continue
                taken[hit] = True
                yes = gy[hit] >= gn[hit]; Kh = K[hit]; win = settle > Kh
                price = np.where(yes, ask[hit], 1 - bid[hit]); fee = np.where(yes, fee_a[hit], fee_b[hit])
                payoff = np.where(yes, win, ~win).astype(float)
                r = payoff - price - fee
                ev = np.where(yes, pt_now[hit], 1 - pt_now[hit]) - price - fee      # true expected P&L at the quote
                sign = np.where(yes, 1.0, -1.0)
                # hedge start
                hs = c["hedge"]
                if hs == "kalshi":
                    Sh, k0 = SK, i
                elif hs == "before":
                    Sh, k0 = SD, i
                elif hs == "grid":                                     # last 1-minute poll, 0..60 s before the quote
                    dg = rng.uniform(0, 60)
                    if dg >= dD:
                        Sh = SD * math.exp(-sd * math.sqrt(max(dg - dD, 0) / 60) * rng.normal())
                    else:                                              # between p_opt's read and the quote: bridge
                        f = dg / dD; lK, lD = math.log(SK), math.log(SD)
                        Sh = math.exp(lK + f * (lD - lK) + sd * math.sqrt(dg * (dD - dg) / dD / 60) * rng.normal())
                    k0 = i
                elif hs == "after":                                    # index read 0.2..1.5 s after the quote
                    f = rng.uniform(0.2, 1.5) / 60; l0, l1 = math.log(path[i]), math.log(path[i + 1])
                    Sh = math.exp(l0 + f * (l1 - l0) + sd * math.sqrt(f * (1 - f)) * rng.normal()); k0 = i + 1
                else:
                    raise ValueError(hs)
                # delta-hedge with p_opt's model (its vol and forward error): first step Sh -> path[k0], then 1-minute grid
                pts = np.concatenate([[Sh], path[k0:61]])
                tleft = np.concatenate([[60 - i if hs != "after" else 60 - i - f * 60], np.arange(60 - k0, -1, -1)])
                hsum = np.zeros(len(hit))
                for a in range(len(pts) - 1):
                    tl = tleft[a]
                    if tl <= 0: break
                    sdk = sig_opt * math.sqrt(tl * MIN_Y); Fk = pts[a] * math.exp(efwd)
                    d2 = (np.log(Fk / Kh) - 0.5 * sdk * sdk) / sdk
                    hsum += npdf(d2) / (pts[a] * sdk) * (pts[a + 1] - pts[a])
                hp = r - sign * hsum
                tot["n"] += len(hit); tot["p"] += r.sum(); tot["h"] += hp.sum(); tot["g"] += g[hit].sum(); tot["ev"] += ev.sum()
    return tot


def fee_std(q): return 0.07 * q * (1 - q)
def fee_cent(q): return np.ceil(np.round(0.07 * q * (1 - q) * 100, 9)) / 100     # rounded up to the cent, 1 contract
def fee_zero(q): return np.zeros_like(q)
FEES = {"std": fee_std, "cent": fee_cent, "zero": fee_zero}


def base_cfg(**kw):
    c = dict(coins=("BTC", "ETH"), delta=0.0, tau=0.01, half=0.01, fee="std", round=True, async_=0.0, hedge="kalshi",
             volerr=0.15, jumps=True, intra=False, basis=0.0, avg=False, stale=0.0, taper=False)
    c.update(kw); return c


def run_pool(cfg, ndays, seed0, workers):
    c = dict(cfg); c["fee"] = FEES[cfg["fee"]]; c["async"] = cfg["async_"]
    jobs = [(seed0 + d, c) for d in range(ndays)]
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(sim_day, jobs, chunksize=4))
    return {k: np.array([r[k] for r in res], float) for k in ("n", "p", "h", "g", "ev")}


def ratio(n, x):
    N, X = n.sum(-1), x.sum(-1); mu = X / np.maximum(N, 1); D = n.shape[-1]
    se = np.sqrt(D / (D - 1) * ((x - mu[..., None] * n) ** 2).sum(-1)) / np.maximum(N, 1)
    return mu, se, N


def tcrit(df, z=1.6448536269514722):
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df * df)


def power(P, days_list, reps, rng):
    out = []
    for D in days_list:
        idx = rng.integers(0, len(P["n"]), size=(reps, D))
        n = P["n"][idx]
        mh, sh, N = ratio(n, P["h"][idx]); mp, sp, _ = ratio(n, P["p"][idx]); t = tcrit(D - 1)
        enough = N >= MIN_TRADES
        out.append({"days": D,
                    "pass_T1": float(np.mean(enough & (mh - t * sh > 0) & (mp > 0))),
                    "pass_hedged_only": float(np.mean(enough & (mh - t * sh > 0))),
                    "pass_unhedged_lb": float(np.mean(enough & (mp - t * sp > 0))),
                    "kill": float(np.mean(~enough | (mh + t * sh < E_MIN)))})
    return out


def summary(P):
    n = P["n"]; N = n.sum()
    mu_h, mu_p = P["h"].sum() / N, P["p"].sum() / N
    sdd = lambda x, mu: float(np.std(x - mu * n, ddof=1) / n.mean())
    return {"trades_per_day": round(float(n.mean()), 1), "true_net_edge_c": round(float(P["ev"].sum() / N * 100), 2),
            "hedged_mean_c": round(float(mu_h * 100), 2), "unhedged_mean_c": round(float(mu_p * 100), 2),
            "exante_gap_c": round(float(P["g"].sum() / N * 100), 2),
            "sd_day_hedged_c": round(sdd(P["h"], mu_h) * 100, 2), "sd_day_unhedged_c": round(sdd(P["p"], mu_p) * 100, 2)}


WORLDS = {
    # power_sim.py's rough world with real strike spacing and common jumps; zero timing error, hedge at the quote
    "design-rough": dict(),
    # the same plus the effects the design leaves out, hedge started as the draft pre-registration says
    "redteam-as-drafted": dict(async_=5.0, hedge="grid", intra=True, basis=0.0002, avg=True),
    # the same world with the timing fix: p_opt from data read before the Kalshi pull, hedge from the index after it
    "redteam-fixed": dict(async_=5.0, hedge="after", intra=True, basis=0.0002, avg=True),
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--out")
    ap.add_argument("--taper-only", action="store_true",
                    help="run only the tapered-mispricing grid and add it to --out")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args(); rng = np.random.default_rng(20261106)
    res = {"size": [], "power": [], "params": {"VOL0": VOL0, "RHO": RHO, "NOISE": NOISE, "JUMP_LAM": JUMP_LAM,
           "JUMP_SD": JUMP_SD, "INTRA_SD": INTRA_SD, "SEASON": SEASON.round(3).tolist(), "basis_sd": 0.0002}}

    if a.taper_only:
        res = json.load(open(a.out)); res["power_taper"] = []
        grid = [("design-rough", 0.01, (0.04, 0.05, 0.06)), ("redteam-fixed", 0.01, (0.04, 0.05, 0.06, 0.08)),
                ("redteam-fixed", 0.02, (0.05, 0.06, 0.08, 0.10))]
        for w, half, deltas in grid:
            for dl in deltas:
                cfg = base_cfg(half=half, delta=dl, taper=True, **WORLDS[w])
                P = run_pool(cfg, 600, 10_000 * (1 + round(dl * 100)) + round(half * 1e5), a.workers)
                row = {"world": w, "taper": True, "half_c": round(half * 100), "delta_c": round(dl * 100), **summary(P),
                       "curve": power(P, (14, 21, 28, 42, 56), 4000, rng)}
                res["power_taper"].append(row); print(json.dumps(row), flush=True)
        with open(a.out, "w") as fh: json.dump(res, fh, indent=1)
        return
    if a.quick:
        # 1) the exact truth matches a Monte Carlo of the generator (bridge-averaged settlement, jumps, 30 min)
        mc = np.random.default_rng(1); m = 400_000; sd = 0.5 * math.sqrt(MIN_Y); lam = JUMP_LAM / 1440; sj = JUMP_SD
        S0b, Ks, T = 76000.0, np.array([75800.0, 76000.0, 76250.0]), 30
        njs = mc.poisson(lam * (T - 1), m)
        x59 = sd * math.sqrt(T - 1) * mc.normal(size=m) - 0.5 * sd * sd * (T - 1) - 0.5 * sj * sj * njs + np.sqrt(njs) * sj * mc.normal(size=m)
        x60 = x59 + sd * mc.normal(size=m) - 0.5 * sd * sd
        xa = 0.5 * (x59 + x60) + sd * math.sqrt(1 / 12) * mc.normal(size=m)
        emp = np.array([(S0b * np.exp(xa) > k).mean() for k in Ks]); th = p_true(S0b, Ks, T, sd, lam, sj, True)
        assert np.all(np.abs(emp - th) < 0.003), (emp, th)
        print("truth vs Monte Carlo ok", emp.round(4), np.asarray(th).round(4))
        ndays, reps, days_list = 120, 1000, (28,)
    else:
        ndays, reps, days_list = 600, 4000, (14, 21, 28, 42, 56)

    # SIZE: a frictionless exact null (no spread, no fee, no rounding, delta 0), so the true net edge is exactly 0 and
    # a 5% test should pass about 5% of the time. Only the timing/hedge choice varies.
    size_cases = [("no timing error, hedge at quote", dict(hedge="kalshi")),
                  ("5 s async, hedge from index before Kalshi", dict(async_=5.0, hedge="before")),
                  ("5 s async, hedge from 1-min grid (as drafted)", dict(async_=5.0, hedge="grid")),
                  ("5 s async, p_opt before + hedge after (fix)", dict(async_=5.0, hedge="after"))]
    size_cases.append(("30 s async, hedge from index before Kalshi", dict(async_=30.0, hedge="before")))
    if a.quick: size_cases = [size_cases[1], size_cases[3]]
    for lab, kw in size_cases:
        # the same seeds for every case (common random numbers), so differences between cases are the timing effect
        cfg = base_cfg(half=0.0, fee="zero", round=False, intra=True, basis=0.0002, avg=True, **kw)
        P = run_pool(cfg, ndays if a.quick else 2 * ndays, 900_000, a.workers)
        row = {"case": lab, **summary(P), "curve": power(P, days_list, reps, rng)}
        res["size"].append(row); print(json.dumps(row), flush=True)

    if a.quick:
        b, f = res["size"]
        # same seeds: hedging from the pre-Kalshi index must read higher than the fix, and the fix must be near 0
        assert b["hedged_mean_c"] > f["hedged_mean_c"], (b, f)
        assert abs(f["hedged_mean_c"] - f["true_net_edge_c"]) < 0.5, f
        print("quick checks passed")
    else:
        grid = [("design-rough", 0.01, (0.0, 0.04, 0.05)),
                ("redteam-as-drafted", 0.01, (0.0, 0.04, 0.05)),
                ("redteam-fixed", 0.01, (0.0, 0.04, 0.05, 0.06)),
                ("redteam-fixed", 0.02, (0.04, 0.05, 0.06, 0.08)),
                ("redteam-fixed", 0.03, (0.06, 0.08))]
        for w, half, deltas in grid:
            for dl in deltas:
                cfg = base_cfg(half=half, delta=dl, **WORLDS[w])
                P = run_pool(cfg, ndays, 10_000 * (1 + round(dl * 100)) + round(half * 1e5), a.workers)
                row = {"world": w, "half_c": round(half * 100), "delta_c": round(dl * 100), **summary(P),
                       "curve": power(P, days_list, reps, rng)}
                res["power"].append(row); print(json.dumps(row), flush=True)
        # fee rounded up to the cent on 1-contract orders, and stale quotes (latency-dependent edge), in the fixed world
        for lab, kw in (("fee rounded up to 1c", dict(fee="cent", delta=0.05)),
                        ("stale Kalshi quotes 3 s, delta 0", dict(stale=3.0)),
                        ("BTC only", dict(coins=("BTC",), delta=0.05))):
            cfg = base_cfg(half=0.01, **{**WORLDS["redteam-fixed"], **kw})
            P = run_pool(cfg, ndays, 700_000 + hash(lab) % 1000, a.workers)
            row = {"world": "redteam-fixed", "variant": lab, "half_c": 1, "delta_c": round(cfg["delta"] * 100),
                   **summary(P), "curve": power(P, days_list, reps, rng)}
            res["power"].append(row); print(json.dumps(row), flush=True)
    if a.out:
        with open(a.out, "w") as fh: json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
