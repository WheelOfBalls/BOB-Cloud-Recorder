# Stage 2 analysis: readings of the pre-registration

`analyze_stage2.py` follows `docs/PREREGISTRATION_stage2.md` (a verbatim copy of `stage2/PREREGISTRATION.md` in the BOB folder, sha256 `e2dee34a…233e`), including deviations 3 and 4. The pre-registration leaves the points below open. Each one lists the reading the script takes and the main alternative, so a reviewer can object before the test runs. None of these was chosen by looking at data: the script was written and tested on synthetic fixtures only. The only real file opened was one snapshot from 2026-11-05 16:23 UTC, for the file format. That event cannot qualify (deviation 3), and no outcome or trade was looked at.

Items marked **(material)** could plausibly move a result.

## Which rows enter the tests

1. **(material) Rows come only from settled events that qualify under the 80% rule** on the merged series. The pre-registration says a test "needs" 10 such events, but it doesn't say whether rows from non-qualifying events (Nov 5, Nov 19, or any day with a long outage) also count. Excluding them seemed the natural reading, since the 80% rule exists to keep thinly covered events out. Alternative: all rows, with the 10-event count used only as a gate.
2. **Settled** means the event has closed and every one of its markets has a non-empty `result` from Kalshi. A voided market loses only its own S2 and S3 rows.
3. **A two-sided quote** means `0 < yes_bid < yes_ask < 1`. Kalshi reports a missing side as 0 or 1.
4. **The mid band is inclusive**: [0.06, 0.94]. **Hours to close** must satisfy 0 < h < 30, measured from the time the Kalshi market-list request finished.
5. **5pm markets** are those whose `event_ticker` ends in `17`, the same test the recorder and `status.py` use.

## Fair value

