# Review experiment (synthetic only): spread of the daily S2 mean, and the days a powered S2 would need.
import random, statistics as st, os
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.py")).read().split("reps = int")[0]; ns = {}; exec(src, ns)
for edge in (0.03, 0.05):
    rng = random.Random(9); ms = []; tot_p = tot_n = 0
    for _ in range(600):
        a, b, c, d = ns["day"](rng, edge, 0.0, 0.003)
        if d: ms.append(c / d); tot_p += c; tot_n += d
    mu, sd = tot_p / tot_n, st.pstdev(ms)
    print(f"edge {edge}: mean P&L/contract {mu*100:.2f}c, sd of daily mean {sd*100:.1f}c, trades/day {tot_n/600:.1f}, "
          f"days for 80% power one-sided 5%: {((1.645+0.842)*sd/mu)**2:.0f}")
