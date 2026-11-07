# Stage 3 counts-only report

Generated 2026-11-07T16:18:03+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 409 (2026-11-06 05:02 to 2026-11-07 16:12 UTC), unreadable 0, modes {'pilot': 409}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 228 | 216 | 216 | 216 | 216 | 75% | no |
| 2026-11-07 | 195 | 193 | 193 | 193 | 193 | 67% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.06
- Snapshot duration (start to end of the last request): 3.33 / 6.12 / 8.70 / 9.61
- BTC: Deribit chain request 0.21 / 0.29 / 0.34 / 0.54; Kalshi market list 0.10 / 0.16 / 0.25 / 1.76; |Kalshi list end - chain end| 0.28 / 0.36 / 0.44 / 1.90 (validity needs <= 5); index_before start to index_after end 0.45 / 0.56 / 0.67 / 2.00
- ETH: Deribit chain request 0.19 / 0.25 / 0.31 / 0.62; Kalshi market list 0.09 / 0.15 / 0.39 / 0.52; |Kalshi list end - chain end| 0.26 / 0.34 / 0.61 / 0.73 (validity needs <= 5); index_before start to index_after end 0.43 / 0.53 / 0.79 / 0.97
- Kalshi list pages per snapshot: {'BTC 1': 409, 'ETH 1': 409}
- Order books per snapshot: 8.00 / 21.00 / 40.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.42 / 30.74 / 33.43 / 33.87; total 11.6 MB

## Kalshi event schedule

Distinct events seen: 76 (70 hourly, 6 ending in 17).

**BTC.** Hourly events seen: 35. Whole hours in span: 35; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 35. Whole hours in span: 35; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 0': 12, 'BTC 1': 397, 'ETH 0': 12, 'ETH 1': 397}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 1867, ETH 1441; per snapshot 6.00 / 17.00 / 30.00 / 37.00
- By minutes to close: {'30-60': 2230, '15-30': 726, '2-15': 352}
- Spread (ask - bid, cents) on those rows: 1: 2492 (75%), 2: 405 (12%), 3: 185 (6%), 4: 89 (3%), 5: 51 (2%), 6-10: 70 (2%), >10: 16 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 90, 3: 319}
- ETH: options within 3 days per snapshot 212.00 / 214.00 / 214.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 56, 3: 353}

## 1-minute index polls

- BTC: minutes in span 2116, with a price 2066 (97.6%), missing 50; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.16 / 0.23 / 0.28 / 0.56 s; whole hours polled within 5 s: 34/35
- ETH: minutes in span 2116, with a price 2066 (97.6%), missing 50; start after the minute 0.16 / 0.23 / 0.28 / 0.56 s; request 0.17 / 0.23 / 0.29 / 4.50 s; whole hours polled within 5 s: 34/35

## Errors and runs

- Request errors by endpoint: none
- Runs started: 7; slot attempts 409; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

