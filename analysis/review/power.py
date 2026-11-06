# Review experiment (synthetic only). Run: python3 analysis/review/power.py [reps]
# Monte Carlo of the S1/S2 gates with 10 or 13 events. Simplified world: flat 50% vol, Kalshi quotes = truth - edge,
# rounded to the cent, +-1c; p_opt = truth + noise (common per snapshot + per strike). Vectorised over snapshots.
import math, random, sys
def N(x): return 0.5 * math.erfc(-x / 1.4142135623730951)
fee = lambda q: 0.07 * q * (1 - q)
VOL, Y = 0.5, 365 * 86400
def day(rng, edge, s_common, s_idio, stride=6):
    S0 = 76000.0; strikes = [round(S0 / 250) * 250 + 250 * j - 0.01 for j in range(-8, 9)]
    n = 360; S = S0; path = []
    for i in range(n):
        path.append(S); S *= math.exp(VOL * math.sqrt(300 / Y) * rng.gauss(0, 1) - 0.5 * VOL**2 * 300 / Y)
    ST = S
    gs, trades, seen = [], [], set()
    for i in range(0, n, stride):          # every 30 min to keep it fast; S2 first-positive is per strike
        tau = (n - i) * 300 / Y; s = VOL * math.sqrt(tau); F = path[i]
        c = rng.gauss(0, s_common)
        for K in strikes:
            p = N((math.log(F / K) - 0.5 * s * s) / s)
            m = min(max(p - edge, 0.02), 0.98); bid = round(m * 100) / 100 - 0.01; ask = bid + 0.02
            mid = (bid + ask) / 2
            if not (0.06 <= mid <= 0.94) or bid <= 0 or ask >= 1: continue
            po = min(max(p + c + rng.gauss(0, s_idio), 0), 1)
            gy = po - ask - fee(ask); gn = (1 - po) - (1 - bid) - fee(1 - bid); g = max(gy, gn)
            gs.append(g)
            if g > 0 and K not in seen:
                seen.add(K); yes = ST > K
                if gy >= gn: trades.append((1.0 if yes else 0.0) - ask - fee(ask))
                else: trades.append((0.0 if yes else 1.0) - (1 - bid) - fee(1 - bid))
    return sum(gs), len(gs), sum(trades), len(trades)
def sim(ndays, edge, sc, si, reps, seed=1):
    rng = random.Random(seed); p1 = p2 = both = 0
    for _ in range(reps):
        a = b = c = d = 0
        for _ in range(ndays):
            x = day(rng, edge, sc, si); a += x[0]; b += x[1]; c += x[2]; d += x[3]
        s1 = a / b > 0; s2 = d > 0 and c / d > 0
        p1 += s1; p2 += s2; both += s1 and s2
    return p1 / reps, p2 / reps, both / reps
reps = int(sys.argv[1]) if len(sys.argv) > 1 else 300
for nd in (10, 13):
    for edge, sc, si, lab in ((0.0, 0.0, 0.003, "no edge, OTM-fit noise ~0.3c"),
                              (0.0, 0.01, 0.02, "no edge, ITM-fit noise ~2c + 1c common"),
                              (0.0, 0.0, 0.04, "no edge, noise 4c"),
                              (0.03, 0.0, 0.003, "true 3c edge, small noise"),
                              (0.05, 0.0, 0.003, "true 5c edge, small noise")):
        a, b, c = sim(nd, edge, sc, si, reps)
        print(f"{nd:2d} events  {lab:40s}  P(S1 pass) {a:.2f}  P(S2 pass) {b:.2f}  P(both) {c:.2f}", flush=True)
