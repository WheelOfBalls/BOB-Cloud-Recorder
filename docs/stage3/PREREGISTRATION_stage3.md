# Crypto stage 3 pre-registration (approved 2026-11-06, before any stage 3 data)

> **Status: approved by Mattias on 2026-11-06.** Written by Claude on 2026-11-06 while stage 2 was still recording and every stage 2 price, outcome and result was unseen. Mattias replied "approved" at 03:51 UTC to the draft as merged in PR #8, and at 03:55 UTC asked for approvals to be handled automatically while he was away. Under that instruction the red-team edits from PR #9 (marked **[review]**) and the fee rounding below were added before freezing. The diff against the text he approved is in the description of the pull request that froze this file (the commit after #9). **One material change he has not seen:** the approved draft said a 4¢ mispricing was detectable; the review puts the reliable minimum at about 6¢ (1¢ half spread). The gates are unchanged. The frozen file's sha256 is recorded in `DESIGN.md`. From now on this file changes only through the deviations log at the end.
>
> Design reasoning and the power simulation behind every number below: [`DESIGN.md`](DESIGN.md). Red-team review of this draft, with the corrected power estimate and the edits it made here: [`REVIEW.md`](REVIEW.md). Edits from that review are marked **[review]**.

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
- **Order within a snapshot [review]:** for each coin, the Deribit chain and an index read (`index_before`) come first, then the Kalshi requests, then a second index read (`index_after`). Every request stores its start and end time (`t0`, `t1`).
- **Validity** (per coin, as stage 2): that coin's Deribit chain and Kalshi top-of-book requests finished within 5 s of each other, and its index moved under 0.10% across the Kalshi pull.
- **Trades and outcomes** are pulled by a separate script after the 28 days, never during them.

## Fair value

As stage 2, with its review fix: total variance w(k) fitted per expiry as a cubic in k = ln(K/F) on two-sided **out-of-the-money** mids (calls K ≥ F, puts K < F) with `mark_iv` present, at least 4 options. A close before the first expiry scales that expiry's w by τ_T/τ_1. Otherwise w is interpolated linearly in calendar time at fixed k. p_opt = (C(K − h) − C(K + h)) / (2h), with the step h given below. No intraday variance clock, no discount.

- **No look-ahead [review]:** p_opt uses only data whose request ended before the Kalshi request started. For a close before the first expiry the forward is `index_before`, not the expiry's `underlying_price` (that is the 08:00 forward, which is off by the futures basis, and the basis matters at minutes to close).
- **Difference step [review]:** h = min($50, 0.1 · F · σ√τ) for BTC and min($2.50, 0.1 · F · σ√τ) for ETH, where σ√τ is the fitted at-the-money total sd to the close. A fixed $50 is about as wide as the whole distribution 5 minutes before an hourly close and smooths p_opt towards 50¢.

## Rows and the trade rule

- **Rows:** valid snapshots × hourly markets with a two-sided quote, mid in [0.06, 0.94], and 2 to 60 minutes to close.
- **Taker fee [approval]:** for each simulated 1-contract trade at price q, f(q) = 0.07·q·(1 − q) rounded **up to the next $0.0001** (centicent), per Kalshi's fee schedule effective 2026-07-07 as read in stage 2's review (`analysis/REVIEW.md`, finding 5). T1 is also reported with the fee rounded up to the whole cent (about 0.45¢ of net edge worse), for reference only. **Makers (T2) pay no fee**, as on that schedule for series it doesn't list. **Before the first stage 3 snapshot**, the live schedule is checked for KXBTCD and KXETHD. If either rule differs, the difference is logged as a deviation before any data exists.
- g = max(p_opt − ask − f(ask), (1 − p_opt) − (1 − bid) − f(1 − bid)).
- **Trade:** for each market, the first row with g > τ = 0.01 buys 1 contract of the better side at the touch. One trade per market at most.
- **Realised net P&L** r = payoff − price − f(price), payoff 1 or 0 from Kalshi's result.
- **Hedge term** h = Σ Δ_i (S_{i+1} − S_i) over the 1-minute index grid from the trade's snapshot to the close, Δ_i = ±∂p_opt/∂S (the lognormal digital delta at that minute, using the variance the trade's snapshot fitted, sign + for YES and − for NO). A missing minute is skipped (its move rolls into the next step). **Hedged P&L** = r − h.
- **Where the hedge starts [review]:** at that snapshot's `index_after` (read after the Kalshi response), then the first 1-minute poll after it, and so on to the close. Not at the 1-minute poll before the snapshot, and not at `index_before`. Reason: the hedged P&L measures the price against the probability *at the hedge's start*. If the hedge starts before the Kalshi quote while p_opt also saw that earlier spot, the hedged figure is credited with the spot move between the two, which is exactly the move that made p_opt and Kalshi disagree. In the review's frictionless null this bias was about +0.1¢ with the 5 s sync window and +0.5¢ with 30 s (the hedged-only test then passed 52% of the time at 28 days). Starting after the response and using only earlier data for p_opt removes it (size 2.3%).
- **Row sync [review]:** a row is dropped if |`index_after` − `index_before`| exceeds 0.1 × F σ√τ for that market (a tenth of the remaining sd). This uses no prices or outcomes.

## Tests and gates

