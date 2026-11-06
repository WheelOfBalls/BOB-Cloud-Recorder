# Stage 3 (designed and pre-registered; nothing is running yet)

- [`DESIGN.md`](DESIGN.md): why stage 2 can't decide, what stage 3 changes, the power results, costs and recorder changes. Read this first.
- [`PREREGISTRATION_stage3.md`](PREREGISTRATION_stage3.md): **Approved 2026-11-06 and frozen** (sha256 in `DESIGN.md`). Changes only through its deviations log.
- [`REVIEW.md`](REVIEW.md): red-team review of the design, corrected power estimate, and the edits it made to the draft.
- `power_sim_redteam.py` / `power_results_redteam.json`: the review's synthetic simulation (timing, intraday vol, basis, averaged settlement, tapered mispricing). `--quick` is a CI check.
- `power_sim.py`: synthetic-only power simulation (`--quick` is the CI smoke test). Needs numpy. Full run about 15 minutes on 4 cores.
- `power_results.json`: output of the full run behind the tables in `DESIGN.md`.
- `discover_series.py`: metadata-only listing of Kalshi crypto series and Deribit expiries (no prices or outcomes). Runs in CI as `stage3-design / discover-series`.
- [`approval_diff_vs_approved_draft.diff`](approval_diff_vs_approved_draft.diff): every change to the pre-registration between the draft Mattias approved at 03:51 UTC (commit 65a6a71) and the frozen file.
