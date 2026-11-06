# Stage 3 code review: recorder, run chaining, frozen analysis, fees

Independent skeptical review, written 2026-11-06 (about 06:30 to 08:00 UTC) of the stage 3 recorder (PR #11, `stage3/`), the self-queueing workflow (PR #13), and the frozen `analysis/analyze_stage3.py` (PR #12), against the frozen pre-registration `docs/stage3/PREREGISTRATION_stage3.md` (sha256 `a62576a8…c515`, unchanged by this review).

**What was looked at.** Every line of `stage3/record_snapshot.py`, `stage3/cloud_loop.py`, `.github/workflows/stage3-recorder.yml`, `analysis/analyze_stage3.py`, `analysis/pull_after_stage3.py`, and the parts of `analysis/analyze_stage2.py` that stage 3 imports (`fit_chain`, `tape_volume`, the S3 rule). All existing unit tests pass. **Data used:** synthetic only. From real data I read nothing but the recorder's own logs on `stage3-pilot` (`cloud_loop.csv` run starts and slot timings, and `series_meta.csv` fee fields), and GitHub's list of workflow runs. No quote, index level, p_opt, gap, trade or outcome from the pilot or stage 2 was opened.

**Severity** is about the pre-registered verdict: *critical* can produce a wrong PASS or KILL, *high* can lose the test or a large part of it, *medium* weakens a guard or a reading, *low* costs a little power or clarity.

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **Critical** | The pre-registered row-sync rule selects rows using `index_after`, read after the Kalshi quote. Under a zero-edge null this biases the hedged P&L upward by about 1 to 2¢ per contract | **Needs a deviation** (not applied) |
| 2 | High | The run chain ended with the pilot; the live start depended on a cron firing in a 5-hour window | Fixed in this PR |
| 3 | High | Settlements came only from `GET /markets`; Kalshi moves older settled markets to `/historical/markets` | Fixed in this PR |
| 4 | Medium | Same settlement gap in stage 2's `pull_after.py` (stage 2 pulls after 2026-11-19) | Flagged, not changed (stage 2) |
| 5 | Medium | The one-shot lock is advisory | Flagged; procedural fix suggested |
| 6 | Medium | T2 can rest both a YES and a NO bid on the same row | Flagged; a reading to write down |
| 7 | Low | The 08:00 UTC close uses Deribit options that are about to expire | Reported split suggested |
| 8 | Low | Chain handovers cost about one slot each | Accepted |
| 9 | Low | Smaller points | Accepted |
| F | n/a | Kalshi's fee schedule, checked from the official PDF and the API | Matches the code |

## 1. Critical: the row-sync rule creates a look-ahead selection bias (needs a deviation)

**Rule** (pre-registration, "Row sync [review]"): a row is dropped if |`index_after` − `index_before`| > 0.1 × F σ√τ. `analyze_stage3.py` implements it as written (`snapshot_rows`, `SYNC_FRAC`).

**Why it biases T1.** `index_after` is read *after* the Kalshi response, and the hedge also starts there. A taker could not know it when deciding. Write the spot path inside one snapshot as `before → quote → after`. When the spot moves between `before` and the quote, Kalshi's price moves with it but p_opt (from `before`) does not, so that move triggers trades, and the trade goes against the direction of the move. The hedged P&L is then credited with the move from the quote to `after`. Bounding |after − before| makes the second leg tend to reverse the first, which is exactly the direction the trade bet on. So the rule keeps the triggered trades whose later move happened to favour them. It uses no prices or outcomes, as the pre-registration says, but it uses the spot after the quote, and the hedged P&L depends on that spot.

The size is large for hourly contracts because the threshold is small: 2.5 minutes before a close, a tenth of the remaining sd is about 1 bp, which is roughly one second of BTC moves.

**Evidence (synthetic).**

- *Exact-expectation simulation* (`docs/stage3/review_code/sync_sim.py`). Kalshi's mid is the true probability at the quote instant, rounded to the cent and quoted ±1¢ (a frictionless null with zero edge), and the metric is the expected hedged P&L given the spot at the hedge start. That metric is noise-free, so differences come only from which rows are selected.

  | σ, lags (s, each leg) | trades, no row sync | mean, no row sync | trades, row sync | mean, row sync | bias |
  |---|---|---|---|---|---|
  | 50%, U(0.2, 1.0) | 5,721 | −2.30¢ | 1,934 | −0.42¢ | **+1.9¢** |
  | 35%, U(0.3, 1.5) | 8,034 | −2.31¢ | 2,646 | −0.21¢ | **+2.1¢** |
  | 50%, U(0.05, 0.3) | 325 | −2.18¢ | 148 | −1.22¢ | +1.0¢ |

  The honest null value is about −2.3¢ (half spread plus fee). The stage 2 per-coin validity rule (index moved under 0.10%) was run as a third arm and changes nothing (the same trades, to the digit), so it is not a concern.

- *End-to-end with the frozen code.* `docs/stage3/review_code/e2e_sync.py` builds the test fixture's world (28 days, delta = 0, so no edge) with a spot move inside each snapshot, runs the frozen `analyze_stage3.analyse()`, and compares T1 with the rule on and with it switched off:

  | seed | trades (rule on) | hedged, rule on [95% one-sided bounds] | unhedged, rule on | verdict, rule on | trades (rule off) | hedged, rule off | verdict, rule off | difference |
  |---|---|---|---|---|---|---|---|---|
  | 1 | 189 | -0.82¢ [-3.72, +2.09] | +0.29¢ | KILL | 553 | -1.93¢ | KILL | +1.11¢ |
  | 2 | 168 | +3.26¢ [+0.57, +5.94] | +4.63¢ | KILL (< 200 trades) | 520 | -0.82¢ | KILL | +4.08¢ |
  | 3 | 158 | +0.10¢ [-2.73, +2.93] | -3.22¢ | KILL | 558 | -2.87¢ | KILL | +2.97¢ |
  | 4 | 183 | +0.08¢ [-3.12, +3.29] | +6.62¢ | KILL | 517 | -0.49¢ | INCONCLUSIVE | +0.57¢ |
  | 5 | 216 | -3.06¢ [-6.10, -0.01] | -8.91¢ | KILL | 605 | -3.76¢ | KILL | +0.70¢ |
  | 6 | 154 | -1.92¢ [-4.29, +0.45] | -0.89¢ | KILL | 482 | -3.07¢ | KILL | +1.15¢ |
  | mean | | −0.39¢ | | | | −2.16¢ | | **+1.76¢** |

  The rule raised the hedged mean in all six seeds, by +0.6¢ to +4.1¢ (mean +1.76¢), consistent with the exact simulation. With the rule on, five of the six KILLs come only from the 200-trade minimum; on the hedged mean alone, none of those five would be KILLed. Lags are U(0.3, 1.5) s per leg. Each seed took about 7 minutes.

  In seed 2 the frozen code, on a world with no edge, meets both PASS conditions on the mean (hedged lower bound +0.57¢ > 0, unhedged +4.63¢ > 0). Only the 200-trade minimum turned it into KILL, and the fixture lists 11 strikes per event against about 188 (BTC) and 300 (ETH) on the real series, so real data will clear 200 trades easily. The rule also cuts trades about threefold, so in this world it pushes toward KILL by the trade count and toward PASS on the mean at the same time.

**How large on real data** depends on how quickly Kalshi's quotes follow the index, which nobody can know before the data. If the quotes lag by seconds, fewer trades come from moves inside the snapshot and the bias is smaller. The frictionless case is the worst case, and in it the bias is as large as the 1¢ KILL margin.

**Proposed deviation (for Mattias; not applied).** Drop the row-sync rule from the rows that T1 and T2 use. Keep it only as a reported figure ("T1 with the pre-registered row-sync rule"), never as a gate. The review that added it (`REVIEW.md`) meant it to drop rows whose quote may be out of sync. That job is already done without look-ahead by the 5-second validity rule, the hedge starting at `index_after`, and the stale-quote split, which uses only data from before the snapshot. A weaker alternative is a rule that uses only data from before the quote (for example |`index_before` − the last 1-minute poll before the chain request| > 0.1·F σ√τ). That one is unbiased, but it measures something different, and the stale-quote split already reports it.

Either version changes `analyze_stage3.py`, which is frozen, so it needs a deviations-log entry in the pre-registration, a re-freeze (`FROZEN_stage3.md`), and a regression test (the end-to-end world above, which with the rule removed should give no PASS at zero edge). It must be done **before 2026-11-20 00:00 UTC**, while no live data exists. I did not edit either file.

## 2. High (fixed): the run chain broke at the end of the pilot

After 2026-11-08 06:00 UTC, `mode_at` returned `off` until 5 hours before the live start. The first such run exited and queued nothing, so the chain stopped, and the live recording could start only when GitHub's cron fired between 2026-11-19 19:00 and 2026-11-20 00:00 UTC. On this repo the cron had started no stage 3 run in its first 75 minutes, and stage 2's cron started two runs in 11 hours. A missed window costs live days, and the 21-day minimum leaves room to lose only seven. Inside the live window the same weakness applied to a single failed `gh workflow run`, which was not retried.

**Fix in this PR.**
- A new `wait` mode from the pilot's end to 5 hours before the start. The run records nothing, checks out no branch, sleeps up to 5 h 40 min (or until one minute into the 5-hour lead) and queues its successor. That is about 50 idle runs over 12 days, at no cost on a public repository.
- Every run queues its successor at its start (now with 4 tries) and again at its end, unless the run was cancelled. A newer queued run replaces the older one in the concurrency group, so there is never more than one recorder and one waiting run.
- `off` now means only "after the live window". To stop the chain by hand, disable the workflow.
- Tests: `test_modes` and `test_wait_hands_over_to_live`. `stage3/NOTES.md` item 15.

**Overlap check.** Runs cannot overlap: the concurrency group is shared and `cancel-in-progress: false`, so one runs and at most one waits. A cron firing while a successor waits replaces it, which is harmless. **Still unverified:** that GitHub keeps a queued run waiting for the whole 5 h 40 min. The first evidence comes at about 11:58 UTC today, when the queued run 42173591144 should start as run 42173575775 ends. The end-of-run re-queue covers a lost successor, but not a run that GitHub cancels from outside (the 05:34 cancellation of the first pilot run is still unexplained).

## 3. High (fixed): settlements of archived markets would be missing

Kalshi's docs ("Historical data", docs.kalshi.com/getting_started/historical_data) say that markets settled before `market_settled_ts`, a cutoff that "advances forward over time", appear only in `GET /historical/markets`. They say settled markets older than the cutoff "will not appear" in `GET /markets`. `pull_after_stage3.py` already pulled trades from both endpoints, but it pulled settlements from `/markets` only. A missing result makes `taker_trades` drop the trade as "unsettled" and makes `maker_fills` drop the order. The loss would fall mostly on the oldest days, which could cut trades toward the 200 KILL line or change the mix of days.

**Fix.** For any event whose markets are missing or not settled yes/no on `/markets`, the puller now also asks `/historical/markets?event_ticker=…`, without overwriting a live result. A historical-endpoint error is logged in `settlements.json` and not filled in, and the file also lists every quoted market still without a result. The query parameters come from the published Kalshi TypeScript client (`kalshi-typescript@3.13.0`, `historical-api.ts`), because the docs page does not list them. The tests use fake HTTP only (`analysis/tests/test_pull_after_stage3.py`). The hash in `FROZEN_stage3.md` is updated with the reason; `analyze_stage3.py` is unchanged.

## 4. Medium (flagged, stage 2): the same settlement gap in `analysis/pull_after.py`

Stage 2's puller has the identical `/markets`-only settlement loop. Stage 2 pulls after 2026-11-19 15:25 UTC, and its earliest events (from 2026-11-05) are the most likely to have passed the cutoff. I did not change it: it belongs to stage 2, it is imported by stage 3 (its hash is in `FROZEN_stage3.md`), and the coordinator asked me to keep to stage 3. The same fallback should go into `pull_after.py`, or the stage 2 analyst should check `settlements.json` for markets without a result before running.

## 5. Medium: the one-shot lock is advisory

- `run` refuses only when `stage3_results.json` already exists in the given `--out`. Another `--out` folder runs the test again.
- The hashes in `FROZEN_stage3.md` are recorded in the output but not compared, so an edited script runs and simply reports a different hash.
- `analyse()` can be imported and called on real data at any time; the guards are in `main()` only.
- `stage3-data` is a public branch, so anyone (including Claude threads) can open prices during the recording.

None of this can be closed in code against a determined user. The practical guard is procedural: run the test once, in a GitHub Actions job pinned to the frozen commit, which checks the hashes and commits its output straight away. That would be a new workflow, not a change to the frozen script. Suggested for after the live window starts, if Mattias wants it.

## 6. Medium: T2 can place two orders on one row

`maker_fills` (stage 3) and `s3_fills` (stage 2) rest a YES bid whenever p > bid and a NO bid whenever 1 − p > 1 − ask. When bid < p < ask, which is the usual case, both conditions hold, so one row gets two orders. That matches "stage 2's S3 maker rule", which the pre-registration names, but not H2's wording "the side p_opt favours". Because the rule is named explicitly, I read it as the code does. The reading should go into `analysis/NOTES_stage3.md` so that it is fixed before the data exists. T2 cannot justify a next stage in any case.

## 7. Low: the 08:00 UTC close

For the 03:00 ET event (08:00 UTC), the first Deribit expiry is the one expiring at that same moment. Its options are minutes from expiry, quoted near the minimum tick, and (from memory, not checked here) Deribit settles them on a 30-minute average of its index, so their implied variance understates the spot variance to 08:00. p_opt for that hour will be noisier and too sharp. This costs power, not validity: outcomes decide T1, and the hedge's deltas are still predictable. Suggest reporting T1 without that hour as an extra figure, through `NOTES_stage3.md` (a reported split, not a gate).

## 8. Low: handover gaps

Each handover (one every 5 h 40 min) loses about one 5-minute slot and one to three minute polls while the next run starts. That is about 1 to 3% of slots, well inside the 80% day rule. A missing poll only lengthens one hedge step. If the close-minute poll is missing, the hedge stops at the minute before, which adds noise but no bias. Accepted.

## 9. Low and checked-OK

- **Point-in-time inputs.** The order per coin is chain → `index_before` → market list → `index_after`, and the recorder tests check it. p_opt is evaluated at `index_before.t1` with F = `index_before` for closes before the first expiry, so p_opt uses nothing that ended after the Kalshi request started. OK.
- **Hedge timing.** The hedge starts at (`index_after.t1`, `index_after`), then the polls whose request started after that, up to and including the close poll. Each delta uses only the current point. OK, and it matches the pre-registration.
- **Minutes to close** use `kalshi.t1` and the runner clock against Kalshi's `close_time`. The T2 order windows compare the runner clock with Kalshi's trade timestamps. GitHub runners are NTP-synced, and the windows are minutes long. OK.
- **Coverage and day rules** (288 slots, 80%, 21 days, close-day clusters, events closing 2026-12-18 00:00 dropped). OK.
- **Gates** match the table, including PASS needing both the hedged lower bound > 0 and the unhedged mean > 0. The t quantile and the cluster se match the formula. OK.
- **Pilot and live separation, the window, and `--now`.** Enforced on real data. OK.

## F. Fee schedule check

**Source:** Kalshi's fee schedule PDF, <https://kalshi.com/docs/kalshi-fee-schedule.pdf>, "Last updated and effective: July 7, 2026". I read it through a fetch tool's summary and verbatim quotes, not the raw PDF; the container cannot reach kalshi.com directly (proxy 403).

- Taker: "fees = round up(M x 0.07 x C x P x (1-P))", with "M … (default is 1 unless otherwise indicated)" and "round up = rounds up such that the fee + positionCost is rounded to a centicent".
- Maker: "fees = round up(M x 0.0175 x C x P x (1-P))", with "M … (default is 0 unless otherwise indicated)".
- The Non-Standard Fees table does **not** list KXBTCD, KXETHD, KXBTC or KXETH. The only crypto rows are KXBTCMAX150 (1/1), KXBTCY (0/0) and KXETHY (0/0). Nothing in the document mentions hourly or 15-minute markets.
- **Kalshi's API**, as the recorder logged it at both pilot run starts (05:01 and 06:18 UTC today): KXBTCD and KXETHD are `frequency: hourly`, `fee_type: quadratic`, `fee_multiplier: 1`.

**Against the pre-registration and the code:** the taker fee 0.07·q(1 − q) per contract, rounded up to $0.0001, and a zero maker fee are what the schedule gives for these two series. `fee()` in `analyze_stage3.py` implements exactly that. For a 1-contract simulated trade, "fee + positionCost rounded to a centicent" is the same as rounding the fee up to $0.0001, because the price is a whole number of centicents. **No deviation is needed.** The pre-registration asks for the check "before the first stage 3 snapshot", meaning the live one, so it should be repeated in the days before 2026-11-20. `series_meta.csv` logs the API fields on every run, as a tripwire.
