# Stage 2 result: KILL

Run once on 2026-11-24 00:04 UTC with the frozen `analyze_stage2.py` (sha256 `3e8dd8fa…dfe5`, matches `analysis/FROZEN_stage2.md`; the same hash is recorded in `results/stage2/stage2_results.json`). Pre-run checks and one known departure are in `results/stage2/PRE_RUN_NOTE.md`, committed before the run.

The test is complete: 13 settled 5pm events qualify on the merged series (Nov 6 to Nov 18; 10 needed), 51,190 rows.

| Test | Estimate | 95% CI (bootstrap over days) | Verdict |
|---|---|---|---|
| S1 mean net gap at the touch | +1.00¢ | +0.61 to +1.46¢ | PASS |
| S2 mean P&L per contract, first positive gap per strike | −6.74¢ (324 trades) | −13.59 to −0.11¢ | KILL |
| S3 outside maker, return per dollar | −1.33% (410 fills of 56,724 orders) | −10.44% to +8.54% | KILL |

## What this means under the pre-registration

- **Any kill ends the idea as written.** Two of three gates killed.
- **S3 kills**, so the pre-registered reading applies: an outside maker could not capture stage 1's return in this sample, and the idea stops.
- **S2 kills** while S1 passes: the options anchor finds gaps that look positive at the touch, but buying them lost money on real outcomes. Per deviation 5, S2 has low power at 13 events (each day acts like one bet), so this kill is not evidence that no mispricing exists. It is still a kill.
- No edge is validated. Nothing here was traded; all results are simulated on public data.

## Reference figures (never used to choose a verdict)

- S1 with the fee rounded up to a whole cent: +0.55¢ [+0.18, +1.00].
- S3 at half depth: −0.17% (1,080 fills). S3b resting on both sides regardless of p_opt: +2.81% [−1.88, +7.85] (798 fills). By hours to close: last hour −2.79%, 1 to 6 h −7.20%, over 6 h +1.26%. All CIs span zero.
- Calibration on each market's last row before T−1h (325 markets): p_opt beat the Kalshi mid slightly, Brier difference −0.0031 [−0.0084, −0.0001], log-loss difference −0.026 [−0.054, −0.010].
- KXBTC bracket gap: −0.25¢ [−0.54, +0.09].
- Cloud series alone: S1 +1.01¢, S2 −6.50¢ (CI touches zero), S3 −1.60%. Local series alone has no qualifying event (the PC was often off).
- Merged series under the coverage reading before deviation 6 (11 events): S1 PASS, S2 KILL, S3 KILL. Deviation 6 did not change any verdict.

## Data and checks

- Settlements: 2,400 markets, 0 without a result, 0 historical-endpoint errors (`results/stage2/settlements.json`, sha256 `249d7ac5…91da`). Trade tapes: 326 files with rows, 641,368 trades, all parsed, none truncated. No S3 order lacked a tape or result; no fill used a missing depth.
- Rows by source: local 17,491, cloud 33,699. 0 rows dropped for lack of a fair value.
- Known departure: local data after 2026-11-18 03:08 UTC was not available, so those slots (part of the Nov 18 event) used cloud snapshots. See the pre-run note. A rerun with full local data, if ever done, is reference only.

## Observations worth a hypothesis, not a result

These are post-hoc and must not be read as support for the idea:

- p_opt was slightly better calibrated than the mid, and S3b (both sides, no anchor) was positive with a CI spanning zero. Neither is a gate, and with 13 correlated days neither is distinguishable from noise. A new idea built on them would need its own pre-registration and fresh data.