6. **(material) Fit inputs.** The fit uses out-of-the-money Deribit options only (calls with K ≥ F, puts with K < F, F being that option's own `underlying_price`) that have `bid_price > 0`, `ask_price ≥ bid_price` and a non-missing `mark_iv`. The fit is ordinary least squares on total variance w, with no weights. *Changed in review, before any data was analysed (see `REVIEW.md`, finding 1):* the first version also used in-the-money options. With Deribit's real tick sizes (0.0001 BTC below 0.005, 0.0005 above) and spreads, an in-the-money mid is mostly tick noise once intrinsic value is taken out, and the unweighted fit then put p_opt off by a median 2 to 5 cents on synthetic chains, about the size of the half spread plus fee that S1 measures. Out-of-the-money only brings that to about 0.3 to 0.5 cents (test `test_p_opt_survives_exchange_ticks_and_spreads`). The pre-registration says only "two-sided option mids", so this stays within its wording. Alternatives not taken: a vega or spread weighting.
7. **Price units.** Deribit quotes BTC options in BTC, which is the Black-76 USD price divided by `underlying_price`. Implied w is inverted on that normalised price. The recorded snapshot's `mark_price` and `mark_iv` reproduce under this convention to 3e-4 BTC (a unit test checks it).
8. **Forward.** Each option's k uses its own `underlying_price`. The expiry's forward F is the median `underlying_price` across that expiry's options.
9. **Interpolation "at fixed k".** The forward at the Kalshi close is interpolated linearly in calendar time between the two expiries. k = ln(K / F_T) is then held fixed while w is interpolated. Before the first expiry, F is that expiry's forward and w is scaled by τ_T / τ_1.
10. **Time.** Calendar seconds on an ACT/365 basis. Deribit expiries are taken as 08:00 UTC. "Now" for the fair value is the moment the Deribit chain request finished (`deribit.t1`).
11. **Missing expiries.** An expiry needs at least 4 usable options to fit. Expiries that fail to fit, or have already expired, are skipped, so the nearest fitted expiries on each side are used. A close after the last fitted expiry gets no p_opt, and the row is dropped and counted. With daily 08:00 expiries this should not happen for a 22:00 close within 30 hours.
12. **(material near the close) Derivative step.** p_opt = (C(K−50) − C(K+50)) / 100, a central difference with $50 on each side. The method says "a step of $50", which could also mean ±$25. In the fixtures the $50 step is accurate to under 0.001 more than 2 hours out, but it is off by up to 0.005 seven minutes before the close, where the distribution is only about $150 wide. This affects the last-hour rows most.
13. **Failure cases.** If the cubic gives w ≤ 0 at K ± 50, or p falls outside [0, 1], the row is dropped and counted. The cubic is not clamped outside the range of fitted k.

## Tests

14. **The fee** is used as written, 0.07·q·(1 − q), with no rounding. Kalshi's fee schedule (effective 2026-07-07) rounds so that fee plus cost lands on a centicent ($0.0001), so rounding barely matters. S1 is also reported with the fee rounded up to a whole cent, which is a conservative upper bound, for reference only. The same schedule charges makers nothing on series it does not list, and KXBTCD is not listed, which matches "makers pay no fee". Check the schedule again before the run.
15. **The S2 side** is whichever of the two gaps is larger, with ties going to YES. The P&L includes the taker fee on entry and nothing at settlement.
16. **S3 price and depth.** The resting price is the best bid from the market list, the same pull that is synchronised with Deribit. The NO bid is 1 − `yes_ask`. **(material)** Depth is the larger of (a) the contracts at that exact price in the recorded order book and (b) the top-of-book size from the market list (`yes_bid_size_fp` for YES, `yes_ask_size_fp` for NO). The book is pulled a few seconds after the list, so the two can disagree. Taking the larger is the stricter choice, which fits "this assumes nobody ahead cancels, so it is strict". Alternative: use the book only.
17. **(material) S3 order life.** An order rests from the end of that snapshot's Kalshi market-list request until the start of the next recorded snapshot's request (valid or not), and never longer than 300 s. Trades count if they fall in (start, end].
18. **S3 fill.** An order fills only if strictly more contracts traded than the recorded depth. A resting YES bid at p is hit by trades with `taker_side = "no"` at `yes_price = p`. A resting NO bid at q is hit by `taker_side = "yes"` at `yes_price = 1 − q`. Prices are matched to within 1e-6.
19. **The S3 statistic** is Σ P&L / Σ price paid across fills: return per dollar, weighted by dollars, as in stage 1. The plain mean of per-fill returns is also stored.
20. **Bootstrap.** 2,000 percentile resamples over days, where a day is one 5pm event. It uses a ratio estimator (resampled Σ numerator / Σ denominator) and seed 20261105, as in stage 1.
21. **An incomplete result** still shows the numbers, but every verdict is INCOMPLETE.

## Deviation 4 merge and coverage

22. **Slot phase.** One phase, the median of t mod 300 over both sources' snapshots. The script prints each source's own median so a mismatch would be visible.
23. **(edge case) "The local snapshot".** This is the first local snapshot in the slot, the one `status.py` picks. If that one is invalid and a later local snapshot in the same slot is valid, the merge uses the first valid cloud snapshot rather than the later local one. Alternative: the first valid local snapshot.
24. **Per-source reference results** use `status.py`'s rule on that source alone: the first snapshot in a slot counts.
25. **Coverage counts a slot for an event** only if that event is listed in the chosen snapshot, as in `status.py`.

## Reference results

26. **Calibration** compares p_opt and the mid on each market's last row more than 1 hour before close. Log loss is clipped at 1e-6.
27. **KXBTC brackets.** Brackets are included for 5pm KXBTC events on days whose KXBTCD event qualifies. They use the same row filters and the same S1 gap formula. A "between" bracket's p_opt is P(>floor) − P(>cap).
28. **Truncated tapes** (over 400 pages) are counted and printed, not excluded.

## Guard rails in the code

- `run` refuses to run on real data before the end time, refuses while any qualifying event is still open, and refuses if `stage2_results.json` already exists in the output folder. On real data `--end` must say 2026-11-19 15:25 UTC (hard-coded), so it can't be moved earlier. `--now` works only on synthetic fixtures: every folder must hold a `SYNTHETIC_FIXTURE` marker *and* every snapshot must carry `"synthetic": true`, which real recorder snapshots never do.
- `pull_after.py` refuses to pull outcomes or trades before the end time, and refuses an `--end` file that moves it.
- These guards stop accidents, not a determined person: a second `--out` folder still allows a second run. The record that counts is the script's sha256 in the result file, matched against the frozen version in `REVIEW.md`.
- `coverage` reads snapshots only, never outcomes, and can be run at any time.

## Things a reviewer should check that are not readings

- The 0.10% index-move rule compares two separate index calls. `index_after` is taken after the KXBTCD pull but before the KXBTC pull, so brackets fall outside the synchronised window by about a second.
- Kalshi settles on the CF Benchmarks BRTI, while the fair value uses Deribit's forward. This is a known limit in the pre-registration and is not corrected here.
- Runtime: about 60 s per 10 days of synthetic snapshots with 70 options each. Real snapshots carry about 290 options, so expect several minutes.
