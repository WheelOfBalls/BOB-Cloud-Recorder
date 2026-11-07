# Stage 3 counts-only report

Generated 2026-11-07T04:58:02+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 275 (2026-11-06 05:02 to 2026-11-07 04:52 UTC), unreadable 0, modes {'pilot': 275}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 228 | 216 | 216 | 216 | 216 | 75% | no |
| 2026-11-07 | 59 | 59 | 59 | 59 | 59 | 20% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.06
- Snapshot duration (start to end of the last request): 3.96 / 6.65 / 8.72 / 9.61
- BTC: Deribit chain request 0.21 / 0.27 / 0.34 / 0.36; Kalshi market list 0.11 / 0.17 / 0.25 / 1.76; |Kalshi list end - chain end| 0.29 / 0.36 / 0.43 / 1.90 (validity needs <= 5); index_before start to index_after end 0.45 / 0.54 / 0.63 / 2.00
- ETH: Deribit chain request 0.19 / 0.25 / 0.40 / 0.62; Kalshi market list 0.10 / 0.16 / 0.20 / 0.41; |Kalshi list end - chain end| 0.27 / 0.34 / 0.40 / 0.57 (validity needs <= 5); index_before start to index_after end 0.44 / 0.51 / 0.58 / 0.72
- Kalshi list pages per snapshot: {'BTC 1': 275, 'ETH 1': 275}
- Order books per snapshot: 11.00 / 25.00 / 40.00 / 44.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.26 / 31.37 / 33.55 / 33.87; total 7.8 MB

## Kalshi event schedule

Distinct events seen: 52 (46 hourly, 6 ending in 17).

**BTC.** Hourly events seen: 23. Whole hours in span: 23; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 23. Whole hours in span: 23; hours with no hourly event: 1 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 0': 12, 'BTC 1': 263, 'ETH 0': 12, 'ETH 1': 263}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 1588, ETH 1203; per snapshot 9.00 / 21.00 / 32.00 / 37.00
- By minutes to close: {'30-60': 1876, '15-30': 615, '2-15': 300}
- Spread (ask - bid, cents) on those rows: 1: 2161 (77%), 2: 348 (12%), 3: 153 (5%), 4: 63 (2%), 5: 29 (1%), 6-10: 31 (1%), >10: 6 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 54, 3: 221}
- ETH: options within 3 days per snapshot 212.00 / 214.00 / 214.00 / 214.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 21, 3: 254}

## 1-minute index polls

- BTC: minutes in span 1436, with a price 1388 (96.7%), missing 48; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.16 / 0.21 / 0.25 / 0.33 s; whole hours polled within 5 s: 22/23
- ETH: minutes in span 1436, with a price 1388 (96.7%), missing 48; start after the minute 0.16 / 0.21 / 0.25 / 0.33 s; request 0.17 / 0.22 / 0.29 / 4.50 s; whole hours polled within 5 s: 22/23

## Errors and runs

- Request errors by endpoint: none
- Runs started: 5; slot attempts 275; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

