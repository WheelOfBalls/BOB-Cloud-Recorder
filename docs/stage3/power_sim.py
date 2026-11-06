# Stage 3 power simulation. SYNTHETIC DATA ONLY: no snapshot, price or outcome from stage 2 is read.
#
#   python3 docs/stage3/power_sim.py            # full run, about 3 to 6 minutes on 4 cores
#   python3 docs/stage3/power_sim.py --quick    # smoke test used by CI
#
# Question: how many days of recording does a taker test need for 80% power when Kalshi is mispriced against the
# true probability, and how much do hourly events, ETH, a threshold and a delta-hedge control variate help?
#
# World (all parameters below, nothing fitted to real data):
#   - BTC (and ETH, correlation RHO) follow GBM on a 1-minute grid. Each day draws its own volatility, lognormal around
#     VOL0, and both the truth and the "options" fair value use that day's volatility, so a zero edge is exactly zero.
#   - Events: hourly (24 a day, each traded in its last 60 minutes, settling on the price at the hour) or daily
#     (one 5pm-style event traded over its last 30 hours, as in stage 2). Strikes every STRIKE_STEP of spot.
#   - Kalshi mid = truth + s * delta, rounded to the cent, quoted +-HALF either side. s = +1 or -1, drawn once per
#     event, so a mispriced event is mispriced the same way at every strike (the hardest case for power, since a
#     day's trades then share one outcome). delta is the "mispricing" in the tables.
#   - p_opt = truth + common noise (per snapshot) + strike noise, both NOISE sd. Stage 2's review put the OTM-only
#     fit at about 0.3 to 0.5c, so 0.5c each is a little pessimistic.
#   - Snapshots every SNAP minutes. Rows: mid in [0.06, 0.94]. Trade rule: for each event and strike, the first row
#     whose better-side gap g (net of the taker fee 0.07 q (1-q)) exceeds TAU, buy 1 contract on that side at the
#     touch. Same as stage 2's S2 when TAU = 0.
#   - Statistic: mean net P&L per contract, pooled over trades, with a cluster-robust standard error where the
#     cluster is a UTC day (all events, both coins). PASS if the one-sided 95% lower bound (Student t, days - 1 df) is > 0. KILL (decisive)
#     if the one-sided 95% upper bound is < the minimum edge the test is sized for (1c), or if there are fewer than
#     MIN_TRADES trades in total. Otherwise INCONCLUSIVE.
#   - "Rough world": the true process adds Poisson jumps (JUMP_LAM a day, sd JUMP_SD) with total vol unchanged, and p_opt
#     uses a plain lognormal with that day's vol times a lognormal error of 15%. The truth is the exact jump-diffusion
#     probability, so a zero mispricing is still exactly zero against the truth while p_opt is now systematically wrong.
#   - Hedged P&L: the same P&L minus the gains of a delta hedge in spot, rebalanced every HEDGE minutes from entry to
#     the close using p_opt's model delta. Spot increments have mean ~0, so this keeps the mean and removes most of
#     the settlement variance. It is a statistical control variate, not an assumed trade.
#
# Power for N days is estimated by resampling N days with replacement from a pool of simulated days.
import argparse, math, os, sys, json
import numpy as np
from concurrent.futures import ProcessPoolExecutor

MIN_Y = 1 / (365 * 1440)
VOL0, VOL_SD_LOG, RHO = 0.50, 0.30, 0.80
S0 = {"BTC": 76000.0, "ETH": 2600.0}
STRIKE_STEP = 0.0033          # strike spacing as a fraction of spot (about $250 on BTC at 76k)
HALF = 0.01                   # half spread
NOISE = 0.005                 # p_opt noise sd, common and per strike
JUMP_LAM, JUMP_SD = 6.0, 0.006   # rough world: 6 jumps a day, each about 0.6% (about a fifth of the variance)
MIN_TRADES = 200              # fewer trades than this over the whole test = KILL (no tradable gaps)
FEE = lambda q: 0.07 * q * (1 - q)
ERF = np.vectorize(math.erf)

