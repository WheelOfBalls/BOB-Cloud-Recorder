# Stage 3 recorder

Records what `docs/stage3/PREREGISTRATION_stage3.md` ("Recording") asks for. Separate from stage 2: its own workflow (`stage3-recorder`), concurrency group and data branches. Stage 2's recorder, code and `stage2-data` branch are not touched. Research only: public read-only Kalshi and Deribit endpoints, no account, no keys, no orders. Readings of the pre-registration that the code had to choose are in [`NOTES.md`](NOTES.md).

| File | What it does |
|---|---|
| `record_snapshot.py` | One snapshot: per coin (BTC, then ETH) the Deribit option chain (expiries within 3 days), `index_before`, every open KXBTCD/KXETHD market (all pages), `index_after`; then order books for hourly markets quoted inside 3 to 97¢; then the KXBTC/KXETH bracket lists (reference only). Every request keeps its `t0`/`t1`. |
| `cloud_loop.py` | Runs a snapshot at every 5-minute slot (phase `hh:m2:30` UTC, so slots sit 57.5 … 2.5 minutes before each hourly close) and polls both Deribit indices on every whole minute in its own thread (`data/index_1m/YYYY-MM-DD.csv`, the hedge grid). Pushes after each snapshot. `--which` prints the mode. |
| `counts_report.py` | Counts-only report: slots and validity per day, timing, the hourly event schedule, candidate-row counts, Deribit fit counts, minute-poll coverage, errors, series fee fields. The spread histogram is printed only on pilot or test data, never on live data. |
| `start_utc.txt`, `end_utc.txt` | The live window: 2026-11-20 00:00 to 2026-12-18 00:00 UTC (28 full UTC days), as pre-registered. |
| `pilot_until_utc.txt` | End of the counts-only pilot (2026-11-08 06:00 UTC). |
| `tests/` | Unit tests on synthetic responses. |

## Modes

The workflow fires at `:06`, `:26`, `:46` and asks `cloud_loop.py --which` what to do:

- **pilot** (now before `pilot_until_utc.txt`): records to the `stage3-pilot` branch. At the end of every run the workflow writes `report/pilot_report.md` (and `.json`) on that branch and in the run's summary. **Pilot data is thrown away: it never enters the test.** It also holds the 5pm KXBTCD quotes recorded during stage 2, so nobody should open it beyond the counts report.
- **live** (from 30 minutes before `start_utc.txt` to `end_utc.txt`): records to `stage3-data`. Slots before the start are skipped, so the first snapshot is at 2026-11-20 00:02:30 UTC.
- **off** (otherwise): the run exits after a few seconds.

During the live window only `counts_report.py` may be run on `stage3-data` (no spreads are printed there). Settlements and trades are pulled after the end, never during.

## Data layout (both branches)

```
data/YYYY-MM-DD/HHMMSS.json.gz   one snapshot (stage 3, version 1; "mode" is pilot or live)
data/index_1m/YYYY-MM-DD.csv     target_utc,coin,t0,t1,index_price,us_out,error  (one row per coin per minute)
data/run_log.csv                 one line per snapshot: counts, per-coin sync gap and validity, duration, size, errors
data/cloud_loop.csv              run starts and ends, and for every slot its target, lateness, duration, exit code, push
data/series_meta.csv             KXBTCD/KXETHD frequency and fee fields, once per run
```

## Checks

- `stage3-check.yml` runs on pull requests that touch `stage3/`: the unit tests, then one real snapshot and two minutes of index polls on a GitHub runner (`cloud_loop.py --mode test`, nothing pushed), summarised as counts only.
- Local: `python3 -m unittest discover -s stage3/tests -v`.
- Report on a branch: `git fetch origin stage3-pilot && git worktree add ../s3p origin/stage3-pilot && python3 -I stage3/counts_report.py --data ../s3p/data`.

## Load and limits

- About 30 to 40 requests per snapshot (two chains, four index reads, two to four list pages, the books, two bracket lists) plus two index reads a minute.
- GitHub-hosted minutes are free on a public repo. During the pilot both recorders run at once (two of the 20 concurrent jobs a free account gets); from 2026-11-20 only stage 3 runs, since stage 2 ends 2026-11-19 15:25 UTC. Each job is capped at 355 minutes, under GitHub's 6-hour limit.
- Expected size about 50 to 80 KB per snapshot gzipped, so 15 to 25 MB a day and well under 1 GB for 28 days. The workflow fetches the data branch with `--depth=20`, so checkout time doesn't grow with it.
