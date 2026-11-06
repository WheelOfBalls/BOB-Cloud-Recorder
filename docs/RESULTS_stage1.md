# Crypto kill test results (run 2026-11-05)

**Verdict: stage 1 passed. This is not a validated edge.** Both pre-registered rules passed on 104 daily BTC events that J never used, so the last-hour result replicated. What passed is the return earned by all makers together. Whether an outside maker could earn it is still unknown, and that is what stage 2 tests.

Rules: `PREREGISTRATION.md`. Raw output: `data/fresh_results.txt`, run once. Code check: `data/repro_results.txt`.

## Sample

- 104 fresh KXBTCD 5pm events, closing July 1 to October 31, 2026; 3,926 markets; 3,418,468 prints; 368.6M contracts.
- This is the full tape. Pulled volume equals lifetime volume for every event, with no truncated markets.
- The same code first reproduced J's published numbers on J's 20 events: 745,112 prints, maker +1.55% (J: +1.6%), last hour +1.66% (J: +1.7%).

## Kill criteria

| # | Test | Result | Rule | Outcome |
|---|---|---|---|---|
| C1 | Maker return, all prints | +1.75% [+0.92, +2.56] | CI includes ≤ 0 | Pass |
| C2 | Maker return, last hour | +1.69% [+0.68, +2.70] | CI includes ≤ 0 | Pass |

## Secondary results

| Cut | Maker return |
|---|---|
| Excluding 1¢ and 99¢ prints | +1.82% [+0.93, +2.68] |
| Maker buying at ≥ 50¢ | +3.59% [+1.71, +5.45] |
| 1–6 hours before close | +2.12% [+0.95, +3.24] |
| Over 6 hours before close | +1.61% [+0.01, +3.04] |
| July | +2.08% [+0.71, +3.43] |
| August | +1.17% [−0.79, +3.00] |
| September | +2.50% [+1.28, +3.61] |
| October | +1.33% [−0.38, +2.90] |

- **Takers:** −4.73% net of fees [−5.83, −3.59].
- **Concentration is low.** The top 3 events gave 16% of P&L and the top 5 gave 26%, against 87% for the top 3 in J's sample. 77 of 104 events were positive.
- **Size:** all makers together earned about $3.7M across the 104 days, or roughly $36,000 a day.

## What the return is made of (exploratory, run after the test)

From `scripts/explore_after_pass.py`, on the fresh events.

**It is mostly not spread.** Cents per contract for all makers:

| Measured after | All prints | Last hour |
|---|---|---|
| 1 minute | +0.19¢ | +0.35¢ |
| 5 minutes | +0.31¢ | +0.50¢ |
| 30 minutes | +0.53¢ | +0.81¢ |
| Held to settlement | +1.01¢ [+0.52, +1.46] | +0.99¢ [+0.40, +1.54] |

About 70% of the profit arrives after the first five minutes, so most of it is paid for holding the position. That makes it look more like a risk premium than a fee for providing liquidity.

The one-minute figure is well below half a 1¢ tick, which suggests makers are already being picked off in the first minute. This assumes a 1¢ spread, and historical spreads aren't available to confirm it.

**It carries real Bitcoin risk, but direction doesn't explain it.**

- Regressing each day's maker return on Bitcoin's daily move (103 days) gives an intercept of +2.10% [+1.50, +2.72] and a beta of −1.11 [−1.40, −0.67].
- Makers lean short Bitcoin: +3.59% on down days and +0.16% on up days.
- Bitcoin rose from about $60,000 to $78,000 over the period, so direction worked against makers, not for them.
- On this fit, the return reaches zero on a day when Bitcoin rises about 1.9%. That is close to one daily standard deviation (1.77%).

## Reconciling with the main kill test

`L_kill_test/RESULTS.md` showed −2.89% for a 70–94¢ maker rule on KXBTCD and KXETHD. `scripts/reconcile_with_L.py` reproduces that figure exactly and explains it:

| Same 70–94¢ rule, closes Jul–Oct | Return | Prints |
|---|---|---|
| L sample, all | −2.89% [−6.97, +1.19] | 11,533 |
| L sample, KXBTCD other hours | −2.70% [−7.14, +1.68] | 9,930 |
| L sample, KXBTCD 5pm | +3.70% [−8.75, +12.07] | 994 |
| Full tape, KXBTCD 5pm | +4.10% [+1.76, +6.33] | all |

The two tests agree. L's figure was mostly hourly events, which this test doesn't cover. The 58 KXETHD 5pm prints in L's sample are too few to read.

## What this does not show

1. **That an outsider can earn this.** The figure averages every maker, including fast firms at the front of the queue. An outside maker is more likely to be filled just before the price moves against them. Historical order books aren't available, so the tape can't measure this.
2. **That it extends beyond the 5pm BTC event.** Hourly BTC events were negative on the 70–94¢ rule in L's sample (interval includes zero). ETH wasn't tested.
3. **That it survives other market regimes.** This is four months of one mostly rising market, and it depends on no sustained sharp rally.
4. **That the net number is the return on capital.** It is per dollar of contract price paid. It doesn't count inventory limits, position risk, or any hedging cost for the short-Bitcoin lean.
5. **That the fee stays zero.** Maker fees exist on other series, and Kalshi could extend them here. This whole return depends on that fee being zero.
6. **That this sample is fully unseen.** L's sample overlapped these dates, though on a different rule.

## Next step

Stage 2, from the pre-registration: a two-week synchronous snapshot test against Deribit options. It needs the order book recorded going forward, so it can't be run on history. It tests the options-anchored fair value that the idea is built on, not outsider fills directly. Those need recorded books with a queue model.
