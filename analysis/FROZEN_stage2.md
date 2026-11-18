# Stage 2 analysis: frozen files

The stage 2 one-shot `run` records the sha256 of `analyze_stage2.py` in its result file. It must match the value below. `tests/test_frozen.py` checks this table on every pull request.

| File | sha256 |
|---|---|
| `analysis/analyze_stage2.py` | `3e8dd8fa701105a04a435f9e7a8d4a62eb96719b72f7767fe9b4ce74701dbfe5` (2026-11-18: deviation 6 and the trade-tape guard; was `c0b3dca6…e379`, frozen 2026-11-06 in `REVIEW.md`) |
| `analysis/pull_after.py` | `cddb55ce07059730c9b96c86702c7db3b058824552338175a4472868c381d29e` (2026-11-06, PR #16: historical settlement fallback; was `3c33715a…5f28`) |
| `docs/PREREGISTRATION_stage2.md` | `6a920c54b573409fdf0a91233b036f736520dc7a8d023b4d82a2468e5a040f82` (deviation 6 logged; `2f81bc69…5944` with deviations 1 to 5) |

The copy of `PREREGISTRATION.md` on the Windows computer is the original. After deviation 6 it must be replaced by this repository's `docs/PREREGISTRATION_stage2.md`, so the two hash the same.

After 2026-11-19 15:25 UTC these files do not change.
