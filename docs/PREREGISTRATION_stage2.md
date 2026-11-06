# Crypto stage 2 pre-registration (written 2026-11-05, before the first snapshot)

Stage 1 passed (`../RESULTS.md`). This fixes stage 2 before any data exists. The report's rule, from K's red team:

> for 2 weeks, snapshot Kalshi KXBTCD/KXBTC books every 5 min with synchronous Deribit-implied digitals (from public current chains). Compute the ask-side gap net of the 0.07 taker fee. Kill if the mean net gap at the touch is ≤0 outside the ≤5c tails.

Public read-only data only. No account, no authentication, no orders. Every trade below is simulated.

## Why this goes beyond the report's rule

- **The rule needs a definition.** Averaged over both sides, the net gap is negative by construction (−spread − fees), so it must mean the better side at each strike.
- **The better side can look positive from noise.** Any error in the options estimate widens |fair − mid|. S2 checks real outcomes to guard against that.
- **It tests takers, while the idea is a maker idea.** It says nothing about the question stage 1 left open: can an outside maker get filled profitably? S3 tests that by replaying the public tape against recorded book depth.

S1 is kept as written. S2 and S3 are added before data, so they are new rules, not rescues.

## Recording

- **Interval:** every 5 minutes for 14 days from the first snapshot. A Windows scheduled task runs `record_snapshot.py`.
- **Each snapshot saves:**
  - Deribit BTC option chain for expiries within 10 days, plus the index before and after the Kalshi pull;
  - top of book for all open KXBTCD and KXBTC markets;
  - full order books for KXBTCD 5pm markets with a two-sided quote inside 3–97¢.
- Request start and end times are stored for each source. A failed request is logged as failed. Nothing is filled in afterwards.

**A snapshot is valid only if** Deribit and Kalshi top-of-book requests finished within 5 seconds of each other, and the Deribit index moved under 0.10% across the Kalshi pull.

**A test needs** at least 10 settled 5pm events, each with at least 80% of its possible snapshots valid. Otherwise the result is reported as incomplete, not as a pass or a kill.

## Fair value (fixed now, so it can't be tuned to the result)

p_opt is the risk-neutral probability that BTC ends above the strike at the Kalshi close.

1. For each Deribit expiry, fit total variance w(k) against log-moneyness k = ln(K/F) from two-sided option mids, using a cubic in k with `underlying_price` as forward F. Options with mark_iv missing are dropped.
2. If the Kalshi close falls between two expiries, interpolate w linearly in calendar time at fixed k. If it falls before the first expiry, scale that expiry's w by time remaining.
3. p_opt is the numerical derivative −dC/dK of the Black price at the strike, with a step of $50.

There is no intraday variance clock. No discount is applied, as the horizon is under two days.

## Tests

**Rows:** valid snapshots × KXBTCD 5pm markets with a two-sided quote, mid in [0.06, 0.94], and under 30 hours to close.

Taker fee f(q) = 0.07·q·(1 − q). Makers pay no fee.

| # | Test | Definition | Kill if |
|---|---|---|---|
| S1 | Report's rule | g = max(p_opt − ask − f(ask), (1 − p_opt) − (1 − bid) − f(1 − bid)); mean of g across rows | Mean ≤ 0 |
| S2 | Do positive gaps pay? | Take the first row with g > 0 for each strike and event, and buy that side at the touch. Mean realised P&L per contract after fees | Mean ≤ 0 |
| S3 | Outside maker | See below. Mean realised return per dollar across simulated fills | Mean ≤ 0, or fewer than 100 fills |

Each is judged on its point estimate. 95% CIs from a bootstrap over days are always reported next to it.

**S3 rule.** At each snapshot, for each row:

- rest a 1-contract order to buy YES at the best YES bid if p_opt > that bid;
- rest a 1-contract order to buy NO at the best NO bid if (1 − p_opt) > that bid;
- the order joins the back of the queue and is cancelled at the next snapshot.

