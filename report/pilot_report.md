# Stage 3 counts-only report

Generated 2026-11-06T23:18:01+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 208 (2026-11-06 05:02 to 2026-11-06 23:12 UTC), unreadable 0, modes {'pilot': 208}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 219 | 208 | 208 | 208 | 208 | 72% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.06
- Snapshot duration (start to end of the last request): 4.54 / 6.93 / 8.98 / 9.61
- BTC: Deribit chain request 0.21 / 0.27 / 0.35 / 0.36; Kalshi market list 0.10 / 0.16 / 0.26 / 1.76; |Kalshi list end - chain end| 0.26 / 0.35 / 0.44 / 1.90 (validity needs <= 5); index_before start to index_after end 0.43 / 0.52 / 0.66 / 2.00
- ETH: Deribit chain request 0.18 / 0.25 / 0.46 / 0.62; Kalshi market list 0.08 / 0.15 / 0.19 / 0.41; |Kalshi list end - chain end| 0.25 / 0.33 / 0.40 / 0.57 (validity needs <= 5); index_before start to index_after end 0.41 / 0.51 / 0.58 / 0.72
- Kalshi list pages per snapshot: {'BTC 1': 208, 'ETH 1': 208}
- Order books per snapshot: 14.00 / 29.00 / 40.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 28.93 / 31.84 / 33.58 / 33.87; total 5.8 MB

## Kalshi event schedule

Distinct events seen: 42 (36 hourly, 6 ending in 17).

**BTC.** Hourly events seen: 18. Whole hours in span: 18; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 18. Whole hours in span: 18; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 0': 12, 'BTC 1': 196, 'ETH 0': 12, 'ETH 1': 196}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 1421, ETH 1054; per snapshot 11.00 / 22.00 / 34.00 / 37.00
- By minutes to close: {'30-60': 1675, '15-30': 535, '2-15': 265}
- Spread (ask - bid, cents) on those rows: 1: 1944 (79%), 2: 295 (12%), 3: 130 (5%), 4: 51 (2%), 5: 26 (1%), 6-10: 24 (1%), >10: 5 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 20, 3: 188}
- ETH: options within 3 days per snapshot 212.00 / 214.00 / 214.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 18, 3: 190}

## 1-minute index polls

- BTC: minutes in span 1096, with a price 1049 (95.7%), missing 47; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.16 / 0.22 / 0.25 / 0.33 s; whole hours polled within 5 s: 17/18
- ETH: minutes in span 1096, with a price 1049 (95.7%), missing 47; start after the minute 0.16 / 0.22 / 0.25 / 0.33 s; request 0.16 / 0.22 / 0.30 / 4.50 s; whole hours polled within 5 s: 17/18

## Errors and runs

- Request errors by endpoint: none
- Runs started: 4; slot attempts 208; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

