# Stage 3 pilot report

Written 2026-11-16 by Claude, four days before the live window (2026-11-20 00:00 to 2026-12-18 00:00 UTC). Research only: no account, no orders, no money.

**Verdict: the recorder is ready for the live window. Nothing in the pilot requires a code or rule change.** Four items still need doing before or at the start (listed at the end); one of them is a decision only Mattias can make.

## What was looked at, and what was not

- The pilot ran 2026-11-06 05:02 to 2026-11-08 05:57 UTC on branch `stage3-pilot` (head `7083757`). Pilot data never enters the test (`stage3/NOTES.md` item 12).
- Sources: the counts-only report the workflow wrote at the pilot's end (copied verbatim to [`pilot_counts_2026-11-08.md`](pilot_counts_2026-11-08.md), sha256 `9638298a…9764`, because the pilot branch is to be deleted), plus the timestamp columns of `run_log.csv`, `cloud_loop.csv` and the `index_1m` CSVs (whether a price was present, never the price), and the GitHub Actions run list for `stage3-recorder` up to 2026-11-16 17:50 UTC.
- I re-ran `stage3/counts_report.py` on the pilot data: the output is identical to the committed report apart from its generation time. The recorder unit tests pass.
- **Not opened:** any quote, mid, index level, p_opt, gap, trade, settlement or outcome, and nothing from stage 2. `analysis/analyze_stage3.py` was not run (it refuses before 2026-12-18 and refuses pilot data anyway). The spread histogram below is the one price-derived figure, and it is computed on pilot data only, as `DESIGN.md` asks.

## Recorder health and coverage

| | Result |
|---|---|
| Snapshots | 571 over the 48 h span; 0 unreadable; 0 duplicate slots; 0 request errors; 0 non-zero exits; 0 failed pushes; empty crash and hang logs |
| Validity | Every recorded snapshot was valid for both coins (571/571). Worst Kalshi-list-to-chain gap 1.90 s against the 5 s limit (99th percentile 0.44 s BTC, 0.60 s ETH) |
| Only full day | 2026-11-07: 284 of 288 slots valid for both coins (99%), far above the 80% (231 slots) a day needs to count |
| Timing | Snapshots start 0.04 s after their slot target (max 0.06 s); duration median 3.1 s, max 9.6 s; the order-book budget never ran out (max 44 books) |
| Size | 29 to 34 KB per snapshot, 16.2 MB for the pilot: about 8 MB a day, about 230 MB for 28 days |
| Kalshi list | Always one page per coin, so the "partial list" invalidity rule never fired |
| Fee fields | KXBTCD and KXETHD stayed `hourly`, `quadratic`, multiplier 1 on every run |

**Where the missing slots were.** 17 slots were lost in total (12 on Nov 6, 4 on Nov 7, 1 on Nov 8):

- 9 slots (05:37:30 to 06:17:30 UTC on Nov 6) and 45 minutes of index polls: the first pilot run was cancelled at 05:34 by something outside the workflow, before run chaining existed (`stage3/NOTES.md` item 14). Already fixed by PR #13.
- 1 slot at each of the 8 later run handovers (the slot 2.5 minutes before the hour, or at :37:30/:17:30, depending on the handover phase), plus 1 index minute each. A run ends 5 h 40 min after it starts and its successor starts about 15 s later, so this is structural: about 4 handovers a day, so about 4 lost slots a day (1.4%). It leaves a 53-slot margin per day before the 80% rule bites, so a GitHub outage of up to about 4 hours in one day still keeps the day. Not worth a code change four days before the start.

**The run chain since the pilot.** The `wait` runs added in PR #15 have kept the chain going: the run list shows 136 runs, with the successful wait runs back to back (for example 2026-11-15 13:45 → 19:26 → 01:06 → 06:46 → 12:26 UTC), and run 134 in progress at 17:50 UTC today. The queued successors that show as "cancelled" are the expected effect of the concurrency group replacing an older queued run with a newer one. The wait run that spans 2026-11-19 19:00 UTC ends a minute after it, and its successor records in `live` mode. The `stage3-data` branch does not exist yet; the workflow creates it as an orphan branch, the same path that created `stage3-pilot` on the pilot's first run.

Stage 2's recorder stops 2026-11-19 15:25 UTC and stage 3's live lead begins 19:00 UTC, so the two recorders never run together in the live window.

## Data quality