**S3 fill.** The order fills only if the public tape shows more contracts traded at that exact price and side, before the next snapshot, than the recorded depth at that price. This assumes nobody ahead cancels, so it is strict. Held to settlement.

## How the outcomes will be read (fixed now)

- **Any kill ends the idea as written.**
- **S1 or S2 kills, S3 does not:** the options anchor is dead for takers. The maker premium stays open only as a new hypothesis.
- **S3 kills:** an outside maker couldn't capture stage 1's return in this sample, and the idea stops.
- **All pass:** this justifies a longer forward paper test. It does not validate an edge. Fourteen daily events is far too few, and strikes on a day are strongly linked.

## Reported, never used to rescue a kill

- S3 with half the recorded depth, the 50% queue haircut from J's plan.
- S3b: the same fill rule resting on both sides regardless of p_opt, which measures the raw premium for a back-of-queue maker.
- S3 by hours to close, including the last hour.
- p_opt against mid, in Brier and log loss, on the final snapshot before T−1h.
- KXBTC bracket gaps.

## Limits known in advance

- Fourteen events, one market period.
- Depth is seen every 5 minutes, not continuously. Orders that arrive and leave between snapshots aren't visible.
- 1-contract fills ignore size. A larger order would fill less often.
- Deribit's option chain has a mark price for every strike but thin bids at some, and BRTI differs slightly from Deribit's index.

## Deviations log

1. **2026-11-05, first day of recording.** About an hour was lost, with no snapshots between 15:23 and about 16:23 UTC. Scheduled tasks default to low priority, and with this computer short of memory Python could not start before the 4-minute limit. A faulty diagnostics edit of mine also broke the recorder for part of that hour. The task now runs at normal priority and the edit is fixed. No rule changed. The gap counts against coverage for that event like any other.
2. **2026-11-05.** The recorder gained a step trace (`data/trace.log`) and a 170-second watchdog (`data/hang_log.txt`), so a stuck run ends itself and leaves a record. What is recorded did not change.
3. **2026-11-05 18:41 UTC, before any analysis.** "Possible snapshots" in the 80% rule means all 360 five-minute slots in the 30 hours before an event's 5pm close, not only the slots after recording began. So the Nov 5 and Nov 19 events cannot qualify, and at most 13 events (Nov 6 to Nov 18) can. This settles a wording gap that the rule left open. The rule itself is unchanged. `status.py` reports coverage on this basis.
4. **2026-11-05 19:30 UTC, before any analysis.** A second, identical recorder now runs in GitHub Actions (repo `WheelOfBalls/BOB-Cloud-Recorder`, branch `stage2-data`), because this computer often loses power and wifi. Its first snapshot was at 19:28:02 UTC. It fetches the same public data with the same code, at the same 5-minute phase (hh:m3:02 UTC), and each snapshot records its source, run id and target slot. The Windows recorder is unchanged. How the two are combined is fixed now:
   - Both sources' snapshots are assigned to 5-minute slots the same way `status.py` does.
   - For each slot, use the local snapshot if it is valid. Otherwise use the first valid cloud snapshot in that slot. If neither is valid, the slot is invalid. The validity rule itself is unchanged.
   - Exactly one snapshot per slot enters the rows, and each row is tagged with its source.
   - The merged series is what the tests and the 80% coverage rule use. Coverage and S1 to S3 are also reported for each source on its own, for reference only. They are never used to choose between sources or to rescue a kill.
5. **2026-11-06 03:14 UTC, before any analysis.** How S2 is read, fixed while every result is still unseen. With 10 to 13 events S2 has little power: every strike of a day settles on the same BTC close, so a day acts like one bet. A simulation on synthetic data (`analysis/REVIEW.md`, finding 2) gave about a 40% chance that S2 kills a true 5¢ mispricing, and about a 20% chance that S1 and S2 both pass with no edge at all when p_opt carries 4¢ of noise. The gates are unchanged: an S2 kill is still a kill and ends the idea as written. But an S2 kill is not evidence that no mispricing exists, and an S2 pass is not evidence that one does. The bootstrap CI is reported next to it and is expected to be wide.
