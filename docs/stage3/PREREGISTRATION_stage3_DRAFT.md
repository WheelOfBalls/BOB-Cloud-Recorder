# Crypto stage 3 pre-registration: DRAFT, NOT APPROVED

> **Status: DRAFT.** Written 2026-11-06 by Claude while stage 2 is still recording and every stage 2 price, outcome and result is unseen. **Mattias must approve this file before stage 3 starts.** Until then nothing here binds, the stage 3 recorder must not run, and any edit is free. On approval, change this banner to "Approved by Mattias on DATE", record the file's sha256 in `DESIGN.md`, and from then on change it only through the deviations log at the end.
>
> Design reasoning and the power simulation behind every number below: [`DESIGN.md`](DESIGN.md).

Public read-only data only. No account, no authentication, no orders. Every trade below is simulated. Passing does not validate an edge; it justifies a small, separately approved paper-trading test with real latency.

## What is being tested

Stage 2 asks whether Kalshi's 5pm KXBTCD contracts are mispriced against Deribit-implied probabilities. With 10 to 13 events it can't answer decisively (deviation 5). Stage 3 asks the same taker question on the **hourly** Kalshi crypto events, which settle 24 times a day, and uses a delta-hedged P&L that removes most of the settlement noise without changing what is measured.

**H1 (primary).** Buying at the touch the side of a Kalshi hourly above/below contract that p_opt says is cheap by more than 1¢ after the taker fee earns a positive mean realised net P&L per contract.

**H2 (secondary).** An outside maker resting at the best bid on the side p_opt favours earns a positive return per dollar, using stage 2's strict fill rule.

## Markets

- **KXBTCD** and **KXETHD** hourly events (series `frequency: hourly`, settled by CF Benchmarks). Checked 2026-11-06 with `discover_series.py`, which prints metadata only.
- An *hourly event* is a KXBTCD or KXETHD event whose `event_ticker` does not end in `17`. Tickers end in the Eastern-time hour of the close (`KXBTCD-26NOV0523` closes 23:00 ET), and the `17` events are the 5pm daily ones stage 2 uses, which have wider strike spacing ($500 against $100 on BTC). So stage 3 shares no events with stage 2. **[confirm in the counts-only pilot that every hour has an event]**
- SOL and XRP hourly series exist but are out of scope: Deribit has no liquid options on them to build p_opt.

## Recording (stage 3 recorder, separate from stage 2)

- A new workflow and script (`stage3/`), its own `stage3-data` branch and concurrency group. The stage 2 recorder, its workflow, branch and code are not touched.
- **Start:** the first 5-minute slot at or after 2026-11-20 00:00 UTC, or the first slot after approval if later. **Length: 28 full UTC days**, fixed now. No extension, no early stop, no peeking (see "Blinding").
- **Every 5 minutes**, one snapshot with:
  - Deribit BTC and ETH option chains, expiries within 3 days, and each index (`btc_usd`, `eth_usd`) before and after the Kalshi pull;
  - top of book for every open KXBTCD and KXETHD market;
  - full order books for hourly markets with a two-sided quote inside 3 to 97¢ (for H2).
- **Every minute**, a light poll of both Deribit indices (for the hedge). One failed poll is a missing minute; nothing is filled in.
- **Validity** (per coin, as stage 2): that coin's Deribit chain and Kalshi top-of-book requests finished within 5 s of each other, and its index moved under 0.10% across the Kalshi pull.
- **Trades and outcomes** are pulled by a separate script after the 28 days, never during them.

## Fair value

As stage 2, with its review fix: total variance w(k) fitted per expiry as a cubic in k = ln(K/F) on two-sided **out-of-the-money** mids (calls K ≥ F, puts K < F) with `mark_iv` present, at least 4 options. A close before the first expiry scales that expiry's w by τ_T/τ_1. Otherwise w is interpolated linearly in calendar time at fixed k. p_opt = (C(K − h) − C(K + h)) / (2h), with h = $50 for BTC (as stage 2) and h = $2.50 for ETH (the same share of spot, roughly). No intraday variance clock, no discount.

## Rows and the trade rule

