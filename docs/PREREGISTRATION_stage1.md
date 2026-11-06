# Crypto kill test pre-registration (written 2026-11-05, before any new trade data was pulled)

This fixes the sample and kill rules for the speculative option's first kill test in Part VI of `reports/Prediction market edge research.md`:

> Extend J's tape study to all 58 Sep–Nov events, and to the ~120 Jul–Oct events. Kill if the maker CI includes 0 or the last-hour cell fails to replicate.

Read-only public GETs only. No account, no authentication, no orders.

## Why fresh events only

J's result came from 20 events: maker +1.6% [−0.4, +3.4], last hour +1.7% [+0.5, +2.8]. The last-hour cell was picked out from those 20, so re-testing on them would not be a replication. **Both kill rules are decided on events J never used.**

## Sample

- **Universe:** KXBTCD daily 5pm ET events (ticker ends `17`) in `G_quant_probe/data/markets_KXBTCD.json`: 124 events, closing 2026-07-01 to 2026-11-01.
- **Fresh set:** the 104 events not in `J_structural_downloads/trades_KXBTCD/_selected_markets.json`.
- **Markets:** lifetime `volume_fp` ≥ 200 contracts, matching J.
- **Trades:** the full public tape for each market, not a sample. Each market is pulled from both `/historical/trades` and `/markets/trades` and de-duplicated by trade ID, because the historical cutoff moves daily. Up to 400 pages per market; truncated markets are logged.
- `/series` shows `fee_type: quadratic` for KXBTCD on 2026-11-05, so makers pay no fee.

## Definitions (same as `J_structural_scripts/analyze2.py`)

- p_t = the price the taker paid for their side; p_m = 1 − p_t.
- Maker P&L per contract = −(1{taker's side wins} − p_t).
- Maker return per dollar = Σ c·P&L / Σ c·p_m over all prints, so it is dollar-weighted.
- **Last hour:** 0 < hours to close ≤ 1.
- **CI:** 95% percentile, bootstrap over events, 2,000 reps. Each daily event is one calendar day, so this is also day-clustered.

## Code check before the fresh run

The same analysis script must first reproduce J's published numbers on J's own 20 events. If it doesn't, the difference is explained before the fresh set is touched.

## Kill rules (either kills)

| # | Test | Kill if |
|---|---|---|
| C1 | Maker return, all prints, fresh events | 95% CI includes ≤ 0 |
| C2 | Maker return, last hour, fresh events | 95% CI includes ≤ 0 |

The fresh-event analysis runs once.

## Stage 2

The report's second test, the two-week synchronous snapshot against Deribit, needs two weeks of forward collection. It starts only if C1 and C2 both pass.

## Reported, never used to rescue a kill

All 124 events combined; other horizon cells; each calendar month; maker buying at ≥ 50¢; excluding 1¢ and 99¢ prints; taker net returns; share of maker P&L from the top three and top five events.

## Limits known in advance

- Every print counts as if it were yours, so these returns flatter an outside maker. Passing would not mean a maker could earn this. Failing is a stronger result than passing.
- The L test has already shown a 70–94¢ maker rule on KXBTCD and KXETHD turning negative on July–October closes. That is a different rule from C1 and C2, but those prints overlap this sample, so the fresh set is not fully unseen.

## Deviations log

(none yet)