def ncdf(x): return 0.5 * (1 + ERF(x / math.sqrt(2)))
def npdf(x): return np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def merton_p(F, K, tau_y, sig_d, lam, sj):
    """P(S_T > K) when log-returns are diffusion (vol sig_d) plus Poisson(lam per year) jumps N(-sj^2/2, sj^2).
    The jump mean makes E[e^J] = 1, so the price stays a martingale. lam = 0 gives the plain lognormal digital."""
    if lam == 0:
        sd = sig_d * math.sqrt(tau_y); return ncdf((np.log(F / K) - 0.5 * sd * sd) / sd)
    m = lam * tau_y; out = 0.0; w = math.exp(-m)
    for j in range(int(m + 8 * math.sqrt(m) + 10)):     # enough terms to hold all but ~1e-12 of the Poisson mass
        v = sig_d * sig_d * tau_y + j * sj * sj
        out = out + w * ncdf((np.log(F / K) - 0.5 * v) / math.sqrt(v))
        w *= m / (j + 1)
    return out

def event_trades(rng, path, K, sig, sigm, t_idx, close_idx, delta, tau, hedge, lam=0.0, sj=0.0):
    """path: 1-minute spot path covering t_idx[0]..close_idx. sig is the true vol, sigm the vol behind p_opt.
    Returns lists, one entry per trade: realised net P&L, hedged net P&L, and the ex-ante gap g (an S1-style figure)."""
    ST = path[close_idx]; s = rng.choice((-1.0, 1.0)); taken = np.zeros(len(K), bool)
    pnl, hpnl, gap = [], [], []
    for i in t_idx:
        tau_y = (close_idx - i) * MIN_Y
        if tau_y <= 0: continue
        F = path[i]; sd = sig * math.sqrt(tau_y); sdm = sigm * math.sqrt(tau_y)
        p = merton_p(F, K, tau_y, sig, lam, sj)
        pm = ncdf((np.log(F / K) - 0.5 * sdm * sdm) / sdm)
        mid = np.clip(np.round((p + s * delta) * 100) / 100, 0.02, 0.98)
        bid, ask = mid - HALF, mid + HALF
        ok = (mid >= 0.06) & (mid <= 0.94) & ~taken
        if not ok.any(): continue
        po = np.clip(pm + rng.normal(0, NOISE) + rng.normal(0, NOISE, len(K)), 0, 1)
        gy = po - ask - FEE(ask); gn = (1 - po) - (1 - bid) - FEE(1 - bid)
        g = np.maximum(gy, gn); hit = ok & (g > tau)
        for j in np.nonzero(hit)[0]:
            taken[j] = True; yes = gy[j] >= gn[j]; win = ST > K[j]
            if yes: r = (1.0 if win else 0.0) - ask[j] - FEE(ask[j]); sign = 1.0
            else:   r = (0.0 if win else 1.0) - (1 - bid[j]) - FEE(1 - bid[j]); sign = -1.0
            # delta hedge: hold -sign * dp/dS units of spot, rebalanced every `hedge` minutes, from i to the close
            h = 0.0; k = i
            while k < close_idx:
                nk = min(k + hedge, close_idx); ty = (close_idx - k) * MIN_Y; sdk = sigm * math.sqrt(ty)
                dk = (math.log(path[k] / K[j]) - 0.5 * sdk * sdk) / sdk
                dlt = math.exp(-0.5 * dk * dk) / math.sqrt(2 * math.pi) / (path[k] * sdk)
                h += sign * dlt * (path[nk] - path[k]); k = nk
            pnl.append(r); hpnl.append(r - h); gap.append(g[j])
    return pnl, hpnl, gap