- **Rows:** valid snapshots × hourly markets with a two-sided quote, mid in [0.06, 0.94], and 2 to 60 minutes to close.
- Taker fee f(q) = 0.07·q·(1 − q), the schedule current at the start. **[check the fee schedule again at approval]**
- g = max(p_opt − ask − f(ask), (1 − p_opt) − (1 − bid) − f(1 − bid)).
- **Trade:** for each market, the first row with g > τ = 0.01 buys 1 contract of the better side at the touch. One trade per market at most.
- **Realised net P&L** r = payoff − price − f(price), payoff 1 or 0 from Kalshi's result.
- **Hedge term** h = Σ Δ_i (S_{i+1} − S_i) over the 1-minute index grid from the trade's snapshot to the close, Δ_i = ±∂p_opt/∂S (the lognormal digital delta at that minute, using the variance the trade's snapshot fitted, sign + for YES and − for NO). A missing minute is skipped (its move rolls into the next step). **Hedged P&L** = r − h.

## Tests and gates

All inference clusters by **UTC day** (both coins and all 24 hours of a day form one cluster). With D days, n_d trades and P&L sum x_d on day d, the estimate is μ = Σx_d / Σn_d and

  se = sqrt(D/(D−1) · Σ_d (x_d − μ·n_d)²) / Σn_d.

t is the one-sided 95% Student t quantile with D − 1 degrees of freedom.

| # | Test | PASS | KILL | Otherwise |
|---|---|---|---|---|
| T1 (primary) | Hedged P&L per contract | μ_hedged − t·se > 0 **and** unhedged μ > 0 | fewer than 200 trades, **or** μ_hedged + t·se < 1¢ | INCONCLUSIVE |
| T2 (secondary) | Stage 2's S3 maker rule on hourly rows, held to settlement | dollar-weighted return per dollar with lower bound > 0 | fewer than 200 fills, or upper bound < 0 | INCONCLUSIVE |

- **The coverage rule:** a day counts if at least 80% of its 288 slots are valid for both coins. A test needs at least 21 counted days; otherwise every verdict is INCOMPLETE. Rows from days that don't count are dropped.
- **KILL on T1** means: if an edge of 1¢ per contract or more existed, data like these would occur less than 5% of the time. That is the decisive "no" stage 2 can't give.
- **PASS on T1** means a positive mean net P&L at 95% one-sided, with the unhedged figure agreeing in sign.
- T2's power is not estimated (no fill model is assumed). Its gate is recorded, but its verdict is read as weaker than T1's.

## How outcomes will be read (fixed now)

- **T1 KILL:** the Deribit anchor gives no taker edge of 1¢ or more on hourly crypto contracts. The taker idea ends.
- **T1 PASS:** justifies a separately approved paper test with real order latency. It does not validate a trading edge: four weeks is one market regime, and the fill assumption (the full touch, zero latency) is optimistic.
- **T1 INCONCLUSIVE:** reported as such. Not extended, not re-run on the same data with other settings.
- **T2** is read as in stage 2 (an outside maker's premium), with the same caveats.
- Stage 2's verdict does not change any stage 3 rule, and stage 3 does not reinterpret stage 2.

## Reported, never used to rescue a verdict

- T1 by coin, by minutes to close (2–15, 15–30, 30–60), and with τ = 0 and τ = 2¢.
- The S1-style ex-ante gap mean on the traded rows, next to the realised figure.
- A cluster bootstrap over days (2,000 resamples, seed 20261120) next to the t interval.
- The hedge with the 5-minute snapshot index instead of the 1-minute grid.
- Calibration of p_opt and the mid (Brier, log loss) on each market's last row ≥ 5 minutes before close.

## Blinding and guard rails

- The analysis script is written and tested on synthetic fixtures only, frozen (sha256 recorded here) **before** the recorder starts.
- During recording only a counts-only coverage report may be run (no prices, gaps, p_opt, outcomes or trades), as stage 2's `preflight`.
- The analysis runs once, on the frozen commit, after the 28 days, and its output is committed straight away.

## Limits known in advance

- One market regime of four weeks. BTC and ETH move together (correlation about 0.8), so ETH adds less than a second coin's worth of information.
- Kalshi settles on a 60-second average of the CF Benchmarks real-time index. The hedge uses Deribit's index; the basis adds noise, not bias.
- Taker fills assume the whole touch is available at zero latency. A quote that looks stale against a Deribit move is the one most likely to be pulled first.
- The hourly fair value scales a daily option's variance down to minutes without an intraday clock. This hurts p_opt (and so power), not the honesty of T1, which is judged on outcomes.

## Deviations log

(empty until approval)
