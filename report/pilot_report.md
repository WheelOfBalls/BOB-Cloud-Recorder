# Stage 3 counts-only report

Generated 2026-11-06T11:58:01+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 74 (2026-11-06 05:02 to 2026-11-06 11:52 UTC), unreadable 0, modes {'pilot': 74}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 83 | 74 | 74 | 74 | 74 | 26% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.05
- Snapshot duration (start to end of the last request): 4.54 / 6.15 / 6.93 / 6.95
- BTC: Deribit chain request 0.25 / 0.32 / 0.35 / 0.36; Kalshi market list 0.05 / 0.12 / 0.25 / 0.41; |Kalshi list end - chain end| 0.26 / 0.34 / 0.44 / 0.62 (validity needs <= 5); index_before start to index_after end 0.44 / 0.53 / 0.66 / 0.77
- ETH: Deribit chain request 0.21 / 0.28 / 0.40 / 0.46; Kalshi market list 0.05 / 0.11 / 0.34 / 0.41; |Kalshi list end - chain end| 0.25 / 0.33 / 0.51 / 0.57 (validity needs <= 5); index_before start to index_after end 0.43 / 0.51 / 0.67 / 0.72
- Kalshi list pages per snapshot: {'BTC 1': 74, 'ETH 1': 74}
- Order books per snapshot: 14.00 / 20.00 / 22.00 / 22.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 28.74 / 29.56 / 29.97 / 30.10; total 2.1 MB

## Kalshi event schedule

Distinct events seen: 16 (14 hourly, 2 ending in 17).

**BTC.** Hourly events seen: 7. Whole hours in span: 6; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 7. Whole hours in span: 6; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 1': 74, 'ETH 1': 74}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 432, ETH 337; per snapshot 11.00 / 16.00 / 18.00 / 19.00
- By minutes to close: {'30-60': 516, '15-30': 178, '2-15': 75}
- Spread (ask - bid, cents) on those rows: 1: 626 (81%), 2: 83 (11%), 3: 29 (4%), 4: 14 (2%), 5: 3 (0%), 6-10: 11 (1%), >10: 3 (0%)

## Deribit chains

- BTC: options within 3 days per snapshot 196.00 / 196.00 / 196.00 / 196.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 20, 3: 54}
- ETH: options within 3 days per snapshot 212.00 / 212.00 / 212.00 / 212.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {2: 18, 3: 56}

## 1-minute index polls

- BTC: minutes in span 416, with a price 371 (89.2%), missing 45; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.19 / 0.23 / 0.25 / 0.29 s; whole hours polled within 5 s: 5/6
- ETH: minutes in span 416, with a price 371 (89.2%), missing 45; start after the minute 0.19 / 0.23 / 0.25 / 0.29 s; request 0.19 / 0.23 / 0.26 / 0.47 s; whole hours polled within 5 s: 5/6

## Errors and runs

- Request errors by endpoint: none
- Runs started: 2; slot attempts 74; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