**Hourly events (the pre-registration's "[confirm in the counts-only pilot that every hour has an event]").** Confirmed. In the 48 whole hours, every hour had an hourly KXBTCD and KXETHD event except the two 5pm ET closes (22:00 UTC), which are the daily `17` events and are excluded by design. So a day has 23 hourly events per coin. Each hourly event was always present from the first slot of its hour (57.5 minutes before the close), with exactly one hourly event open per coin at a time. BTC events had 188 markets at $100 spacing and ETH 300 at $5, unchanged across the pilot.

**Candidate rows** (valid snapshot × hourly market with a two-sided quote, mid in [0.06, 0.94], 2 to 60 minutes to close): 3,891 in the pilot (BTC 2,187, ETH 1,704), about 1,950 a day, so about 55,000 over 28 days if the pilot is typical. It covers one weekday and one Saturday only. Most rows are far from the close (30 to 60 min: 67%; 15 to 30 min: 22%; 2 to 15 min: 11%), as expected when contracts near the close drift to the extremes. Rows are not independent: each market is quoted in up to 12 snapshots.

**Deribit chains.** 188 to 196 BTC options and 200 to 214 ETH options within 3 days per snapshot. Every snapshot had at least two expiries with 4 or more two-sided out-of-the-money options with a mark IV (BTC: 3 expiries in 78% of snapshots; ETH: 85%), so p_opt has a fit in every snapshot.

**1-minute index polls (the hedge grid).** 2,885 of 2,938 minutes (98.2%) per coin; no failed requests; all 53 missing minutes are the 45 minutes of the cancelled first run plus 1 per handover. Requests take 0.17 s median (max 1.3 s BTC, 4.5 s ETH). 47 of 48 hourly closes were polled within 5 s; the one missed (06:00 on Nov 6) was inside the cancelled run's gap. The pilot's handover minutes fell at :58, :38 and :18, never on a close. In the live window the phase is set by when the first live run starts (about 19:01 UTC on Nov 19), which puts handovers near :41, :21 and :01, so the close poll should not normally be hit (a delayed or restarted run can shift the phase). If it is, the pre-registered rule applies (`analysis/NOTES_stage3.md` item 13: the last step to the close goes unhedged, which adds noise, not bias).

## The spread histogram, next to the power statement

The pre-registration ("Expected power") asks for this to be recorded next to the power statement before the start. It changes no gate.

Spread (ask − bid) on the pilot's candidate rows: **1¢ 74%**, 2¢ 12%, 3¢ 5%, 4¢ 3%, 5¢ 2%, 6 to 10¢ 3%, over 10¢ 1%.

The power statement is written at a 1¢ **half** spread (a 2¢ spread): a mispricing of about 6¢ is needed for T1 to decide reliably in 28 days, 7 to 8¢ at a 2¢ half spread. 86% of pilot rows are at a 2¢ spread or tighter, so the 1¢-half-spread figure is the relevant one and, if anything, conservative. Two cautions: T1 trades only rows where p_opt and the quote disagree by more than 1¢ after the fee, and those may sit at wider spreads than the average row; and two days is a small sample. I have not re-run the power simulation at a 0.5¢ half spread, so I make no claim about how much smaller the detectable mispricing would be.

## Before and at the start

1. **Decision for Mattias, by 2026-11-20 00:00 UTC: keep or revert stage 3 deviation 1** (PR #17: the row-sync rule flags rows instead of dropping them, because the rule as frozen biased hedged P&L up by about 1 to 2¢ at zero edge in synthetic tests). It was approved by the coordinator under delegation while Mattias was away. Recommendation: keep it. Reverting would put back a known bias as large as the 1¢ KILL margin.
2. **Acknowledge the power change Mattias has not seen** (stated at the top of `PREREGISTRATION_stage3.md`): the reliable minimum detectable mispricing is about 6¢, not the 4¢ in the draft he approved. The gates are unchanged; this only changes what a KILL means (no edge of about 6¢ or more, rather than none of 4¢ or more).
3. **Fee schedule re-check.** Checked 2026-11-16 against Kalshi's fee schedule PDF (kalshi.com/docs/kalshi-fee-schedule.pdf): still "Last updated and effective: July 7, 2026"; taker fee round up(M × 0.07 × C × P × (1 − P)) with M = 1 by default; maker M = 0 by default; KXBTCD and KXETHD are not in the non-standard tables. This matches the frozen fee rule, so no deviation. The pre-registration asks for the check "before the first stage 3 snapshot", so it should be repeated once on 2026-11-19, and a change logged as a deviation before 00:00 UTC.
4. **Check the first live hours on 2026-11-20** with `counts_report.py` on `stage3-data` (counts only; it prints no spreads on live data): snapshots from 00:02:30 UTC, both coins valid, minute polls present.

After stage 2's analysis is done, delete the `stage3-pilot` branch: it holds 5pm KXBTCD quotes recorded during stage 2. The counts report it produced is kept in this folder.
