# Stage 3 counts-only report

Generated 2026-11-06T05:33:59+00:00. Data: `_data/data`. Counts, shares and timings only; no prices, gaps, p_opt or outcomes.

Snapshots: 7 (2026-11-06 05:02 to 2026-11-06 05:32 UTC), unreadable 0, modes {'pilot': 7}.

## Slots and validity (per UTC day)

A day counts in the live test if at least 80% of its 288 slots are valid for both coins. Partial days here are the pilot's edges.

| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | 7 | 7 | 7 | 7 | 7 | 2% | no |

Duplicate snapshots in a slot: 0.

## Timing (seconds; median / 90% / 99% / max)

- Snapshot start after its slot target: 0.05 / 0.05 / 0.05 / 0.05
- Snapshot duration (start to end of the last request): 5.87 / 6.40 / 6.93 / 6.93
- BTC: Deribit chain request 0.26 / 0.32 / 0.32 / 0.32; Kalshi market list 0.08 / 0.12 / 0.16 / 0.16; |Kalshi list end - chain end| 0.32 / 0.34 / 0.38 / 0.38 (validity needs <= 5); index_before start to index_after end 0.52 / 0.58 / 0.63 / 0.63
- ETH: Deribit chain request 0.22 / 0.27 / 0.29 / 0.29; Kalshi market list 0.08 / 0.10 / 0.16 / 0.16; |Kalshi list end - chain end| 0.30 / 0.34 / 0.40 / 0.40 (validity needs <= 5); index_before start to index_after end 0.51 / 0.58 / 0.58 / 0.58
- Kalshi list pages per snapshot: {'BTC 1': 7, 'ETH 1': 7}
- Order books per snapshot: 18.00 / 20.00 / 20.00 / 20.00; snapshots where the book budget ran out: 0
- Snapshot size (KB, gzipped): 29.35 / 29.46 / 29.56 / 29.56; total 0.2 MB

## Kalshi event schedule

Distinct events seen: 4 (2 hourly, 2 ending in 17).

**BTC.** Hourly events seen: 1. Whole hours in span: 0; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 188.00 / 188.00 / 188.00 / 188.00; strike spacings seen: [100.0].

**ETH.** Hourly events seen: 1. Whole hours in span: 0; hours with no hourly event: 0 (of which not a 5pm ET close: 0).
Minutes before close an hourly event was first listed (median / 90% / 99% / max): 57.50 / 57.50 / 57.50 / 57.50; markets per hourly event per snapshot: 300.00 / 300.00 / 300.00 / 300.00; strike spacings seen: [5.0].

Open hourly events per snapshot (coin, count: snapshots): {'BTC 1': 7, 'ETH 1': 7}

## Candidate rows (counts only)

Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.

- Rows: BTC 55, ETH 46; per snapshot 14.00 / 17.00 / 18.00 / 18.00
- By minutes to close: {'30-60': 88, '15-30': 13}
- Spread (ask - bid, cents) on those rows: 1: 79 (78%), 2: 12 (12%), 3: 2 (2%), 4: 3 (3%), 5: 1 (1%), 6-10: 3 (3%), >10: 1 (1%)

## Deribit chains

- BTC: options within 3 days per snapshot 186.00 / 186.00 / 186.00 / 186.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {3: 7}
- ETH: options within 3 days per snapshot 200.00 / 200.00 / 200.00 / 200.00; expiries with >= 4 two-sided OTM options with mark_iv (expiries: snapshots) {3: 7}

## 1-minute index polls

- BTC: minutes in span 32, with a price 32 (100.0%), missing 0; start after the minute 0.00 / 0.00 / 0.00 / 0.00 s; request 0.20 / 0.25 / 0.29 / 0.29 s; whole hours polled within 5 s: 0/0
- ETH: minutes in span 32, with a price 32 (100.0%), missing 0; start after the minute 0.20 / 0.25 / 0.29 / 0.29 s; request 0.22 / 0.26 / 0.28 / 0.28 s; whole hours polled within 5 s: 0/0

## Errors and runs

- Request errors by endpoint: none
- Runs started: 1; slot attempts 7; non-zero exit 0; failed pushes 0
- crash_log bytes: 0; hang_log bytes: 0
- Series fee fields seen (series, frequency, fee_type, fee_multiplier): [('KXBTCD', 'hourly', 'quadratic', '1'), ('KXETHD', 'hourly', 'quadratic', '1')]

