# Stage 3 design: a test that can actually say yes or no

Written 2026-11-06, while stage 2 is still recording. **Nothing here used real stage 2 data.** No snapshot, price, quote, outcome or result from stage 2 was opened. The power numbers come from `power_sim.py` on synthetic data only, and the only live data touched is market *metadata* (series, settlement hours, strike counts) printed by `discover_series.py` in CI.

> **Red-team review (2026-11-06): the power figures below are superseded.** See [`REVIEW.md`](REVIEW.md). The constant-offset mispricing in `power_sim.py` creates near-riskless trades in the tails, and the fair value is closer to the truth than it can be at hourly horizons. With both corrected, the test decides reliably in 28 days at a mispricing of about 6¢ (1¢ half spread) or 7 to 8¢ (2¢), not 4¢. The structure of the test (outcome-scored, day clusters, hedge as a control variate) holds, with a fix to where the hedge starts.

The pre-registration that follows from this is [`PREREGISTRATION_stage3.md`](PREREGISTRATION_stage3.md). **Approved by Mattias on 2026-11-06 and frozen** (see its banner for how the approval was given). Frozen sha256: `a62576a867276b45bda07398f4fa804b44f275d054dfa653510814ee69c3c515`. If the file's sha256 differs from this, it was changed after the freeze, and the change must appear in its deviations log.

## In short

- **Stage 2 can't be fixed by recording longer.** With one 5pm settlement a day, the plain realised-P&L test (S2) needs roughly 550 to 1,500 days for 80% power at a 5¢ mispricing (table below). That's not a recording problem: each day is one bet on one BTC close.
- **Two changes get a decisive answer in four weeks:**
  1. **Use the hourly events.** KXBTCD and KXETHD are hourly series (checked, see "What exists"). That is 24 settlements a day per coin instead of one.
  2. **Score each trade by its delta-hedged P&L.** Subtract what a spot hedge would have earned between the trade and the close. The hedge has mean zero, so the estimate still measures realised payoff minus price, the honest quantity S2 measures. It removes most of the settlement noise. It's a control variate, not an assumed trade.
- **Recommended:** 28 days of hourly BTC and ETH, a 1¢ entry threshold, day-clustered inference, and a three-way verdict: PASS, KILL (decisive: "no edge of 1¢ or more"), or INCONCLUSIVE. In the pessimistic synthetic world it passes a 4¢ mispricing (about 1.6¢ net) 100% of the time and kills a zero edge 100% of the time, even though the S1-style ex-ante gap there wrongly says +2.8¢.
- **Cost:** $0 in fees (public repo, free Actions minutes, public data), about 0.5 GB of snapshots, one new workflow, and Mattias's time to approve and later read one result.

## Why stage 2 is underpowered

From stage 2's review (`analysis/REVIEW.md`, finding 2): all strikes of a 5pm event settle on one BTC close, so a day acts like one leveraged bet. The daily-mean P&L has a standard deviation of tens of cents against an expected net edge of 1 to 3¢. `power_sim.py` reproduces this independently:

| Design (synthetic) | Mispricing | Net edge per contract | Days for 80% power, plain P&L | Days, hedged P&L |
|---|---|---|---|---|
| Daily 5pm BTC, as stage 2 | 4¢ | 2.1¢ | ~810 | ~1 |
| Daily 5pm BTC, as stage 2 | 5¢ | 2.3 to 3.1¢ | ~550 | <1 |
| Daily 5pm BTC, rough world | 5¢ | 1.4 to 3.0¢ | ~1,500 | ~2 |

(Normal approximation from the per-day spread over 300 simulated days. "Rough world" is defined below.)

So the bottleneck is settlement noise, and there are two ways to beat it: more independent settlements, or a statistic with less noise per settlement. Stage 3 does both. The hedge alone would rescue even the daily design on paper, but its power then rests on one settlement a day and on p_opt's delta being good, which is too fragile to rely on alone. Hourly events make the plain P&L reach usable power too, which gives an independent check.

## What exists (metadata check, 2026-11-06 03:27 UTC)

