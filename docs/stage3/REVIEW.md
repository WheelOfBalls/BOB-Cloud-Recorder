# Stage 3 design: red-team review

Written 2026-11-06 by Claude, acting as an independent skeptical reviewer of the design merged in PR #8 (`DESIGN.md`, `PREREGISTRATION_stage3_DRAFT.md`, `power_sim.py`). **Synthetic data only.** No stage 2 snapshot, price or outcome was opened, and nothing in stage 2 (pre-registration, analysis code, recorder) was touched. The pre-registration is still a **DRAFT** that only Mattias can approve.

New simulation: [`power_sim_redteam.py`](power_sim_redteam.py), results in [`power_results_redteam.json`](power_results_redteam.json) (600 simulated days per cell, 4,000 resamples, seeds fixed in the script).

## Verdict

The design's structure holds up: an outcome-scored taker test, clustered by day, with a hedge as a control variate, can't be fooled into a PASS by a bad fair value, and its false-pass rate under an exact null is at or below 5%. **The power claim does not hold.** "A 4¢ mispricing passes about 100% of the time in the pessimistic world" comes mostly from how the synthetic mispricing was built. In a harsher but still plain world the test needs a mispricing of **about 6¢** (1¢ half spread) or **7 to 8¢** (2¢ half spread) to decide reliably in 28 days. A 4¢ mispricing is then worth nothing after costs, and the test KILLs it, which is the correct answer for that world.

## Corrected power estimate

T1 as pre-registered (hedged lower bound > 0 **and** unhedged mean > 0; KILL if the hedged upper bound < 1¢ or under 200 trades), 28 days, BTC + ETH hourly, τ = 1¢. "Red-team world" = the design's rough world plus 5 s recorder asynchrony, intraday volatility, a 2 bp forward error in p_opt, 60-second-average settlement, common jumps, the fixed $50 difference step, and the timing fix below. The mispricing fades out in the tails (full δ for truths between 10% and 90%, linear to 0 at 0% and 100%).

| World | Half spread | Mispricing δ | True net edge / contract | P(PASS) 14 / 28 / 56 days | P(KILL) 28 days |
|---|---|---|---|---|---|
| design's rough world, as `power_sim.py` (constant δ) | 1¢ | 4¢ | 1.4¢ | 0.89 / 0.99 / 1.00 | 0.00 |
| design's rough world, δ fading in tails | 1¢ | 4¢ | 0.7¢ | 0.41 / 0.63 / 0.87 | 0.12 |
| design's rough world, δ fading in tails | 1¢ | 5¢ | 1.9¢ | 0.89 / 0.99 / 1.00 | 0.00 |
| **red-team world** | 1¢ | 0 | −2.0¢ | 0 / 0 / 0 | 1.00 |
| **red-team world** | 1¢ | 4¢ | −0.1¢ | 0.02 / 0.01 / 0.01 | 0.96 |
| **red-team world** | 1¢ | 5¢ | 0.8¢ | 0.44 / 0.64 / 0.83 | 0.13 |
| **red-team world** | 1¢ | **6¢** | **1.7¢** | 0.90 / **0.99** / 1.00 | 0.00 |
| **red-team world** | 2¢ | 5¢ | −0.2¢ | 0.01 / 0.01 / 0.00 | 0.99 |
| **red-team world** | 2¢ | 6¢ | 0.7¢ | 0.39 / 0.61 / 0.85 | 0.11 |
| **red-team world** | 2¢ | **8¢** | **2.6¢** | 0.99 / **1.00** / 1.00 | 0.00 |

In terms of net edge, which is what the test measures: about 0.7 to 0.8¢ gives roughly 60% power at 28 days (80% needs about 50 days), and 1.7¢ or more gives about 99%. The 1¢ minimum the KILL rule is sized on sits between, at roughly 85 to 90% (interpolated, not run). **Corrected statement for the pre-registration: T1 decides reliably in 28 days when the true net edge is about 1¢ or more. In the red-team world that means a Kalshi mispricing of about 6¢ at a 1¢ half spread and 7 to 8¢ at 2¢.** The hedge cuts the day-level spread by about 2.3× (1.7¢ against 3.9¢ per contract), so it saves a factor of about 5 in days. That's still the main reason a 28-day test is possible, but it's not the 10 to 25× in `DESIGN.md`.

## Findings, most severe first

### 1. High: the synthetic mispricing builds in much of the answer