All inference clusters by **UTC day of the event's close** (both coins and all 24 hours of a day form one cluster, and an event that trades across midnight belongs to its close's day) **[review: the close's day]**. With D days, n_d trades and P&L sum x_d on day d, the estimate is μ = Σx_d / Σn_d and

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
- **Only T1 can justify a next stage [review].** A T2 PASS alone is reported but does not justify the paper test, so the two gates don't double the chance of a false go-ahead. Splits by coin, hour or minutes to close are unadjusted, never gates.
- **Expected power (from REVIEW.md, synthetic, not a promise) [review]:** T1 decides reliably only when the true net edge per contract is about 1¢ or more. In the review's harsher synthetic world (mispricing fading out at the tails, timing fixed) that takes a Kalshi mispricing of about 6¢ at a 1¢ half spread (net 1.7¢, T1 passes 99% at 28 days) and about 7 to 8¢ at a 2¢ half spread, not 4¢. There a 4¢ mispricing nets about 0¢ at a 1¢ half spread (KILL 96%), and 5¢ nets 0.8¢ (PASS 64%, KILL 13%, otherwise INCONCLUSIVE). The counts-only pilot's spread histogram is recorded next to this before the start; it changes no gate.

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
- **[review]** The same with 7-day blocks (four blocks, so descriptive only): if the edge comes from one week, the day-clustered interval overstates how much the 28 days say about other periods.
- **[review] Stale-quote split:** T1's estimate on rows where the index moved less than 0.25 × F σ√τ over the 60 s before the snapshot, against the rest. A PASS whose edge comes mostly from rows after a move is read as picking off slow quotes, which needs a latency the paper test must show is available.
- The hedge with the 5-minute snapshot index instead of the 1-minute grid.
- Calibration of p_opt and the mid (Brier, log loss) on each market's last row ≥ 5 minutes before close.

## Blinding and guard rails

- The analysis script is written and tested on synthetic fixtures only, frozen (sha256 recorded here) **before** the recorder starts.
- During recording only a counts-only coverage report may be run (no prices, gaps, p_opt, outcomes or trades), as stage 2's `preflight`.
- The analysis runs once, on the frozen commit, after the 28 days, and its output is committed straight away.

## Limits known in advance

- One market regime of four weeks. BTC and ETH move together (correlation about 0.8), so ETH adds less than a second coin's worth of information.
- Kalshi settles on a 60-second average of the CF Benchmarks real-time index. The hedge uses Deribit's index; for the hedge the basis adds noise, not bias. **[review]** For p_opt it is a bias near the close: a 2 bp forward error is a tenth of the 5-minute sd. It costs power (wrong trades), not validity.
- Taker fills assume the whole touch is available at zero latency. A quote that looks stale against a Deribit move is the one most likely to be pulled first.
- The hourly fair value scales a daily option's variance down to minutes without an intraday clock. This hurts p_opt (and so power), not the honesty of T1, which is judged on outcomes.

## Deviations log

### Deviation 1 (2026-11-06, before any live stage 3 data): the row-sync rule no longer selects rows

**Approval.** Approved at about 06:51 UTC on 2026-11-06 by the project's coordinator (a Claude session), acting under Mattias's delegation ("remember, im stepping away so automatically continue, reprompt and approve", 03:55 UTC). Mattias has not seen it yet. **He can revert it at any time before 2026-11-20 00:00 UTC**; after that it stands, because live data will exist.

**Data seen.** None. The live window starts on 2026-11-20. The finding came from code review and from synthetic simulations only. No pilot or stage 2 quote, index level, p_opt, trade or outcome was opened.

**Change.** The rule under "Row sync [review]" (drop a row if |`index_after` − `index_before`| > 0.1 × F σ√τ) **no longer removes rows** from T1 or T2. Each row is flagged instead. T1 recomputed with the original rule applied is reported under "Reported, never used to rescue a verdict", as "T1 with the pre-registered row-sync rule". Nothing else changes: the gates, the 5 s and 0.10% validity rules, the hedge start at `index_after`, p_opt's inputs, the stale-quote split and the 28-day window all stay as written above.

**Why.** `index_after` is read after the Kalshi quote, and the hedged P&L is measured from it. A spot move between `index_before` and the quote triggers trades against that move. Requiring |`index_after` − `index_before`| to be small then keeps mostly the trades whose next move (quote to `index_after`) reversed it, which is the direction the trade bet on. So the rule selects on information a taker could not have had. In a zero-edge synthetic world (Kalshi quoting the true probability at the quote instant), it raised the expected hedged P&L by +1.0 to +2.1¢ per contract in an exact-expectation simulation, and by +1.76¢ on average over 6 seeds of the frozen analysis code. In one seed both PASS conditions held on the mean. That bias is as large as the 1¢ KILL margin. Details and scripts: `docs/stage3/REVIEW_code.md` (finding 1) and `docs/stage3/review_code/`. The purpose the rule was added for, which is not trusting quotes taken while the index moved, is still served without look-ahead by the 5 s validity rule, by starting the hedge after the quote, and by the stale-quote split.

**Code.** `analysis/analyze_stage3.py` (new sha256 in `analysis/FROZEN_stage3.md`), with a test that a moved `index_after` flags rows and does not drop them. The zero-edge check was re-run after the change (results in `REVIEW_code.md`).