`discover_series.py` ran in CI (job `discover-series` on PR #8). It prints metadata only.

| Series | Frequency | Settled by | Strikes seen | Usable for stage 3 |
|---|---|---|---|---|
| KXBTCD | hourly | CF Benchmarks | hourly event: 188 "greater" strikes, $100 apart; 5pm event: 50 strikes, $500 apart | **yes** (non-5pm events) |
| KXETHD | hourly | CF Benchmarks | hourly: 300 strikes, $5 apart; 5pm: 50, $40 apart | **yes** |
| KXBTC, KXETH | hourly | CF Benchmarks | brackets ($100 / $5) | reference only, like stage 2's brackets |
| KXBTC15M, KXETH15M | fifteen_min | CF Benchmarks | one "greater or equal" market per event | not now (one market per event, and p_opt from daily options is weakest at 15 minutes) |
| KXSOLD, KXXRPD | hourly | CF Benchmarks | many | no: Deribit has no liquid SOL/XRP options for p_opt |
| KXBTCMAXW (weekly high) | weekly | | no open events | no: path-dependent, few events |
| KXBTCY, KXETHY | annual | | | no: far too few events |

Deribit lists daily 08:00 UTC expiries for both BTC (946 instruments) and ETH (812), so both chains can price an hourly close.

At 03:27 UTC only two KXBTCD events were open: the next hourly one (closing 04:00 UTC) and the 5pm one. So an hourly event seems to trade for about an hour. **To confirm in the pilot:** whether every hour has an event, when each opens, and how wide hourly spreads are (no quote was looked at).

## Options considered

| Option | Verdict |
|---|---|
| Record the daily 5pm events for longer | Rejected. 550+ days. |
| Weekly contracts | Rejected. Fewer settlements, not more. |
| Add ETH to the daily design | Rejected alone. BTC and ETH move together (correlation about 0.8), so this is well under 2× the information. |
| Hourly KXBTCD + KXETHD | **Chosen.** 48 settlements a day. |
| 15-minute contracts | Deferred. One market per event and the weakest fair value. A possible stage 4. |
| Delta-hedged P&L as the statistic | **Chosen** as primary, with the plain P&L required to agree in sign. |
| Treat each day as a cluster | **Chosen.** Conservative: hourly events within a day share a volatility regime and possibly a mispricing regime. |

## The power simulation

`power_sim.py` (run `python3 docs/stage3/power_sim.py`; `--quick` is the CI smoke test). Results: `power_results.json`.

**World.** BTC and ETH follow geometric Brownian motion on a 1-minute grid, correlation 0.8, with a fresh volatility each day (lognormal around 50%, ETH 1.25× BTC). Kalshi's mid is the true probability shifted by ±δ, with the sign drawn once per event (so a mispriced event is wrong the same way at every strike, which is the hardest case), rounded to the cent and quoted ±1¢. p_opt is the true probability plus 0.5¢ of common noise per snapshot and 0.5¢ per strike, close to the 0.3 to 0.5¢ stage 2's review measured for the out-of-the-money fit. Snapshots every 5 minutes. The trade rule is stage 2's S2 with an entry threshold τ: the first row per market whose better-side gap net of the taker fee exceeds τ buys one contract.

**Rough world** (the one the design is sized on). The true process adds jumps (6 a day of about 0.6%, about a fifth of the variance, total volatility unchanged), and p_opt uses a plain lognormal with that day's volatility times a 15% lognormal error. The truth is computed exactly (the Merton jump-diffusion digital, checked against Monte Carlo in the smoke test), so δ = 0 is still exactly no edge, while p_opt is now systematically wrong. This is the world where an ex-ante gap test like S1 is fooled.

**Test.** Pooled mean net P&L per contract, with a day-clustered standard error. PASS if the one-sided 95% lower bound (Student t, days − 1 df) is above 0. KILL if the upper bound is below 1¢, or if there are fewer than 200 trades. Power for N days comes from resampling N days out of 800 simulated ones, 4,000 times.

### Results: hourly BTC + ETH, τ = 1¢

Mispricing δ is the gap between Kalshi's mid and the truth. The net edge is what a trade actually earns after the 1¢ half spread and the fee (about 1.7¢ at 50¢), so δ = 3¢ leaves almost nothing.

| World | δ | Net edge | Ex-ante gap (S1-style) | Trades/day | P(PASS) hedged, 14 / 21 / 28 days | P(PASS) plain P&L, 14 / 28 / 42 days |
|---|---|---|---|---|---|---|
| ideal | 0 | (few trades) | 1.2¢ | 0.6 | 0 / 0 / 0, KILL 100% | 0 / 0 / 0 |
| ideal | 4¢ | 2.0¢ | 2.2¢ | 351 | 1.00 / 1.00 / 1.00 | 0.57 / 0.81 / 0.93 |
| ideal | 5¢ | 3.1¢ | 3.1¢ | 376 | 1.00 / 1.00 / 1.00 | 0.94 / 1.00 / 1.00 |
| **rough** | **0** | **−2.0¢** | **+2.8¢** | 198 | 0 / 0 / 0, KILL 100% | 0 / 0 / 0, KILL 95–100% |
| **rough** | 3¢ | 0.3 to 0.4¢ | 3.1¢ | 271 | 0.28 / 0.32 / 0.38 (KILL 0.38 / 0.56 / 0.69) | 0.08 / 0.10 / 0.12 |
| **rough** | **4¢** | **1.5 to 1.7¢** | 3.4¢ | 319 | **0.98 / 1.00 / 1.00** | 0.47 / 0.74 / 0.88 |
| **rough** | **5¢** | **2.7 to 2.9¢** | 3.8¢ | 384 | **1.00 / 1.00 / 1.00** | 0.94 / 1.00 / 1.00 |

What it shows:

- **The rough null is the important row.** p_opt is wrong enough that the ex-ante gap on traded rows is +2.8¢, so an S1-style test would pass. The realised P&L is −2¢ and the test kills it every time. The outcome-based test can't be fooled by a bad fair value; it can only lose power.
- **At δ = 3¢ the net edge is about 0.3¢, below the 1¢ the test is sized for.** That's correct behaviour, not a failure: a 3¢ mispricing doesn't survive a 1¢ half spread and the fee. Read the coordinator's "3 to 5¢ edge" as: the test decides reliably once the mispricing is 4¢ or more (a net edge of about 1.5¢ or more) at a 1¢ half spread. If hourly spreads turn out wider, the mispricing needed rises one for one.
- **The hedge is worth a factor of about 10 to 25 in days.** Hedging on the 5-minute snapshots instead of a 1-minute index grid costs little (the 5-minute row in `power_results.json`: at δ = 4¢, 0.95 at 14 days against 0.98).
- **Single coin:** hourly BTC alone, ideal world, δ = 4¢: hedged 1.00 at 14 days; plain P&L 0.62 at 28 days and 0.87 at 56. Adding ETH cuts the days the plain P&L needs by about a third (0.81 at 28 days), less than half because the two coins move together.

### Event count for 80% power

| Target | Statistic | Days | Settlements (hourly events, both coins) |
|---|---|---|---|
| δ = 5¢ (net ≈ 2.8¢), rough world | plain P&L | about 7 to 10 | about 340 to 480 |
| δ = 4¢ (net ≈ 1.6¢), rough world | plain P&L | about 32 to 35 | about 1,550 to 1,700 |
| δ = 4¢, rough world | hedged | under 7 (0.81 at 7 days) | under 340 |
| Daily 5pm only, δ = 5¢ | plain P&L | about 550 to 1,500 | the same number of days |

(Trades per day run 200 to 380 in the sim. The real hourly BTC events have $100 strikes, about 2.5× denser than the sim's, so there will be more trades, but trades within an event are almost perfectly correlated, so this changes little.)

**Chosen length: 28 days.** The hedged test has more than 95% power at δ = 4¢ in the rough world from about 14 days, so 28 leaves room for a hedge that works worse in reality than in the sim (basis to the settlement index, intraday volatility pattern) and for lost coverage (the floor is 21 counted days). And the plain P&L, which doesn't depend on the hedge, reaches 74 to 81% at δ = 4¢ and about 100% at δ = 5¢ by 28 days, so the sign-agreement condition rarely blocks a true pass.

### What the simulation does not cover

- **Kalshi's real hourly spreads and depth.** It assumes ±1¢ and fills at the touch. A wider spread raises the mispricing needed one for one. The pilot will measure spread widths in counts-only form before the test is frozen.
- **Latency.** A quote that looks stale against Deribit is the most likely to be pulled first. Neither stage 2 nor 3 can see this. A pass leads only to a paper test that measures it.
- **The settlement index.** Kalshi settles on a 60-second average of the CF Benchmarks real-time index, not Deribit's index. The basis adds hedge noise, not bias.
- **The maker test (T2).** There is no fill model to simulate it with, so its power is unknown.
- **Mispricing that only exists in some hours** (say, quiet Asian hours). Clustering by day handles the dependence, but power then depends on how many hours carry the edge.

## Recorder changes (new code, nothing in stage 2 changes)

The stage 2 recorder, its workflow, `stage2-data` branch and analysis stay exactly as they are. Stage 3 gets its own:

| Item | Stage 2 | Stage 3 |
|---|---|---|
| Script | `stage2/record_snapshot.py` | `stage3/record_snapshot.py`, forked from it |
| Workflow / concurrency group | `stage2-recorder` | `stage3-recorder` |
| Data branch | `stage2-data` | `stage3-data` |
| Kalshi | KXBTCD + KXBTC lists, 5pm books | KXBTCD + KXETHD lists (KXBTC/KXETH for reference), books for **hourly** markets with a quote inside 3–97¢ |
| Deribit | BTC chain, expiries ≤ 10 days, `btc_usd` index | BTC and ETH chains, expiries ≤ 3 days, both indices before and after the Kalshi pull |
| Hedge path | none | a 1-minute poll of both Deribit indices inside the loop (`index_1m.csv`) |
| Validity | 5 s sync, 0.10% index move | the same, per coin |
| Outcomes and tape | pulled after the end | the same: pulled once, after the 28 days |
| Start / end | Nov 5 to Nov 19 | first slot ≥ 2026-11-20 00:00 UTC (or approval, if later), 28 days |

- **Load:** about 40 order-book requests per 5-minute snapshot instead of about 15. At the existing 0.15 s spacing that's about 6 to 8 s. Well inside Kalshi's public limits as far as known (not verified), and the step trace will show it.
- **Storage:** stage 2 snapshots are about 20 to 25 KB gzipped (sizes of the files on `stage2-data`, contents not opened). With ETH and hourly books, expect 50 to 80 KB, so about 15 to 25 MB a day and 0.4 to 0.7 GB for 28 days. That's fine for one branch. Squash or archive it after the analysis.
- **Running cost:** GitHub-hosted minutes are free on public repos. 28 days of a continuous loop is about 40,000 runner-minutes, the same pattern as stage 2. Public data needs no keys.
- **Starting after stage 2 ends** avoids two loops competing on one repo and keeps stage 2's recorder untouched. Running both at once would also work (separate concurrency groups), if Mattias wants stage 3 to start sooner.

### Before the start (each step needs nothing from stage 2's data)

1. **Mattias approves the draft** (or edits it).
2. **Write `stage3/record_snapshot.py` and its workflow.** Test them with a 12-minute `workflow_dispatch` run and a 48-hour **counts-only pilot**, like stage 2's `preflight`: event schedule per hour, strikes per event, the share of snapshots that are valid, spread widths as a histogram of tick counts, book counts. No mids, no p_opt, no outcomes. The pilot data is thrown away and never enters the test.
3. **Write `analysis/analyze_stage3.py` on synthetic fixtures** (reusing stage 2's fitter), with tests. Freeze it and record its sha256 in the pre-registration.
4. **Re-check the Kalshi fee schedule** for KXBTCD and KXETHD hourly events (`fee_multiplier` 1 was seen for both; maker fees not checked).

## Blinding

- This design used no stage 2 data. It should not be revised after stage 2's results are seen, except through the deviations log with a note that the results were known.
- Stage 2's recorder also stores the hourly KXBTCD markets in its market lists, since it pulls every open KXBTCD market. **Those must not be used for stage 3**, not even as a pilot: by the time anyone analyses them, stage 2's results will be known, and the BTC path is shared.
- **The hedge idea is new to stage 3.** It could also be applied to stage 2's data as a reference figure. Doing that after stage 2's results are seen would be exploratory only and must be labelled so. It can't change any stage 2 verdict.

## Decisions (2026-11-06)

1. **Pre-registration approved** (Mattias, 03:51 UTC, then automatic approval at 03:55 UTC while he was away). The red-team edits and the fee rounding were added under the automatic approval before the freeze.
2. **Start after stage 2 ends**, the first slot at or after 2026-11-20 00:00 UTC, as the pre-registration says.
3. **T2 (maker) stays a secondary gate.** Only T1 can justify a next stage (review edit).

**Still to do before the start** (none of it changes a rule): write the stage 3 recorder and its workflow, run the 48-hour counts-only pilot, write and freeze `analyze_stage3.py` on synthetic fixtures, and re-check the fee schedule.
