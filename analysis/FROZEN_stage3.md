# Stage 3 analysis: frozen files

Frozen 2026-11-06, before the live recording starts (2026-11-20 00:00 UTC), as the pre-registration's "Blinding and guard rails" asks. Written and tested on synthetic fixtures only (see `NOTES_stage3.md`). The one-shot `run` records the sha256 of `analyze_stage3.py` and of the stage 2 fitter it imports; both must match the values below.

| File | sha256 |
|---|---|
| `analysis/analyze_stage3.py` | `d42d5a914213642d7f0fd4d3a6d60413f5137ae10151de86d1663550b375d736` |
| `analysis/analyze_stage2.py` (fitter, imported) | `c0b3dca6c3b9a00364d2bc7b84ca0960bb346d8f28c32a55647d2907cc49e379` |
| `analysis/pull_after_stage3.py` | `8d223d432dde006bea12bc33da5dbcad89d664be4d076573c8d9d285870e6254` (was `13f3af0c…11bf`, see below) |
| `analysis/pull_after.py` (HTTP helper, imported) | `3c33715ad2601fa689a99e9ef5884167be31c7f96a5a8f0dd8be0085b2715f28` |
| `docs/stage3/PREREGISTRATION_stage3.md` (for reference) | `a62576a867276b45bda07398f4fa804b44f275d054dfa653510814ee69c3c515` |

The pre-registration says the analysis hash is "recorded here", meaning in the pre-registration itself. That file is frozen and was not edited, so the hashes live in this file instead. If Mattias wants them in the pre-registration too, the place is its deviations log.

If the counts-only pilot shows a format problem that needs a code change before 2026-11-20, the change is made on synthetic fixtures only, this table is updated in the same commit, and the commit message says why. After 2026-11-20 00:00 UTC these files do not change.

**Change on 2026-11-06 (code review, `docs/stage3/REVIEW_code.md` finding 3).** `pull_after_stage3.py` only asked `GET /markets` for settlements. Kalshi moves markets settled before a moving cutoff to `GET /historical/markets`, and `GET /markets` then no longer returns them, so early-window markets could come back without a result and their trades would be dropped as unsettled. The script now also asks the historical endpoint for any event whose markets are missing or unsettled. This is a data-access fix in the puller, made on synthetic tests only, before any live snapshot exists; `analyze_stage3.py` and every rule are unchanged. It is outside the "format problem from the pilot" case above, so it is logged here explicitly.
