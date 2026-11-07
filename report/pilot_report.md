# Stage 3 counts-only report

Generated 2026-11-07T10:38:03+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 342 (2026-11-06 05:02 to 2026-11-07 10:32 UTC), unreadable 0, modes {'pilot': 342}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 228 | 216 | 216 | 216 | 216 | 75% | no |
| 2026-11-07 | 127 | 126 | 126 | 126 | 126 | 44% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.06
- Snapshot duration (start to end of the last request): 3.49 / 6.25 / 8.72 / 9.61
- BTC: Deribit chain request 0.20 / 0.27 / 0.34 / 0.36; Kalshi market list 0.10 / 0.16 / 0.25 / 1.76; |Kalshi list end - chain end| 0.27 / 0.36 / 0.43 / 1.90 (validity needs <= 5); index_before start to index_after end 0.43 / 0.53 / 0.63 / 2.00
- ETH: Deribit chain request 0.18 / 0.24 / 0.40 / 0.62; Kalshi market list 0.09 / 0.15 / 0.20 / 0.41; |Kalshi list end - chain end| 0.25 / 0.33 / 0.40 / 0.57 (validity needs <= 5); index_before start to index_after end 0.41 / 0.51 / 0.58 / 0.72
- Kalshi list pages per snapshot: {'BTC 1': 342, 'ETH 1': 342}
- Order books per snapshot: 9.00 / 23.00 / 40.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.35 / 31.04 / 33.55 / 33.87; total 9.7 MB

## Kalshi event schedule

Distinct events seen: 64 (58 hourly, 6 ending in 17).

**BTC.** Hourly events seen: 29. Whole hours in span: 29; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 29. Whole hours in span: 29; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 0': 12, 'BTC 1': 330, 'ETH 0': 12, 'ETH 1': 330}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 1727, ETH 1322; per snapshot 7.00 / 19.00 / 32.00 / 37.00
- By minutes to close: {'30-60': 2058, '15-30': 671, '2-15': 320}
- Spread (ask - bid, cents) on those rows: 1: 2331 (76%), 2: 380 (12%), 3: 167 (5%), 4: 73 (2%), 5: 39 (1%), 6-10: 51 (2%), >10: 8 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 90, 3: 252}
- ETH: options within 3 days per snapshot 214.00 / 214.00 / 214.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 56, 3: 286}

## 1-minute index polls

- BTC: minutes in span 1776, with a price 1727 (97.2%), missing 49; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.16 / 0.21 / 0.25 / 0.33 s; whole hours polled within 5 s: 28/29
- ETH: minutes in span 1776, with a price 1727 (97.2%), missing 49; start after the minute 0.16 / 0.21 / 0.25 / 0.33 s; request 0.16 / 0.22 / 0.29 / 4.50 s; whole hours polled within 5 s: 28/29

## Errors and runs

- Request errors by endpoint: none
- Runs started: 6; slot attempts 342; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