`power_sim.py` sets Kalshi's mid to truth ± δ at **every** strike. A contract that is 99.9% certain is then quoted at 94¢ (the clip at 0.98 minus δ = 4 to 6¢, inside the [0.06, 0.94] row filter), and buying it is a near-riskless 4 to 5¢. Those trades carry high weight and almost no variance, which inflates both the net edge and the power. Fading δ out in the tails alone takes the rough world's δ = 4¢ from 1.4¢ net and 99% power to 0.7¢ and 63% (rows 1 and 2 above). Signs it was happening: at δ = 6¢ the constant-offset version trades about 3,600 contracts a day against about 550 with the taper, with a day-level spread of 0.2¢ (`power` block in the JSON). A real market maker doesn't quote 94¢ on a contract that is settled in all but name.

Fix: the review's tables use the tapered mispricing. Power claims in `DESIGN.md` are now marked as superseded. Nothing in the gates changes.

### 2. High: the mapping from mispricing to net edge is much worse once p_opt is realistic at hourly horizons

At hourly horizons p_opt isn't really an options-implied distribution. The strikes that matter lie within about ±1% of spot, so the fitted smile contributes almost nothing and p_opt is a daily expiry's at-the-money variance scaled down to minutes. The red-team world adds what that misses, one assumption each (none measured):

- **Intraday volatility.** Variance by UTC hour varies from 0.7× to 1.7× the day's average (US open and data hours busy, Asian hours quiet), times a 30% hourly random factor. The truth (Kalshi's information) knows it; p_opt doesn't.
- **Forward error.** For a close before the first expiry, stage 2's fitter takes F from the 08:00 expiry's `underlying_price`, which is a futures price, and settlement is the CF Benchmarks index, not Deribit's. A 2 bp forward error is a tenth of the remaining sd 5 minutes before the close, about 4¢ at the money.
- **Settlement on a 60-second average**, which has a third of the last minute's variance. p_opt treats the close as a point.
- **The fixed $50 difference step,** about as wide as the whole distribution 5 minutes out, which smooths p_opt towards 50¢.

Together they cut the net edge at a given δ by about 0.9¢ (δ = 5¢: 1.9¢ in the tapered rough world, 0.8¢ in the red-team world). This is what pushes the needed mispricing from 4¢ to 6¢. The ex-ante gap on traded rows rises to 5 to 6¢ while the realised net edge falls. That's the S1 trap again, and T1 still isn't fooled by it.

Fixes in the draft: the forward for a close before the first expiry is `index_before`; h = min($50, 0.1·F·σ√τ) (and the ETH equivalent). The intraday clock and the averaging are left out on purpose. Fitting an intraday clock would mean choosing a model, and it's better to accept the power loss than to tune p_opt. This is written down as a known limit.

### 3. Medium: where the hedge starts can bias the hedged statistic upward

