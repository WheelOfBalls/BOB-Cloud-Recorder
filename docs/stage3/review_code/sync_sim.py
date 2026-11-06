# Frictionless null: Kalshi mid = true P(S_T > K) at the quote instant. Does the row-sync filter (which reads
# index_after, taken after the quote) bias the hedged P&L? Metric: X = P(S_T>K | S_after) - price - fee, i.e. the
# expectation of the (continuously) hedged P&L given information at the hedge start. Under the null E[X] < 0.
import numpy as np, math, sys
from math import erf
rng = np.random.default_rng(1)
YEAR = 365.25 * 86400
sig = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
lag_lo, lag_hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.2, 1.0)
N = 20000
s1 = sig / math.sqrt(YEAR)
Phi = lambda z: 0.5 * (1 + np.vectorize(erf)(z / math.sqrt(2)))
def ptrue(x, K, tau):  # x = log S, driftless log (ignore -w/2, tiny)
    return Phi((x - np.log(K)) / (sig * np.sqrt(tau / YEAR)))
fee = lambda q: np.ceil(0.07 * q * (1 - q) * 10000 - 1e-7) / 10000
S0 = 90000.0
strikes = S0 + 100 * np.arange(-15, 16)
res = {"nofilter": [], "filter": [], "valid010": []}
dropped = 0; rows = 0
x = np.full(N, math.log(S0)) + rng.normal(0, 0.003, N)   # random start so strikes sit anywhere
t = 0.0
slots = [3600 - (57.5 - 5 * j) * 60 for j in range(12)]   # seconds after hour start; close at 3600
traded = {k: np.zeros((N, len(strikes)), bool) for k in res}
for ts in slots:
    x = x + rng.normal(0, s1 * math.sqrt(ts - t), N); t = ts
    xb = x
    dq = rng.uniform(lag_lo, lag_hi, N); da = rng.uniform(lag_lo, lag_hi, N)
    xq = xb + rng.normal(0, 1, N) * s1 * np.sqrt(dq)
    xa = xq + rng.normal(0, 1, N) * s1 * np.sqrt(da)
    tau_b = 3600 - ts; tau_q = tau_b - dq; tau_a = tau_q - da
    sd_rem = sig * math.sqrt(tau_b / YEAR)
    sync_bad = np.abs(np.exp(xa) - np.exp(xb)) > 0.1 * np.exp(xb) * sd_rem
    for j, K in enumerate(strikes):
        p_opt = ptrue(xb, K, tau_b); mid = ptrue(xq, K, tau_q); va = ptrue(xa, K, tau_a)
        bid = np.round(mid * 100) / 100 - 0.01; ask = bid + 0.02
        m = 0.5 * (bid + ask)
        ok = (bid > 0) & (ask < 1) & (m >= 0.06) & (m <= 0.94)
        gy = p_opt - ask - fee(ask); gn = (1 - p_opt) - (1 - bid) - fee(1 - bid)
        g = np.maximum(gy, gn)
        yes = gy >= gn
        price = np.where(yes, ask, 1 - bid)
        X = np.where(yes, va, 1 - va) - price - fee(price)
        rows += ok.sum(); dropped += (ok & sync_bad).sum()
        for key in res:
            elig = ok & (g > 0.01) & ~traded[key][:, j]
            if key == "valid010":
                elig &= ~(np.abs(np.exp(xa) / np.exp(xb) - 1) >= 0.001)
            if key == "filter":
                # rows dropped by sync are not candidates; a later row of the same market can still trade
                elig &= ~sync_bad
            traded[key][elig, j] = True
            res[key] += list(X[elig])
    x = xa; t = ts + dq.mean() + da.mean()  # approx
print(f"sigma {sig}, lags U({lag_lo},{lag_hi}) s each; rows {rows}, sync-dropped {dropped/rows:.1%}")
for k, v in res.items():
    v = np.array(v); print(f"{k:9s} trades {len(v):6d}  mean X {v.mean()*100:+.3f}c  se {v.std()/math.sqrt(len(v))*100:.3f}c")
