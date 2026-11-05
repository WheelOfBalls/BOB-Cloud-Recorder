# BOB stage 2 cloud recorder

A second copy of the BOB crypto stage 2 recorder that runs in GitHub Actions, so snapshots keep coming when the Windows computer is asleep, offline or out of memory. The Windows task keeps running too. Research only: public read-only Kalshi and Deribit endpoints, no account, no keys, no orders.

## How it runs

- `.github/workflows/stage2-recorder.yml` fires every 20 minutes (`:11`, `:31`, `:51`). Only one run records at a time; one more waits in the queue.
- Each run calls `stage2/cloud_loop.py`, which takes one snapshot per 5-minute slot at the Windows task's phase (`hh:m3:02` UTC) for about 5 h 40 min, then exits. The queued run takes over within a minute or so.
- Every snapshot is committed and pushed to the `stage2-data` branch under `data/YYYY-MM-DD/HHMMSS.json.gz`, the same layout as the local `data/` folder.
- Recording stops at `stage2/end_utc.txt` (2026-11-19 15:25 UTC). After that, runs exit at once. Disable the workflow in the Actions tab when done.

## Timing is recorded, not assumed

GitHub's scheduled runs can start late or be skipped. Nothing is filled in afterwards:

- each snapshot holds its real start time (`utc`) and per-request `t0`/`t1`, as before, plus a `source` block (`host`, `run_id`, `event`, `slot_target`);
- `data/cloud_loop.csv` logs every run start and end and, for every slot, the target time, how late the run started (s), how long it took (s), the exit code and whether the push worked.

## Differences from the Windows recorder

`stage2/record_snapshot.py` is the Windows script with two changes: `BOB_DATA_DIR` can move the data folder, and each snapshot gets the `source` block above. What is fetched and how is unchanged.

## Check coverage

```bash
git fetch origin stage2-data
git worktree add ../stage2-data origin/stage2-data
cp -r ../stage2-data/data stage2/data
python3 -I stage2/status.py
```

## Checks

- `stage2-check.yml` runs on every pull request (or by hand): it takes one real snapshot on a GitHub runner, pushes nothing, and fails if Kalshi or Deribit did not answer.
- After merging, Actions tab → stage2-recorder → Run workflow with `max_minutes` = 12 starts recording at once instead of waiting for the cron. Then check `stage2-data` for snapshots with an empty `errors` list.

## Minutes

Recording nonstop for 14 days uses about 20,000 runner minutes. That is free only while the repo is public. A private repo gets 2,000 free minutes a month.
