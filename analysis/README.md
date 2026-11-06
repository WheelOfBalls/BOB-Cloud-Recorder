# Stage 2 analysis

The one-shot analysis for the BOB crypto stage 2 test. The rules are in `../docs/PREREGISTRATION_stage2.md`, a verbatim copy of `stage2/PREREGISTRATION.md` in the BOB folder. `NOTES.md` lists every point the rules leave open and the reading taken here. Research only: the scripts read public data and simulate trades, and never place orders.

| File | What it does |
|---|---|
| `analyze_stage2.py coverage` | Slot validity, the deviation 4 merge of local and cloud snapshots, and the 80% coverage of each event. It reads no outcomes, so it is safe to run while recording continues. |
| `pull_after.py` | After recording ends, pulls settlement results and the public trade tape. It refuses to run before `stage2/end_utc.txt`. |
| `analyze_stage2.py run` | S1, S2 and S3 on the merged series, plus the reference results. It refuses to run before the end time or while a qualifying event is still open, and it refuses to overwrite an earlier result. |
| `tests/` | Unit and end-to-end tests on synthetic fixtures (`tests/make_fixture.py`). |

Stdlib only, Python 3.9 or later.

## After recording ends (2026-11-19 15:25 UTC)

```bash
git fetch origin stage2-data && git worktree add ../stage2-data origin/stage2-data
python3 -I analysis/analyze_stage2.py coverage --local <BOB>/stage2/data --cloud ../stage2-data/data
python3 -I analysis/pull_after.py --local <BOB>/stage2/data --cloud ../stage2-data/data --out results
python3 -I analysis/analyze_stage2.py run --local <BOB>/stage2/data --cloud ../stage2-data/data \
    --settlements results/settlements.json --trades results/trades --out results
```

Run `run` once. Its output (`results/stage2_results.txt` and `.json`) records the script's sha256.

## Tests

```bash
python3 -m unittest discover -s analysis/tests -v
```

The end-to-end tests build two 10-day synthetic fixtures, one with quotes centred on the true probability and one with a planted 6¢ bias, and take about two minutes.
