# Stage 2 one-shot run: pre-run note

Written 2026-11-24 ~00:20 UTC, after the counts-only checks and before `analyze_stage2.py run` was executed. No result, p_opt, gap, outcome or trade had been looked at.

Checks done (RUN_CHECKLIST_stage2.md steps 1-5):

- `analyze_stage2.py` 3e8dd8fa…, `pull_after.py` cddb55ce…, `PREREGISTRATION_stage2.md` 6a920c54…: all match `FROZEN_stage2.md`. `tests/` (11) and `analysis/tests/` (65) pass.
- Coverage on the merged series: 13 events qualify (Nov 6 to Nov 18; need 10). 11 qualify under the reading before deviation 6 (Nov 11 and Nov 12 count only under deviation 6). Nov 5, Nov 19 fail by construction.
- Preflight: every valid snapshot fitted 4 to 6 Deribit expiries; 0 rows dropped for lack of a fair value; 55,882 of 56,155 candidate rows have a recorded order book.
- `pull_after.py`: 2,400 markets settled, 0 without a result, 0 historical-endpoint errors; 718 trade tapes.

**Known departure, fixed before the run.** The local recorder's data available here ends at 2026-11-18 03:08 UTC (the copy synced that day, 1,222 snapshots). The Windows computer could not be reached for a later copy. So for slots from 2026-11-18 03:08 UTC to the end, the merged series uses cloud snapshots where deviation 4 would have used a valid local one. Both recorders run the same code against the same public endpoints, and the cloud series covers the Nov 18 event 360/360, so qualification is unaffected; only which of two near-identical snapshots enters a slot can differ, for part of one of 13 events.

**Decided now, before the result is seen:** this run is the stage 2 result. If the full local data is later recovered, a rerun on it is reported for reference only and is never used to change a verdict.
