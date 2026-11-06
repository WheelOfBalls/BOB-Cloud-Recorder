# Adversarial review of the stage 2 analysis (2026-11-06)

Scope: `analyze_stage2.py`, `pull_after.py`, `NOTES.md`, `tests/` and `docs/PREREGISTRATION_stage2.md` as merged in PR #4, plus the deviation 4 merge rule shared with `status.py` (PR #3). Everything below was found by reading the code and running it on synthetic data. No real snapshot, outcome or trade was opened, `run` and `pull_after.py` were not run on real data, and the pre-registration was not edited.

The review experiments are in `analysis/review/` and can be rerun (`python3 analysis/review/fitnoise.py`, `power.py`, `daysd.py`).

**Frozen script after this review:** `analyze_stage2.py` sha256 `c0b3dca6c3b9a00364d2bc7b84ca0960bb346d8f28c32a55647d2907cc49e379` (main after PRs #5 and #6). PR #5 added the counts-only `preflight` mode. It was checked here too: it prints fitted-expiry, row and book counts per event, and no prices, gaps, p_opt, outcomes or trades, so it can't leak a result. The result file records the sha256 of the script that produced it. If the two differ, the run used a changed script and needs explaining.

**Needs Mattias:** items marked **[decision]** would change a pre-registered rule, so they need a new deviation that only Mattias can approve. Nothing here was changed on his behalf.

## Ranked findings

### 1. High, fixed in code: the fair-value fit was dominated by tick noise from in-the-money options

The fit used every two-sided option, in-the-money included, with an unweighted least-squares fit on total variance. Deribit quotes BTC options in ticks of 0.0001 BTC below 0.005 BTC and 0.0005 above (about $38). Once intrinsic value is taken out, an in-the-money mid holds almost no time value, so its implied variance is mostly tick noise, and the unweighted fit takes it at full weight. The synthetic fixtures didn't catch this because they quote exactly ±0.0002 around the true price, so every mid is exact.

On synthetic chains with real tick rounding and modest spreads (`review/fitnoise.py`), p_opt was off by these amounts:

| Quotes | All options (before) | Out-of-the-money only (now) |
|---|---|---|
| tightest: 1 tick plus 0.0002 spread | median 1.8 to 2.5¢, p90 about 5¢ | median 0.2 to 0.3¢, p90 0.4 to 0.8¢ |
| 0.0005 + 1% of price | median 2.4 to 3.6¢, p90 5 to 7¢ | median 0.3 to 0.5¢, p90 about 1¢ |
| 0.0005 + 3% of price | median 3 to 5¢, p90 8 to 14¢ | median 0.3 to 0.5¢, p90 about 1¢ |

The half spread plus fee that S1 has to beat is about 2.7¢. So under the old fit, noise alone was about as large as the effect being tested. Because S1 takes the better of two sides, noise in p_opt pushes S1 up, toward a false pass (see finding 2).

**Fix:** use out-of-the-money options only (calls with K ≥ F, puts with K < F), which is standard practice. The pre-registration says only "two-sided option mids", so this stays within its wording, and NOTES item 6 already listed it as the main alternative. A new test, `test_p_opt_survives_exchange_ticks_and_spreads`, fails on the old fit (median error 4.8¢) and passes on the new one. The end-to-end tests still pass. Weighting by bid ≥ 2 ticks or by relative spread was also tried, and it did not help further.

**[decision, optional]** This changes a reading, not a rule, and it was made before any data was analysed. Mattias may still want to log it as deviation 5 for transparency. Suggested wording: "2026-11-06, before any analysis: the variance fit uses out-of-the-money options only (calls K ≥ F, puts K < F). The rule said 'two-sided option mids' without saying which; in-the-money mids were found on synthetic data to add 2 to 5¢ of tick noise to p_opt."

### 2. High, needs a decision: with 10 to 13 events, S2 is close to a coin flip in both directions

`review/power.py` is a simplified Monte Carlo: flat 50% volatility, 17 strikes, quotes 1¢ either side of a cent-rounded mid, the S2 rule as written, and either 10 or 13 events.

| World | P(S1 pass) | P(S2 pass) | P(S1 and S2 pass) |
|---|---|---|---|
| no edge, p_opt noise 0.3¢ (the new fit) | 0.00 | 0.07 to 0.10 | 0.00 |
| no edge, p_opt noise 2¢ plus 1¢ shared (about the old fit) | 0.00 | 0.31 to 0.36 | 0.00 |
| no edge, p_opt noise 4¢ | 1.00 | 0.18 to 0.21 | 0.18 to 0.21 |
| Kalshi mispriced by 3¢, small noise | 1.00 | 0.49 to 0.50 | 0.49 to 0.50 |
| Kalshi mispriced by 5¢, small noise | 1.00 | 0.59 to 0.63 | 0.59 to 0.63 |

(300 simulations per row; the range covers 10 and 13 events.)

Why: all of a day's S2 trades tend to fall on the same side and settle on one BTC close, so each day acts like a single, highly leveraged bet. In `review/daysd.py`, the daily mean P&L per contract has a standard deviation of about 36¢. With a 5¢ mispricing, the expected net P&L is about +1¢ per contract. Detecting that with 80% power would take thousands of days, not 13.

What this means:
- **A KILL from S2 is weak evidence.** A real 5¢ mispricing gets killed about 40% of the time.
- **A PASS is weaker still.** In a world with no edge and 4¢ of p_opt noise, S1 and S2 both pass about 20% of the time. S1 then says more about p_opt noise against the trading costs than about an edge. The bootstrap CI for S2 will be very wide, and it should be read that way.
- The pre-registration already says all-pass "does not validate an edge". It does not say that a kill is just as weak.

**Decided 2026-11-06 03:14 UTC by Mattias: option 1, logged as deviation 5 in the pre-registration.** The options were:
1. *(recommended)* Leave the gates unchanged, and add a sentence to the pre-registration now, before results: "S2 has low power with 10 to 13 events. A simulation gives about a 40% chance of killing a true 5¢ mispricing, so an S2 kill is recorded as a kill, but it is not evidence that no mispricing exists." This changes nothing about the verdicts. It only fixes how they are read, while that can still be done blind.
2. Make S2 a reported-only statistic and leave S1 and S3 as the gates. This is a real rule change, and it would read as a rescue if decided after any result, so it is only defensible now.
3. Change nothing.

S3 does not have this problem to the same degree, because it has at least 100 fills. But fills in one market at one price level are correlated in the same way, so its CI should be read with the same caution.

### 3. Medium, fixed in code: two run guards could be bypassed

- `--end` accepted any file, so `--end <file with a past date>` let `run` work on real data before 2026-11-19, and `pull_after.py` pull outcomes early. Now, on real data, the end time must equal the hard-coded `2026-11-19T15:25:00+00:00`, in both scripts. Coverage mode, which reads no outcomes, is unaffected.
- Real data was treated as synthetic if a `SYNTHETIC_FIXTURE` file sat in each folder, which unlocked `--now` and the other guards. Now every snapshot must also carry `"synthetic": true`, which the recorder never writes.
- **Not fixed (can't be in code):** pointing `--out` at a new folder still allows a second run. These guards stop accidents only. **Suggestion:** run `run` once, on the frozen commit, and commit `stage2_results.{txt,json}` straight away. The script sha256 above and GitHub's timestamp then make a second run visible.

### 4. Medium, judgement: S2 assumes the taker is filled at the snapshot quote with zero latency

S2 buys at the touch recorded in the snapshot. A quote that looks stale against a Deribit move that just happened is exactly the kind that gets pulled before a real order arrives, so S2 is optimistic about execution. The 5 s synchronisation rule and the 0.10% index-move rule limit this, but they don't remove it. Recorded data can't correct it: the next snapshot is 5 minutes later. **Recommendation:** no code change. Read any S2 pass with this in mind. A forward paper test should measure real latency.

### 5. Medium, checked: the fee assumptions still hold, but NOTES had the rounding wrong

According to Kalshi's fee schedule (PDF "last updated and effective July 7, 2026", <https://kalshi.com/docs/kalshi-fee-schedule.pdf>, read through a fetch tool's summary rather than in full):
- The general taker fee is round_up(0.07 × C × P × (1 − P)).
- The maker fee is 0.0175 × C × P × (1 − P), times a per-series multiplier that defaults to 0. KXBTCD and KXBTC are not in the non-standard table. So the pre-registered "makers pay no fee" holds on that schedule.
- Rounding is to the **centicent** (fee plus cost rounded up to $0.0001), not to the cent as NOTES item 14 said. NOTES is corrected. The S1 "fee rounded up to cent" reference is now a conservative upper bound.

**Action for Mattias:** the schedule can change before 2026-11-19. Check it again (especially maker fees on KXBTCD) before the run. A maker fee would hurt S3 by about 0.9% per dollar at 50¢, and adding it would need a deviation.

### 6. Low, agree with the code: the deviation 4 merge choice for duplicate local snapshots

If the first local snapshot in a slot is invalid and a later local snapshot in the same slot is valid, the merge uses the first valid cloud snapshot, not the later local one. Deviation 4 says both sources are "assigned to 5-minute slots the same way `status.py` does", and `status.py` counts the first snapshot in a slot and treats later ones as duplicates. So the code follows the text. The asymmetry, where the cloud gets its first *valid* snapshot but local gets its *first* snapshot, comes from the pre-registration's own wording. It can't be gamed: validity depends only on request timing and the index move, never on prices or outcomes, and both recorders run identical code. Local duplicates should also be rare (they need a run more than 150 s late). No change and no deviation needed.

### 7. Low, agree: the other readings in NOTES.md

- Item 1 (rows only from qualifying events): agree. It is the reading that matches the purpose of the 80% rule.
- Item 12 (±$50 central difference): agree. "Step h" in a central difference conventionally means ±h.
- Item 17 (order life capped at 300 s and ended by the next recorded snapshot): agree.
- Item 19 (S3 weighted by dollars, as in stage 1): agree. Note that the plain mean of per-fill returns, which is also reported, is dominated by cheap contracts and can have the opposite sign. Only the dollar-weighted figure is the gate.
- Item 23: see finding 6.
- **Multiple testing:** the verdict needs all three tests to pass, so no correction is needed for the gate. The risk is the 10 or so reference statistics and the per-source results being used to tell a story after the fact. The pre-registration already forbids that. Keep to it.
- **Look-ahead:** none found. p_opt uses the chain as it stood when its request finished, which is before the Kalshi quote. Row filters use only the close time and quotes at that moment. Which events qualify depends on coverage, and coverage depends only on timing. "Settled" checks only that a result exists, not what it is.

### 8. Low, known limits worth restating

- BRTI vs the Deribit forward, and the 60-second settlement average: a steady basis shifts p_opt the same way at every strike, which is the "S1 passes from noise" pattern in finding 2. It is a known limit, not corrected.
- S3 counts trades at the exact price. Whether Kalshi prints a sweep through several levels as one trade per level is unverified. If it prints one trade at the taker's limit price, S3 misses some fills, which is conservative.
- Truncated tapes: Kalshi pages newest first, so truncation drops the oldest trades and loses fills (conservative). The count is printed.
- KXBTC brackets are about 1 s outside the synchronised window. They are reference only.

## What changed in code (this PR)

- `fit_chain`: out-of-the-money options only (finding 1). NOTES item 6 is updated.
- `analyze_stage2.py run` and `pull_after.py`: `--end` can't move the end time on real data. Synthetic status needs the marker file and a per-snapshot flag (finding 3). The fixture writes the flag.
- NOTES item 14: fee rounding corrected (finding 5). The guard-rails section is updated.
- Tests: realistic-tick fit test, moved-end refusal, stray-marker test.
- `analysis/review/`: the three experiment scripts behind findings 1 and 2.
