# Stage 3 counts-only report

Generated 2026-11-08T03:38:04+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 543 (2026-11-06 05:02 to 2026-11-08 03:32 UTC), unreadable 0, modes {'pilot': 543}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 228 | 216 | 216 | 216 | 216 | 75% | no |
| 2026-11-07 | 288 | 284 | 284 | 284 | 284 | 99% | yes |
| 2026-11-08 | 43 | 43 | 43 | 43 | 43 | 15% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.06
- Snapshot duration (start to end of the last request): 3.14 / 5.80 / 8.66 / 9.61
- BTC: Deribit chain request 0.22 / 0.28 / 0.35 / 1.63; Kalshi market list 0.10 / 0.16 / 0.26 / 1.76; |Kalshi list end - chain end| 0.28 / 0.36 / 0.45 / 1.90 (validity needs <= 5); index_before start to index_after end 0.45 / 0.55 / 0.67 / 2.00
- ETH: Deribit chain request 0.20 / 0.26 / 0.40 / 0.62; Kalshi market list 0.08 / 0.15 / 0.38 / 0.52; |Kalshi list end - chain end| 0.26 / 0.34 / 0.60 / 0.73 (validity needs <= 5); index_before start to index_after end 0.43 / 0.53 / 0.79 / 0.97
- Kalshi list pages per snapshot: {'BTC 1': 543, 'ETH 1': 543}
- Order books per snapshot: 7.00 / 19.00 / 38.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.50 / 30.52 / 33.07 / 33.87; total 15.4 MB

## Kalshi event schedule

Distinct events seen: 98 (90 hourly, 8 ending in 17).

**BTC.** Hourly events seen: 45. Whole hours in span: 46; hours with no hourly event: 2 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 45. Whole hours in span: 46; hours with no hourly event: 2 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 0': 23, 'BTC 1': 520, 'ETH 0': 23, 'ETH 1': 520}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 2139, ETH 1668; per snapshot 5.00 / 15.00 / 30.00 / 37.00
- By minutes to close: {'30-60': 2570, '15-30': 840, '2-15': 397}
- Spread (ask - bid, cents) on those rows: 1: 2824 (74%), 2: 459 (12%), 3: 208 (5%), 4: 117 (3%), 5: 65 (2%), 6-10: 105 (3%), >10: 29 (1%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 96, 3: 447}
- ETH: options within 3 days per snapshot 212.00 / 214.00 / 214.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 56, 3: 487}

## 1-minute index polls

- BTC: minutes in span 2796, with a price 2744 (98.1%), missing 52; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.17 / 0.22 / 0.28 / 1.27 s; whole hours polled within 5 s: 45/46
- ETH: minutes in span 2796, with a price 2744 (98.1%), missing 52; start after the minute 0.17 / 0.22 / 0.28 / 1.27 s; request 0.17 / 0.23 / 0.29 / 4.50 s; whole hours polled within 5 s: 45/46

## Errors and runs

- Request errors by endpoint: none
- Runs started: 9; slot attempts 543; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

