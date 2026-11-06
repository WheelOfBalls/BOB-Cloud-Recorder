# Stage 3 (pre-registered; counts-only pilot recording, live recording from 2026-11-20)

- [`DESIGN.md`](DESIGN.md): why stage 2 can't decide, what stage 3 changes, the power results, costs and recorder changes. Read this first.
- [`PREREGISTRATION_stage3.md`](PREREGISTRATION_stage3.md): **Approved 2026-11-06 and frozen** (sha256 in `DESIGN.md`). Changes only through its deviations log.
- [`REVIEW.md`](REVIEW.md): red-team review of the design, corrected power estimate, and the edits it made to the draft.
- `power_sim_redteam.py` / `power_results_redteam.json`: the review's synthetic simulation (timing, intraday vol, basis, averaged settlement, tapered mispricing). `--quick` is a CI check.
- `power_sim.py`: synthetic-only power simulation (`--quick` is the CI smoke test). Needs numpy. Full run about 15 minutes on 4 cores.
- `power_results.json`: output of the full run behind the tables in `DESIGN.md`.
- `discover_series.py`: metadata-only listing of Kalshi crypto series and Deribit expiries (no prices or outcomes). Runs in CI as `stage3-design / discover-series`.
- [`approval_diff_vs_approved_draft.diff`](approval_diff_vs_approved_draft.diff): every change to the pre-registration between the draft Mattias approved at 03:51 UTC (commit 65a6a71) and the frozen file.
- Recorder: [`../../stage3/`](../../stage3/README.md) (workflow `stage3-recorder`, branches `stage3-pilot` and `stage3-data`); its readings of this pre-registration are in `stage3/NOTES.md`.
- Analysis: `../../analysis/analyze_stage3.py`, readings in `analysis/NOTES_stage3.md`, frozen hashes in `analysis/FROZEN_stage3.md`.
