# Stage 2 one-shot run: checklist

For the run after recording ends at **2026-11-19 15:25 UTC**. `run` happens once, so follow this in order and stop at the first failed check. Every step before step 6 prints counts only.

## Before

1. **Code.** Check out `main`. `sha256sum analysis/analyze_stage2.py analysis/pull_after.py` must match `analysis/FROZEN_stage2.md`. `python3 -m unittest discover -s tests` must pass (it checks the same hashes).
2. **Both data sources.** The merged series needs the local recorder's `stage2/data` folder from the Windows computer as well as the cloud data. Without the local folder only the cloud series can be computed, which deviation 4 makes reference only. Get the cloud data with `git fetch origin stage2-data && git worktree add ../stage2-data origin/stage2-data`.
3. **Wait until the last qualifying event has closed** (the Nov 18 event closes at 22:00 UTC on Nov 18; recording ends Nov 19 15:25 UTC). `run` refuses earlier anyway.

## Counts only

4. `python3 -I analysis/analyze_stage2.py coverage --local <BOB>/stage2/data --cloud ../stage2-data/data`. Note the number of qualifying events on the merged series. It needs 10. Also run `preflight` and check that every valid snapshot fitted at least one Deribit expiry.
5. `python3 -I analysis/pull_after.py --local <BOB>/stage2/data --cloud ../stage2-data/data --out results`. Then check, without opening any result: `settlements.json` lists `historical_errors` (should be empty) and the number of markets with an empty `result` (`python3 -c "import json; d=json.load(open('results/settlements.json'))['markets']; print(sum(1 for v in d.values() if not v.get('result')), 'of', len(d))"`). If any market has no result, wait a few hours and pull again before running.

## The run

6. `python3 -I analysis/analyze_stage2.py run --local <BOB>/stage2/data --cloud ../stage2-data/data --settlements results/settlements.json --trades results/trades --out results`. If it refuses because of the trade tape, nothing was written: fix the pull and run again.
7. Check the result file's `script_sha256` against `FROZEN_stage2.md`, then read the verdicts. The figures under "reference only", including the result under the coverage reading used before deviation 6, are never used to choose a verdict.
8. Commit `results/stage2_results.txt` and `.json` to the repository straight away, so the time of the run is on record.

## Notes

- Memory: `coverage` on the full cloud series used about 30 MB. `run` keeps the rows of every snapshot it reads, so give it a machine with a few GB free; the Windows computer may be short.
- Nothing here places an order or needs an account.