The hedged P&L really measures the price against the true probability **at the moment the hedge starts**. If the hedge starts at a spot reading that p_opt also saw, and that reading is from a different moment than the Kalshi quote, the hedged figure is credited with the very spot move that made p_opt and Kalshi disagree. The unhedged figure has no such bias. The recorder reads Deribit before Kalshi (as stage 2's `record_snapshot.py` does), and the draft starts the hedge at "the trade's snapshot" on the 1-minute grid.

In a frictionless exact null (no spread, no fee, Kalshi = truth, so the true edge is exactly 0), with the same random numbers in each case:

| Timing | Hedged mean | Hedged-only test passes at 28 days | T1 (needs unhedged > 0 too) |
|---|---|---|---|
| hedge at the Kalshi quote (unattainable) | −0.04¢ | 3.2% | 2.0% |
| 5 s async, hedge from `index_before` | +0.10¢ | 8.0% | 5.0% |
| 5 s async, hedge from the 1-minute grid (as drafted) | +0.08¢ | 7.5% | 4.6% |
| 5 s async, p_opt before, hedge from `index_after` (**fix**) | −0.03¢ | 3.4% | 2.3% |
| 30 s async, hedge from `index_before` | +0.53¢ | **52.5%** | **29.9%** |

At the drafted 5 s sync window the bias is small, and the sign condition on the unhedged mean keeps T1 at 5%. But it grows fast as the sync loosens, and nothing in the draft tied p_opt's inputs or the hedge's start to the Kalshi request's timestamps. Fix in the draft: a fixed order of requests; p_opt uses only data whose request ended before the Kalshi request started; the hedge starts at `index_after`, read after the Kalshi response; a row is dropped if the index moved more than a tenth of the remaining sd across the Kalshi pull. Under that rule the bias is gone (proof sketch: the increment from the quote to `index_after` is independent of everything the trade decision saw).

### 4. Medium: spreads and fees move the threshold one for one, and the fee rounding is unspecified

Every cent of half spread raises the mispricing needed by about a cent (table: at 2¢, δ = 5¢ nets −0.2¢). The design assumes 1¢, and no hourly quote has been looked at. If Kalshi rounds fees up to the whole cent per order, a 1-contract trade pays 2¢ at 50¢, not 1.75¢. That costs about 0.45¢ of net edge (δ = 5¢, red-team world, constant offset: 1.99¢ → 1.55¢). The stage 2 review recorded centicent rounding under the schedule effective 2026-07-07. That wasn't re-checked here: the Kalshi API is blocked from this container. Fix: the draft now requires the exact formula, with its rounding, to be written in at approval. The pilot's spread histogram goes next to the power statement. Depth isn't an issue for a 1-contract statistic, but it is for any money conclusion.

### 5. Medium: a PASS can come from picking off slow quotes, which a home or GitHub runner can't do

The test fills at the recorded touch at zero latency. If Kalshi's quotes lag spot, buying the stale side is a real edge in the data but only for whoever is fastest. In the red-team world, quotes that are 3 s stale at δ = 0 add +0.3¢ of net edge (−2.0¢ → −1.7¢). That isn't enough to pass alone, but it adds to any true edge. Fix: a pre-declared split of T1 by the index move in the 60 s before the snapshot. A PASS whose edge comes mostly after moves is read as latency-dependent, and the paper test must show the latency is available. This is not a gate.

### 6. Low: correlation and independence are handled correctly, with one caveat on scope

Hourly events within a day, all strikes of an event, and BTC against ETH are strongly dependent. The draft puts all of them in one UTC-day cluster, which is right. Under the exact null, payoffs minus fair prices are martingale differences across days, so day clusters give valid inference. The simulation agrees: size 2 to 5% across the timing variants above, with 27 degrees of freedom. Two caveats:

- (a) Simulated days are independent, but real ones share volatility regimes and possibly a mispricing regime that lasts weeks. The test then speaks for these 28 days, not for other periods. Added: a 7-day block bootstrap as a reported, non-gating figure.
- (b) An event that trades across midnight UTC must belong to one cluster. The draft now uses the close's day.

ETH adds less than a second coin (BTC alone at δ = 5¢: hedged day spread 1.24¢ against 1.05¢ with both coins), as `DESIGN.md` already says.

### 7. Low: the reported power was for the hedged test alone, not T1

`power_sim.py`'s "P(PASS) hedged" ignores T1's second condition (unhedged mean > 0). It hardly matters when the edge is large, but at 0.6¢ net it's 0.73 against 0.59 (constant-offset red-team world, δ = 4¢). All power figures here are for the full T1 rule.

### 8. Low: multiple testing

There is one primary test, and the splits are reported only. But the draft let T2 (maker) pass as a second gate, which roughly doubles the chance of a false go-ahead. The draft now says only T1 can justify a next stage. The requirement that the hedged and unhedged figures agree makes T1 conservative (2% in the exact null against a nominal 5%).

### 9. Low: power from resampling a finite pool

Both simulations resample days from a pool of 600 to 800 and treat the pool's mean as the truth. That shifts power by a few points (the exact-null size varied between 2% and 3% across pools of the same world). Fine for sizing. Not worth more compute.

## What is not covered

- Real hourly spreads, depth, event schedule (does every hour have an event?) and quote staleness. The counts-only pilot measures the first three without prices.
- Mispricing patterns other than a uniform offset, such as Kalshi's implied volatility being too high or too low (zero at the money, largest about 1 sd out) or a longshot bias. They would change the trade mix, not the logic.
- The maker test T2 (no fill model).
- Whether the assumed intraday profile and the 2 bp forward error are realistic. They are guesses, and the conclusion (needs about 6¢, not 4¢) depends on them about as much as on the tails.

## Edits made in this PR

- `PREREGISTRATION_stage3_DRAFT.md`: request order; no look-ahead in p_opt; forward and difference step for hourly closes; where the hedge starts; row sync; fee rounding to be written in; clustering by close day; only T1 justifies a next stage; corrected expected power; block bootstrap and stale-quote split reported. Every edit is marked **[review]**. Still DRAFT.
- `DESIGN.md`: a notice that its power figures are superseded by this file.
- `power_sim_redteam.py` + results; CI runs its `--quick` check (an exact-truth Monte Carlo check and the timing bias check).