def sim_day(args):
    seed, kind, coins, delta, tau, snap, hedge, volerr, jumps = args
    rng = np.random.default_rng(seed)
    sig = {"BTC": VOL0 * math.exp(rng.normal(-0.5 * VOL_SD_LOG**2, VOL_SD_LOG))}
    sig["ETH"] = sig["BTC"] * 1.25
    err = math.exp(rng.normal(0, volerr)) if volerr else 1.0     # p_opt's vol is wrong by this factor all day
    n = 24 * 60 + 1 if kind == "hourly" else 30 * 60 + 1
    z1 = rng.normal(size=n - 1); z2 = RHO * z1 + math.sqrt(1 - RHO**2) * rng.normal(size=n - 1)
    out = {"n": 0}
    P = H = G = 0.0
    for coin, z in zip(("BTC", "ETH"), (z1, z2)):
        if coin not in coins: continue
        sg = sig[coin]
        # jumps: LAM per day of size sd SJ; the diffusion keeps the remaining variance, so total vol is unchanged
        lam = JUMP_LAM * 365 if jumps else 0.0; sj = JUMP_SD if jumps else 0.0
        sdiff = math.sqrt(max(sg * sg - lam * sj * sj, 0.01 * sg * sg))
        inc = sdiff * math.sqrt(MIN_Y) * z - 0.5 * sdiff * sdiff * MIN_Y
        if jumps:
            nj = rng.poisson(lam * MIN_Y, n - 1)
            inc = inc + nj * (-0.5 * sj * sj) + np.sqrt(nj) * sj * rng.normal(size=n - 1)
        path = S0[coin] * np.exp(np.concatenate([[0.0], np.cumsum(inc)]))
        if kind == "hourly":
            events = [(60 * e, 60 * (e + 1)) for e in range(24)]
        else:
            events = [(0, n - 1)]
        for a, c in events:
            ref = path[a]; step = STRIKE_STEP * ref
            K = np.round(ref / step) * step + step * np.arange(-40, 41) - 0.01 * step
            t_idx = range(a, c, snap)
            pnl, hp, gp = event_trades(rng, path, K, sdiff if jumps else sg, sg * err, t_idx, c, delta, tau, hedge, lam, sj)
            out["n"] += len(pnl); P += sum(pnl); H += sum(hp); G += sum(gp)
    out["p"], out["h"], out["g"] = P, H, G
    return out

def pool(kind, coins, delta, tau, snap, hedge, volerr, jumps, ndays, seed0, workers):
    jobs = [(seed0 + d, kind, coins, delta, tau, snap, hedge, volerr, jumps) for d in range(ndays)]
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(sim_day, jobs, chunksize=8))
    return (np.array([r["n"] for r in res], float), np.array([r["p"] for r in res]), np.array([r["h"] for r in res]),
            np.array([r["g"] for r in res]))

def decide(n, x, e_min):
    """Ratio estimator with a cluster-robust (day) SE. Returns mean, se."""
    N, X = n.sum(axis=-1), x.sum(axis=-1)
    mu = X / np.maximum(N, 1)
    D = n.shape[-1]
    resid = x - mu[..., None] * n
    se = np.sqrt(D / (D - 1) * (resid**2).sum(axis=-1)) / np.maximum(N, 1)
    return mu, se

def tcrit(df, z=1.6448536269514722):
    """One-sided 95% Student t quantile (Cornish-Fisher; within 0.002 of the exact value for df >= 5)."""
    return z + (z**3 + z) / (4 * df) + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df * df)

def power_curve(n, x, days_list, e_min, reps, rng):
    rows = []
    for D in days_list:
        idx = rng.integers(0, len(n), size=(reps, D))
        mu, se = decide(n[idx], x[idx], e_min)
        N = n[idx].sum(axis=-1); enough = N >= MIN_TRADES
        t = tcrit(D - 1)
        rows.append({"days": D, "pass": float(np.mean(enough & (mu - t * se > 0))),
                     "kill": float(np.mean(~enough | (mu + t * se < e_min))), "mean_c": float(np.mean(mu) * 100),
                     "median_trades": float(np.median(N))})
    return rows

def per_day_stats(n, x):
    mu = x.sum() / n.sum()
    sd_day = np.std(x - mu * n, ddof=1) / n.mean()     # sd of a day's contribution, per average trade count
    return mu, sd_day, n.mean()

