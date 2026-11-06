# Stage 3 analysis: readings of the pre-registration

`analyze_stage3.py` follows `docs/stage3/PREREGISTRATION_stage3.md` (frozen 2026-11-06, sha256 `a62576a8…c515`), which is not edited. Where it leaves a point open, the reading taken is listed here with the main alternative, so a reviewer can object before the test runs. Nothing here was chosen by looking at data: the script was written and tested on synthetic fixtures (`tests/make_fixture_stage3.py`). The only real files it has read are counts-only `preflight` runs on the first pilot snapshots (to check the format). No price, gap, p_opt, outcome or trade from real data was printed or looked at. Recorder readings are in `stage3/NOTES.md`. Items marked **(material)** could plausibly move a result.

## Rows

1. **(material) Which rows count.** A row needs its snapshot's UTC day (by slot time) **and** its event's close day to be counted days. The pre-registration says "rows from days that don't count are dropped" without saying which day. Only the snapshots at 23:02:30 to 23:57:30 can differ (their events close at 00:00 the next day). Alternative: the close day only.
2. **A row needs that coin's snapshot to be valid** (per-coin validity). The day rule needs both coins; a slot valid for BTC only still gives BTC rows.
3. **Minutes to close** are measured from the end of that coin's Kalshi market-list request, inclusive: 2 ≤ minutes ≤ 60. The mid band is inclusive, [0.06, 0.94]. A two-sided quote means 0 < bid < ask < 1. (Stage 2's conventions.)
4. **Hourly market** = event ticker not ending in `17`. Only `greater` (and, if one ever appears, `less`) markets are single-strike rows; anything else is counted as dropped.
5. **The first snapshot in a slot counts** (stage 2's rule). Slots come from the recorder's `slot_target`.

## Fair value

6. **"Now" for p_opt** is the end of the `index_before` request, the latest input p_opt uses. Both the chain fit's τ and the time to the close are measured from it. The chain and `index_before` both end before the Kalshi request starts (the recorder's order), so there is no look-ahead.
7. **A close exactly at the first expiry** (the 08:00 UTC hourly close against the 08:00 Deribit expiry) is treated as "before the first expiry": forward = `index_before`, w scaled by τ_T/τ_1 (= 1). Alternative: the expiry's `underlying_price`, which the pre-registration's reason (the futures basis) argues against.
8. **"The fitted at-the-money total sd to the close"** is √W(k = 0), with k measured from the forward used (the index). It sets the difference step h = min($50, 0.1·F·sd) (BTC) or min($2.50, …) (ETH), the row-sync threshold 0.1·F·sd and the stale-quote threshold 0.25·F·sd.
9. **Variance for the delta**: W at the strike's own k, the variance the trade's snapshot fitted, scaled linearly by the time left at each hedge point.

## T1

10. **Fee** f(q) = ceil(0.07·q·(1 − q) × 10⁴) / 10⁴ per 1-contract trade (rounded up to the centicent). The whole-cent version is reported only.
11. **Ties** between the YES and NO gaps go to YES (stage 2).
12. **One trade per market**, at its first row with g > τ. If that market has no yes/no result, its trade is dropped and counted (`unsettled_trades_dropped`), and the market is not traded later.
13. **(material) The hedge path.** It starts at `index_after` of the trade's snapshot, then takes every 1-minute poll whose request *started* after `index_after` ended, up to and including the poll targeted at the close. A missing minute is skipped, so its move rolls into the next step. If the close's own poll is missing, the path ends at the last poll before it, and the move after that is unhedged. Alternative: drop such trades (that would select on data availability).
14. **Δ** = ∂N(d₂)/∂S at each point, with S the Deribit index at that point; sign + for YES on an "above" market, − for NO (flipped for a "below" market).
15. **D in the se formula** is the number of days with at least one trade. A counted day without trades contributes nothing to the sums either way; counting it would only raise D/(D − 1) and the degrees of freedom.
16. **"Unhedged μ > 0"** in the PASS rule is the point estimate (the pre-registration gives no bound for it).

## T2

17. **The maker rule is stage 2's S3, applied to the same rows as T1**: at every row, a 1-contract order rests at the best bid on each side whose p_opt value is above the bid; it lives from the end of that coin's Kalshi list request to the start of the next recorded snapshot's request for the same coin, at most 300 s; it fills only if strictly more contracts traded at that price against it than the recorded depth (the larger of the book level and the top-of-book size); held to settlement; no fee. Stage 2's `tape_volume` and `book_depth` are reused.
18. **T2's bounds** use the same day-clustered t interval as T1, applied to the dollar-weighted ratio (x_d = P&L, n_d = dollars paid). PASS if the one-sided 95% lower bound > 0; KILL if under 200 fills or the upper bound < 0. Stage 2 used a percentile bootstrap; the stage 3 pre-registration says "all inference clusters by UTC day" with the t formula, so the formula is used.

## Reported figures

19. **Bootstraps**: percentile, ratio estimator, 2,000 resamples, seed 20261120, over days; the 7-day version resamples blocks of 7 consecutive days counted from the first day with a trade (four blocks in 28 days).
20. **Stale-quote split**: the reference index is the latest 1-minute poll whose request started at least 60 s before `index_before`'s request (so 60 to 120 s before). Trades with no such poll are counted as unknown.
21. **The 5-minute hedge**: `index_after` of each later snapshot of that coin (valid or not) before the close, then the close's 1-minute poll.
22. **Calibration** uses each market's last row at least 5 minutes before the close, over all rows (not just traded ones), comparing p_opt and the mid with Brier score and log loss (clipped at 1e-6), with day-clustered intervals.
23. **Ex-ante gap on traded rows** is g at the trade's row, the S1-style figure the review warns can mislead.

## Guard rails

- `run` refuses real data before 2026-12-18 00:00 UTC, refuses any snapshot whose `mode` is not `live` (pilot data never enters the test), refuses a moved window, and refuses to overwrite `stage3_results.json`. `--now` works only when the folder has a `SYNTHETIC_FIXTURE` marker *and* every snapshot says `"synthetic": true`.
- `coverage` and `preflight` print counts only and also accept pilot data, so the format can be checked before the start.
- `pull_after_stage3.py` refuses before the end and on non-live snapshots.
- The script imports stage 2's fitter. The result records the sha256 of both files; the frozen values are in `FROZEN_stage3.md`.

## What the fixtures show (synthetic only)

On 22 synthetic days with an exact fair value: a planted 6¢ mispricing passes T1 (hedged estimate within noise of the ex-ante gap, hedged se about 10× smaller than unhedged); no mispricing gives no trades and a KILL; a fair value from a 30% too low volatility produces a positive ex-ante gap on many trades and still KILLs on realised P&L; maker fills that are always adverse KILL T2. With uninformed random fills a maker earns the half spread and T2 passes even with no mispricing, which is why only T1 can justify a next stage.

**Deviation 1 (2026-11-06).** The row-sync threshold in item 8 now only flags rows (`sync_ok`); it no longer removes them from T1 or T2. T1 recomputed with the rule applied is reported as `T1_with_preregistered_row_sync_rule`. See the pre-registration's deviations log and `docs/stage3/REVIEW_code.md` finding 1.
