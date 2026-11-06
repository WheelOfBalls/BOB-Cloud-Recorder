# Stage 3 counts-only report

Generated 2026-11-06T17:38:02+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 141 (2026-11-06 05:02 to 2026-11-06 17:32 UTC), unreadable 0, modes {'pilot': 141}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 151 | 141 | 141 | 141 | 141 | 49% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.05
- Snapshot duration (start to end of the last request): 4.88 / 7.57 / 9.18 / 9.61
- BTC: Deribit chain request 0.22 / 0.28 / 0.35 / 0.36; Kalshi market list 0.05 / 0.11 / 0.41 / 1.76; |Kalshi list end - chain end| 0.22 / 0.31 / 0.62 / 1.90 (validity needs <= 5); index_before start to index_after end 0.38 / 0.51 / 0.77 / 2.00
- ETH: Deribit chain request 0.18 / 0.25 / 0.40 / 0.46; Kalshi market list 0.04 / 0.10 / 0.34 / 0.41; |Kalshi list end - chain end| 0.21 / 0.29 / 0.51 / 0.57 (validity needs <= 5); index_before start to index_after end 0.36 / 0.49 / 0.67 / 0.72
- Kalshi list pages per snapshot: {'BTC 1': 141, 'ETH 1': 141}
- Order books per snapshot: 16.00 / 34.00 / 42.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.26 / 32.46 / 33.67 / 33.87; total 4.1 MB

## Kalshi event schedule

Distinct events seen: 28 (26 hourly, 2 ending in 17).

**BTC.** Hourly events seen: 13. Whole hours in span: 12; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 13. Whole hours in span: 12; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 1': 141, 'ETH 1': 141}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 1146, ETH 840; per snapshot 12.00 / 27.00 / 36.00 / 37.00
- By minutes to close: {'30-60': 1356, '15-30': 432, '2-15': 198}
- Spread (ask - bid, cents) on those rows: 1: 1569 (79%), 2: 219 (11%), 3: 108 (5%), 4: 47 (2%), 5: 23 (1%), 6-10: 15 (1%), >10: 5 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 20, 3: 121}
- ETH: options within 3 days per snapshot 212.00 / 212.00 / 212.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 18, 3: 123}

## 1-minute index polls

- BTC: minutes in span 756, with a price 710 (93.9%), missing 46; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.16 / 0.22 / 0.26 / 0.33 s; whole hours polled within 5 s: 11/12
- ETH: minutes in span 756, with a price 710 (93.9%), missing 46; start after the minute 0.16 / 0.22 / 0.26 / 0.33 s; request 0.16 / 0.23 / 0.30 / 4.50 s; whole hours polled within 5 s: 11/12

## Errors and runs

- Request errors by endpoint: none
- Runs started: 3; slot attempts 141; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