def days_needed(mu, sd_day, e_min=None):
    """Days for 80% power, one-sided 5%, at true mean mu, from the per-day sd (normal approximation)."""
    if mu <= 0: return float("inf")
    return ((1.645 + 0.842) * sd_day / mu) ** 2

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    pool_days = 60 if a.quick else 800
    reps = 400 if a.quick else 4000
    rng = np.random.default_rng(20261106)
    # label, kind, coins, tau, snap, hedge, volerr
    # label, kind, coins, tau, snap, hedge, volerr, jumps
    scen = [
        ("daily BTC, tau 0 (stage 2 S2)", "daily", ("BTC",), 0.0, 5, 5, 0.0, False),
        ("daily BTC, tau 0, rough world", "daily", ("BTC",), 0.0, 5, 5, 0.15, True),
        ("hourly BTC, tau 0", "hourly", ("BTC",), 0.0, 5, 1, 0.0, False),
        ("hourly BTC, tau 1c", "hourly", ("BTC",), 0.01, 5, 1, 0.0, False),
        ("hourly BTC+ETH, tau 1c", "hourly", ("BTC", "ETH"), 0.01, 5, 1, 0.0, False),
        ("hourly BTC+ETH, tau 1c, rough world", "hourly", ("BTC", "ETH"), 0.01, 5, 1, 0.15, True),
        ("hourly BTC+ETH, tau 1c, rough world, hedge every 5 min", "hourly", ("BTC", "ETH"), 0.01, 5, 5, 0.15, True),
    ]
    deltas = (0.0, 0.03, 0.04, 0.05)
    if a.quick: scen, deltas = [scen[5]], (0.0, 0.05)
    results, pools = [], {}
    for lab, kind, coins, tau, snap, hedge, volerr, jumps in scen:
        for dl in deltas:
            pd = min(pool_days, 300) if kind == "daily" else pool_days
            n, p, h, g = pool(kind, coins, dl, tau, snap, hedge, volerr, jumps, pd, 10_000 * (1 + round(dl * 100)), a.workers)
            pools[(lab, dl)] = (n, p, h)
            for which, x in (("unhedged", p), ("hedged", h)):
                mu, sdd, tpd = per_day_stats(n, x)
                r = {"scenario": lab, "delta_c": round(dl * 100), "stat": which, "trades_per_day": round(tpd, 1),
                     "net_edge_c": round(mu * 100, 2), "exante_gap_c": round(g.sum() / n.sum() * 100, 2),
                     "sd_day_c": round(sdd * 100, 2),
                     "days_80pct_approx": None if mu <= 0 else round(days_needed(mu, sdd), 1)}
                results.append(r); print(json.dumps(r), flush=True)
    # power curves by resampling days, sized for a minimum net edge of 1c per contract
    curves = {}
    days_list = (7, 14, 21, 28, 42, 56) if not a.quick else (14, 28)
    for (lab, dl), (n, p, h) in pools.items():
        if lab.startswith("daily"): continue
        for which, x in (("hedged", h), ("unhedged", p)):
            key = f"{lab} | {which} | delta={dl*100:.0f}c"
            curves[key] = power_curve(n, x, days_list, 0.01, reps, rng)
            print(key, json.dumps(curves[key]), flush=True)
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"per_day": results, "curves": curves,
                       "params": {"VOL0": VOL0, "VOL_SD_LOG": VOL_SD_LOG, "RHO": RHO, "HALF": HALF, "NOISE": NOISE,
                                  "STRIKE_STEP": STRIKE_STEP, "pool_days": pool_days, "reps": reps}}, f, indent=1)
    if a.quick:
        # the jump-diffusion truth must match a Monte Carlo of the same process (30 h horizon, about 7.5 jumps)
        mc = np.random.default_rng(1); F = 76000.0; Ks = np.array([74000.0, 76000.0, 78000.0]); ty = 30 / 24 / 365
        lam, sj = JUMP_LAM * 365, JUMP_SD; sd = math.sqrt(VOL0**2 - lam * sj * sj); m = 400_000; nj = mc.poisson(lam * ty, m)
        x = sd * math.sqrt(ty) * mc.normal(size=m) - 0.5 * sd * sd * ty - 0.5 * sj * sj * nj + np.sqrt(nj) * sj * mc.normal(size=m)
        emp = np.array([(F * np.exp(x) > k).mean() for k in Ks])
        assert np.all(np.abs(emp - merton_p(F, Ks, ty, sd, lam, sj)) < 0.004), (emp, merton_p(F, Ks, ty, sd, lam, sj))
        # smoke checks: the null world must rarely pass, and the hedge must cut the day-level spread
        lab = scen[0][0]
        null = curves[f"{lab} | hedged | delta=0c"]
        assert all(r["pass"] <= 0.10 for r in null), null
        hv = [r for r in results if r["stat"] == "hedged" and r["delta_c"] == 5][0]
        uv = [r for r in results if r["stat"] == "unhedged" and r["delta_c"] == 5][0]
        assert hv["sd_day_c"] < uv["sd_day_c"] and hv["net_edge_c"] > 0, (hv, uv)
        print("quick checks passed")

if __name__ == "__main__":
    main()
