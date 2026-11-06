# Stage 3 (design only, nothing is running)

- [`DESIGN.md`](DESIGN.md): why stage 2 can't decide, what stage 3 changes, the power results, costs and recorder changes. Read this first.
- [`PREREGISTRATION_stage3_DRAFT.md`](PREREGISTRATION_stage3_DRAFT.md): **DRAFT, not approved.** Mattias must approve it before any stage 3 recording or analysis.
- `power_sim.py`: synthetic-only power simulation (`--quick` is the CI smoke test). Needs numpy. Full run about 15 minutes on 4 cores.
- `power_results.json`: output of the full run behind the tables in `DESIGN.md`.
- `discover_series.py`: metadata-only listing of Kalshi crypto series and Deribit expiries (no prices or outcomes). Runs in CI as `stage3-design / discover-series`.
