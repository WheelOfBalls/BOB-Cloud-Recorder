# BOB review, 2026-11-17

Written by Claude on 2026-11-16 and 17 at Mattias's request, before anything more is built. Reviewed at `main` = `3acb8c35` (PR #17). **This pull request adds this file and changes nothing else.**

Two dates drive the urgency of what follows:

- **2026-11-19 15:25 UTC** (10:25 Toronto): stage 2 recording ends and its locked analysis may run.
- **2026-11-20 00:00 UTC** (Nov 19, 19:00 Toronto): stage 3 goes live. After that, any change to the stage 3 analysis is a change made with data in hand.

## How to read this

Every claim carries one of three tags.

- **[ran]** I confirmed it by running code: the test suites, the counts-only modes on the recorded data, or a small synthetic call.
- **[read]** I confirmed it by reading the code or document, but did not execute that path.
- **[inferred]** I did not confirm it. Treat it as a hypothesis.

### What I checked

- Read in full: every workflow, both recorders (`stage2/`, `stage3/`), `analysis/analyze_stage2.py`, `analysis/analyze_stage3.py`, both pull scripts, `stage2/status.py`, all three pre-registrations, `RESULTS_stage1.md`, every NOTES, README, REVIEW and FROZEN file, `DESIGN.md` and the approval diff.
- Ran all three test suites on Python 3.13: `tests` 8 pass, `stage3/tests` 16 pass, `analysis/tests` 58 pass (254 s). 82 tests, no failures. **[ran]**
- Ran `analyze_stage2.py coverage` on the `stage2-data` branch as of 03:41 UTC Nov 17, and read the recorder's own logs (`cloud_loop.csv`, `run_log.csv`). Read the stage 3 pilot report on `stage3-pilot` and measured the stage 3 loader on the 571 pilot snapshots. **[ran]**
- Checked the merge history of PRs #1 to #17 and the Actions run history around the Nov 11 gap. **[ran]**

### What I did not check

- **The local BOB folder on the Windows PC.** Access to `D:\Coding\Projects\BOB` was refused twice. So I have not seen the stage 1 code, the local recorder's data, the authoritative local `PREREGISTRATION.md`, or any `OVERNIGHT_NOTES.md` that might live there.
- **`overnight/claude` and `OVERNIGHT_NOTES.md` do not exist in this repository**, on any branch. **[ran]** The record of the overnight work here is the PR descriptions, `analysis/NOTES.md`, `analysis/NOTES_stage3.md`, `stage3/NOTES.md` and the three review files. That is what section 3 is based on.
- Not read line by line: `stage3/counts_report.py`, the test files and fixtures (I read the test names and `test_verdict_rules`), the power simulations, `discover_series.py`, the helper scripts under `analysis/review/` and `docs/stage3/review_code/`, and the JSON result files.
- PR #18 (stage 3 pilot report, another thread) is not reviewed.
- **No locked analysis was run on real data and no price, gap, fair value, outcome or trade was looked at.** Everything from real data in this review is a count of slots, files or fields. The consequence is that the numerical core (the volatility fit, the P&L, the fill rule) is checked only on synthetic fixtures and by reading.
- Kalshi's trade endpoint field names are not verified against Kalshi's documentation.

---

## 1. What BOB does, and how well that matches its purpose

**What it is meant to do [inferred from the pre-registrations].** Test, with rules fixed in advance, whether Kalshi's Bitcoin (and for stage 3, Ether) price contracts are mispriced against a fair value taken from Deribit options, by enough to cover fees and spread. Research only. No account, no orders, no money.

**What it does today [read, ran].**

- **Stage 1** is a finished historical study. Only its pre-registration and results are in this repo. Its code is not, so the result cannot be reproduced from here.
- **Stage 2** takes a snapshot every 5 minutes of Kalshi's daily 5pm ET Bitcoin markets and the Deribit option chain, from GitHub Actions and, in parallel, from a Windows scheduled task. After Nov 19 a locked script computes three tests (S1 fair value against settlement, S2 simulated taker trades, S3 simulated maker fills).
- **Stage 3** does the same for the hourly Bitcoin and Ether contracts, plus a one-minute price poll for a simulated delta hedge. It ran a 48 hour pilot, is now idling in a `wait` mode, and starts recording for real on Nov 20 for 28 days. Its analysis script is written and frozen.
- `status.py` and the `coverage` / `preflight` modes report counts without revealing results.

**How well it matches.**

- The name and the root `README.md` say "stage 2 cloud recorder". The repo is in fact the whole research project: three pre-registrations, two recorders, two analyses. Someone arriving cold would not find stage 3 from the README. **[read]**
- The research discipline is the strongest part and is real: rules written before data, deviations logged with timestamps, scripts hashed, guards in code that refuse to run early or twice. **[read]**
- The recorders work. The stage 2 cloud recorder captured 3130 of 3150 expected slots (99.4%), every one on time to the second, with a median snapshot time of 10.6 s. The stage 3 pilot captured 571 snapshots, all valid for both coins. **[ran]**
- The weak point is the gap between "the recorder is healthy" and "the test will be able to return a verdict". The coverage rule as coded is far stricter than the notes say (finding 1), and the stage 3 analysis as frozen will probably not fit in memory (finding 2). Both would surface only on the day, when changing anything is most expensive.
- **BOB has produced no stage 2 or stage 3 result yet.** Nothing in this repo is evidence of an edge. Stage 1 passing is a claim I could not check.

---

## 2. Findings, ranked

### Severity A: can cost you a verdict, and has a deadline this week

#### 1. The stage 2 coverage rule tolerates one hour of lost data per event, not six

- **Where:** `analysis/analyze_stage2.py:289-296`, `stage2/status.py:22` and `:202`, `README.md:33`, `analysis/NOTES.md` item 25, `docs/PREREGISTRATION_stage2.md` deviation 3.
- **What happens [ran]:** a slot counts toward an event only if the snapshot is valid *and that event is listed in it* (item 25). Deviation 3 fixes the denominator at 360 slots (30 hours). But Kalshi lists a normal 5pm event at 21:03 UTC the day before, 24.9 hours before close. So a normal event can score at most 300 of 360, and it needs 288. The real allowance is 12 slots, one hour. Only the Friday events, which are listed a week ahead, get the full 72.
- `status.py` line 22 and the README both say a gap must exceed 6 hours to fail an event. That is wrong for every event except Fridays.
- **It has already cost two events.** One gap of 20 slots on Nov 11 (20:43 to 22:18 UTC) put both the Nov 11 and the Nov 12 events at 284, four short. In those two windows the recorder had 344 and 340 valid snapshots.
- **Cloud-only scoreboard at 03:41 UTC Nov 17:** 9 events qualify (Nov 6, 7, 8, 9, 10, 13, 14, 15, 16). Nov 10 qualified by 3 slots. Nov 17 and Nov 18 are still open. The test needs 10. So on cloud data alone, one more outage of over an hour in each of the next two windows makes stage 2 INCOMPLETE.
- **What I can't see:** the local recorder. Under deviation 4 its snapshots are merged in, so if the PC was recording between 20:43 and 22:18 UTC on Nov 11, both failed events may already be rescued.
- **Also [read, not run]:** `status.py`'s "can still reach 80%" figure counts every future slot as reachable, including the ones before the event is listed, so it overstates what open events can still score.
- **Why it matters:** two weeks of recording could end as INCOMPLETE because of a reading (item 25) that was never marked material and whose interaction with deviation 3 nobody wrote down. In effect the rule is "96% of the slots that can exist", not 80%.
- **Fix I would make:** this is your decision, not a code fix, and it must be made before Nov 19 15:25 UTC. Either (a) accept the rule as coded and correct the 6 hour claim in the docs, or (b) log a deviation 6 that says what "possible snapshots" means when the event is not yet listed. The two natural wordings are "slots in which the event was listed" (denominator about 300) or "a valid snapshot counts whether or not the event is listed yet" (denominator 360). **Be aware that option (b) is now being chosen with the coverage counts known.** Coverage counts are not outcomes, so this does not break blinding, but it is a choice that adds two events, and the deviation should say so in those words.

#### 2. The frozen stage 3 analysis will need about 16 GB of memory just to load its data

- **Where:** `analysis/analyze_stage3.py:224-237` (`load_snapshots`), used by `coverage`, `preflight` and `run`.
- **What happens [ran]:** it parses every snapshot and keeps the whole thing in a dictionary. Loading the 571 pilot snapshots peaked at 1158 MB, about 2 MB each (each file is 30 KB compressed, 643 KB as JSON). The live stage is 28 days × 288 = 8064 snapshots. Scaled linearly that is about 16 GB before any analysis starts. The scaling is **[inferred]**; the per-snapshot cost is measured.
- **Why it matters:** the Windows PC is short of memory (that is why the cloud recorder exists). A standard GitHub runner has 16 GB. So on Dec 18 the one-shot test most likely crashes, and the fix would then be a change to a frozen script after the data exists. Even the counts-only `coverage` mode would stop working partway through the stage.
- **Fix I would make:** before Nov 20, change the loader to keep only the fields the analysis reads, show on the synthetic fixtures that the results file is byte-identical, re-hash, and log it in `FROZEN_stage3.md`. If you would rather not touch the script, the alternative is to decide now that the Dec 18 run happens on a machine with 32 GB or more, and write that down.
- For comparison, stage 2's `coverage` mode on 3247 snapshots peaked at 29 MB. **[ran]** Stage 2's `run` mode memory is not measured, because I may not run it.

#### 3. A renamed field in Kalshi's trade data turns into a KILL verdict with no warning

- **Where:** `load_tape` in `analysis/analyze_stage2.py:518` and the same pattern in `analyze_stage3.py`.
- **What happens [ran, synthetic]:** trades missing `yes_price_dollars`, `count_fp` or `created_time` are skipped silently. I fed it trades using `yes_price` and `count`. It returned an empty tape and said nothing. An empty tape means zero maker fills, and fewer than 100 fills (S3) or 200 fills (T2) is a KILL by rule.
- **Why it matters:** a false KILL from a format change is the worst failure a pre-registered test can have, because the rules then say the idea is dead. The field names are untested against live trade data. They are consistent with the snapshot fields, which do match **[ran]**, so I think the risk is low but it is unverified **[inferred]**.
- **Fix I would make:** stage 2's script is locked, so add a step to the run procedure instead: after `pull_after.py`, count trades pulled against trades parsed (a count, not a result) and stop if they differ. For stage 3, before the freeze, make the script count skipped trades and return INCOMPLETE if more than a trivial share are skipped.

### Severity B: real defects, lower odds or smaller effect

#### 4. The stage 2 run chain has a hole that the stage 3 chain already closed

- **Where:** `.github/workflows/stage2-recorder.yml` (the "queue successor" step) against `.github/workflows/stage3-recorder.yml`.
- **What happens [read, ran]:** stage 2 queues its successor once, at the start of the run, with no retry and no second attempt at the end. On Nov 11 a scheduled run took the queued slot, which cancelled the dispatched successor, and then that scheduled run ended as "failure" without recording anything. Nothing was queued until the next scheduled run fired 78 minutes later. That is the 100 minute gap in finding 1.
- I could not find out why that scheduled run failed. GitHub reports the run as failed but lists no failed job. **Undetermined.**
- Stage 3's workflow retries the queue call four times and queues again at the end of the run.
- **Fix I would make:** port stage 3's end-of-run re-queue to stage 2. With two days left, weigh that against the risk of editing a live recorder. If the local recorder is healthy, leaving it alone is defensible.

#### 5. Every stage 3 handover loses one slot

- **Where:** `stage3/cloud_loop.py:201` and `:214`.
- **What happens [ran]:** the loop stops taking snapshots 200 s before its deadline but keeps the minute poller alive until 60 s before the deadline, so the run exits after the next slot's time has passed. All 8 handovers in the pilot lost exactly one slot (for example 11:52:30 then 12:02:30). Stage 2's loop exits at once and lost none.
- **Why it matters:** about 4 slots a day, 1.4%. That is well inside the 80% day rule, so it will not cost a day. It does cost about 110 candidate snapshots over the stage for no reason.
- **Fix I would make:** let the run exit as soon as its last snapshot is done and have the successor's poller cover the minute series, or take one more snapshot before exiting. A recorder change, allowed before Nov 20.

#### 6. Missing depth is treated as zero depth, which makes fills easier

- **Where:** `analysis/analyze_stage2.py:462` (`depth = max(x for x in (dbook, dtop, 0.0) if x is not None)`), and the same fallback in `maker_fills` in `analyze_stage3.py`.
- **What happens [ran, synthetic]:** when a row has neither a book depth nor a top-of-book size, depth becomes 0 and a single traded contract counts as a fill.
- **Why it matters:** it biases S3 and T2 toward more fills, in the optimistic direction. How often it happens on real data is **not measured**. The recorder only stores books for quotes between 3¢ and 97¢, so it is not obviously rare.
- **Fix I would make:** for stage 3 before the freeze, treat a row with no depth information as no fill, or at least report how many fills used the fallback. For stage 2 the script is locked: report the count of fallback fills next to the result.

#### 7. One market without a result drops the whole event, and the notes say otherwise

- **Where:** `analysis/analyze_stage2.py:580` (`all(results[t] for t in tick)`), against `analysis/NOTES.md` item 2 ("A voided market loses only its own S2 and S3 rows").
- **What happens [ran, synthetic]:** a single empty result marks the event unsettled, and unsettled events are dropped entirely.
- **Why it matters:** with 10 events needed and 9 to 11 likely, one voided strike could decide between a verdict and INCOMPLETE. How Kalshi reports a void (empty result, or a value like "void") I did not verify **[inferred]**.
- **Fix I would make:** after the settlement pull, count markets with an empty result per event before running. If any exist, stop and decide by logged deviation.

#### 8. The stage 3 PASS and KILL conditions can both be true

- **Where:** `docs/stage3/PREREGISTRATION_stage3.md:64`, `analysis/analyze_stage3.py:446-452`.
- **What happens [ran, synthetic]:** PASS is "lower bound above 0", KILL is "upper bound below 1¢". An interval of 0.2¢ to 0.8¢ satisfies both. The code checks KILL first, so it returns KILL. `NOTES_stage3.md` does not list this reading and `test_verdict_rules` does not cover it.
- **Why it matters:** it is unlikely, because the red-team review puts the smallest detectable effect near 6¢, so an interval narrower than 1¢ is improbable **[inferred]**. But an unstated tie-break in the primary gate is exactly what a pre-registration exists to prevent. KILL is the defensible answer (a real edge under 1¢ is not worth trading), it just has to be written down before data.
- **Fix I would make:** one line in the deviations log before Nov 20, and one test.

#### 9. A trade with no hedge path is silently reported as hedged

- **Where:** `analysis/analyze_stage3.py:408-411` (`hedge_term` returns 0.0 with fewer than 2 path points).
- **What happens [read]:** the "hedged" P&L for that trade equals the unhedged P&L. The per-trade point count is kept but never summarised in the output.
- **Why it matters:** the primary test is on hedged P&L. If the minute poll fails for a stretch, the hedged series quietly becomes a mixture. The pilot's minute poll was 98.2% complete **[ran]**, so today it is small.
- **Fix I would make:** before the freeze, print the number of trades with fewer than 2 hedge points, and say in the notes whether they stay in the hedged mean.

#### 10. The freeze record is out of date

- **Where:** `analysis/FROZEN_stage3.md:10`.
- **What happens [ran]:** it lists `analysis/pull_after.py` as `3c33715a…5f28`. The file is `cddb55ce…d29e`, because PR #16 changed it afterwards. The other four hashes in the table match.
- Three files (`analyze_stage3.py` line 3, `stage3/NOTES.md`, `analysis/NOTES_stage3.md`) and `DESIGN.md` line 7 still give the pre-registration's hash as `a62576a8…` and call it "not edited". It has since had deviation 1 appended and now hashes to `a258ac46…`. `DESIGN.md` says a different hash means the file "was changed after the freeze", which is now literally the case.
- **Why it matters:** the hash table is the only thing that lets anyone check that the analysis was not adjusted after the fact. One stale line makes every line doubtful.
- **Fix I would make:** correct the table with a dated note, and add a test that recomputes every hash in `FROZEN_stage3.md` so CI fails when they drift.

### Severity C: security and privacy

#### 11. Your personal email address is public in the commit history

- **What [ran]:** 17 of the 19 commits on `main` carry your personal Gmail address as author. The repo is public.
- **Fix I would make:** turn on "Keep my email addresses private" in GitHub so future commits use the noreply address. I would **not** rewrite history: the commit timestamps are the evidence that rules came before data, and rewriting destroys that. So the existing 17 stay exposed unless you accept that cost.

#### 12. Stage 3 depends on one free service that its terms arguably don't allow

- **What [read]:** GitHub's Actions terms say hosted runners should not be used for "any other activity unrelated to the production, testing, deployment, or publication of the software project associated with the repository", nor for load "disproportionate to the benefits provided to users". A recorder running 24 hours a day, plus about 11 days of sleeping `wait` runs to keep the chain alive, sits against that wording.
- **Why it matters:** whether GitHub would act is **[inferred]**; I have no evidence either way. But as far as I can see from the repo, stage 3 has no second recorder. Stage 2 has the PC. If Actions is disabled for the repo in week three, stage 3 is INCOMPLETE and four weeks are gone.
- **Fix I would make:** a second, independent stage 3 recorder on something you control (any always-on machine or a small paid VM), merged under the same kind of rule as stage 2's deviation 4. That needs a logged rule before Nov 20.

#### 13. Blinding is on the honour system

- **What [read]:** all recorded quotes are on public branches, and settlement results are public on Kalshi. Anyone, including any Claude thread with repo access, could compute the result early. The guards in the scripts stop accidents, not intent. `REVIEW_code.md` finding 5 already says this.
- **Fix:** none that is cheap. Know that "we didn't peek" rests on trust and on the thread instructions, not on a mechanism.

#### 14. Workflow hardening (low risk today)

- **What [read]:** both recorder workflows grant `contents: write` and `actions: write` to the whole job; actions are pinned by tag (`@v4`), not commit; `${{ inputs.max_minutes }}` is pasted straight into a shell command. Only someone with write access can exploit the last one, so the practical risk is small. `stage2-check.yml` runs on every pull request with a read-only token and takes one live snapshot.
- **Fix I would make:** pin actions by commit SHA, pass inputs through `env:`, and after stage 2 ends, remove workflows that are no longer needed.

### Severity D: fragile or confusing

- **15. No pagination on Kalshi `/markets` in the stage 2 recorder** (`stage2/record_snapshot.py:44,46`, `limit=1000`, cursor ignored). The most markets seen in one snapshot is 318 **[ran]**, so it is fine today and would truncate silently if listings tripled.
- **16. Hidden ordering dependency** in `analyze_stage2.py`: `s2_trades` reads `r["g"]`, which only exists because `s1()` ran first **[read]**. Locked, so document rather than change.
- **17. Two definitions of the slot grid.** The analysis takes the grid phase as the median over both sources; `status.py` uses the local median when local data exists **[read]**. The two tools can disagree about a slot at the margin, so `status.py` is a guide to coverage, not the authority.
- **18. `stale_split`** (`analyze_stage3.py:539`) takes the latest poll at least 60 s old with no upper age limit, and rescans the whole grid for every trade **[read]**. A poll from an hour earlier would count as the stale price. Reference-only output, so low stakes.
- **19. The analysis test suite takes 254 s and leaks file handles** (75 "unclosed file" warnings). The other two suites run with warnings as errors in CI; this one does not **[ran]**.
- **20. Leftover branches.** Eleven working branches besides `main` and the data branches are still on the remote **[ran]**. At least one belongs to an open PR. I did not check the others for unmerged work.

---

## 3. What the overnight runs got right and wrong

### How the work was actually approved [ran]

Every PR from #1 to #17 was opened and merged by the same GitHub identity, between 40 seconds and 22 minutes after opening. For the three I checked (#12, #14, #17), CI had finished and passed before the merge. None had a human review. The three "independent review" documents were written by other Claude threads. They found real problems, so they were worth doing, but they are the same system checking itself, with the same blind spots. Findings 1, 2, 5, 8 and 9 above all sat in code those reviews had already covered.

### Keep

- **The pre-registration structure**, deviations logs, run-once guards and counts-only modes. This is the part of BOB I would trust most.
- **The red-team power correction** (PR #9): the smallest reliably detectable mispricing is about 6¢, not the 4¢ in the draft you approved. It makes the project look worse and is correct to state. You have not signed off on it (see open questions).
- **The out-of-the-money-only volatility fit** (PR #6) and the tests around it.
- **The historical-settlement fallback** (PRs #15, #16). Without it, early events would have been dropped as unsettled after Kalshi archives them. A real catch.
- **The self-queueing run chain** (PRs #13, #14). GitHub's schedule barely fires on this repo; the chain is why there is data at all. Across 47 runs, every handover but one was clean.
- **The 48 hour stage 3 pilot** and its counts-only report.
- **Stage 3 deviation 1** (PR #17, the row-sync rule flags rows instead of dropping them). I read the argument and agree with it: the dropped rule conditioned on a price read *after* the quote, which is the same price the hedge starts from, so dropping on it selects on the outcome. It was approved by the coordinator, not by you, and it is yours to revert until Nov 20.

### Revert

**Nothing needs reverting wholesale.** I looked for a decision that should be undone and did not find one. What I found are things to correct before the two dates (findings 1 to 10), not things to roll back.

### Where the notes claim something the code doesn't do

| Claim | Where it is made | What is true |
|---|---|---|
| A gap must exceed 6 hours to fail an event | `stage2/status.py:22`, `README.md:33` | One hour, for every event except Fridays. **[ran]** |
| A voided market loses only its own rows | `analysis/NOTES.md` item 2 | One empty result drops the whole event. **[ran, synthetic]** |
| `pull_after.py` is frozen at `3c33715a…` | `analysis/FROZEN_stage3.md:10` | It was changed by PR #16 and hashes to `cddb55ce…`. **[ran]** |
| The stage 3 pre-registration is `a62576a8…` and "not edited" | `analyze_stage3.py:3`, `stage3/NOTES.md`, `analysis/NOTES_stage3.md`, `DESIGN.md:7` | Deviation 1 was appended; it is `a258ac46…`. Only `FROZEN_stage3.md` says so. **[ran]** |
| "Approved by Mattias on 2026-11-06 and frozen" | `DESIGN.md:7`, the pre-registration's title | You approved the draft. The red-team edits, the fee rounding and deviation 1 were approved by a Claude coordinator under your "approve automatically" instruction. The pre-registration's own banner does disclose this; the headline does not. **[read]** |
| Each stage 2 run queues its successor | PR #14 | True, but once, at the start, with no retry. A cancelled successor is not replaced (finding 4). **[read]** |
| The fee schedule re-check is still open | `stage3/NOTES.md` item 11 | Project notes outside the repo say it was done on Nov 16 with no change. Nothing on `main` records that. The pre-registration requires the check, so the record should be in the repo. **[read]** |
| Stage 3 has three modes | `stage3/README.md` "Modes" | There is a fourth, `wait`, which is the one running now. **[read]** |
| "BOB stage 2 cloud recorder" | `README.md` title | The repo also holds stage 3 and both analyses. **[read]** |

### One over-claim in the design, not the code [inferred]

The pre-registration says a T1 KILL means "the Deribit anchor gives no taker edge of 1¢ or more… The taker idea ends." The fair value used is knowingly rough: the notes themselves list the basis between Deribit's index and Kalshi's settlement index, no intraday variance clock, and near-expiry options in the early UTC hours. So a KILL would show that *this* fair value has no edge. It would not show that no Deribit-based fair value has one. That is my judgement of the design, not something I can test.

---

## 4. Gaps

**Tests**

- No test asserts the hashes in `FROZEN_stage3.md` (finding 10).
- No test for the PASS and KILL overlap (finding 8), for an all-skipped trade tape (finding 3), or for zero-depth fills (finding 6).
- No test that a normal event's best possible coverage is 300 of 360. The fixtures list events for the whole window **[inferred from the fixture generator's name and the test names; I did not read the fixtures]**.
- Nothing exercises the stage 3 loader at realistic size.
- No test of either workflow's handover. That logic is YAML and shell and is verified only by watching production.
- The numerical core has only ever run on synthetic data. That is by design, but it means the first real run is also the first real test.

**Error handling**

- Silent skips where a loud failure is needed: malformed trades (finding 3), missing depth (finding 6), missing hedge path (finding 9).
- 9 stage 2 snapshots had request errors (Deribit index and chain) and were correctly marked invalid **[ran]**. That path works.

**Recovery**

- Stage 2 chain: no recovery when a queued successor is cancelled (finding 4).
- Stage 3: no second recorder (finding 12).
- 3 of about 3130 pushes failed and were recovered by the next run **[ran]**. That path works.
- There is no written procedure for the two one-shot runs: which machine, which commands in which order, which counts to check before the irreversible `run`. The commands are in `analysis/README.md`, but the run happens once and should be rehearsed from a checklist.

**Docs**

- Root README (stage 2 only), `stage3/README.md` (`wait` mode missing), stale hashes, stale fee item, the 6 hour claim.
- Stage 1 code and the authoritative stage 2 pre-registration live only on one PC that loses power and wifi.
- No single page says what BOB is, what state each stage is in, and what happens on which date.

---

## 5. Next steps, in order

Each is sized for one thread. Steps 1 to 5 have deadlines.

1. **Check the local recorder and decide the coverage reading** (before Nov 19 15:25 UTC). Run `status.py --fetch-cloud` on the PC to get the merged count. Then choose between accepting the rule as coded or logging deviation 6 (finding 1). Correct the 6 hour claim either way.
2. **Write the stage 2 run checklist** (before Nov 19 15:25 UTC). Machine, commands, and the counts-only stops before `run`: trades pulled against parsed, empty results per event, fallback fills. No change to locked code (findings 3, 6, 7).
3. **Fix the stage 3 loader's memory use, or commit to a big machine** (before Nov 20 00:00 UTC). Prove identical output on the fixtures, re-hash, log it (finding 2).
4. **One pre-freeze stage 3 PR for the small analysis items** (before Nov 20 00:00 UTC): the verdict tie-break, the skipped-trade guard, the hedge-point summary, the zero-depth handling, the corrected freeze table and a hash test (findings 3, 6, 8, 9, 10). Each is a logged change made before any live data.
5. **Fix the stage 3 handover slot loss** (before Nov 20 00:00 UTC), finding 5. Decide in the same thread whether deviation 1 stays.
6. **Decide on a second stage 3 recorder** (finding 12). If yes, it needs its merge rule logged before Nov 20, so it competes with steps 3 to 5 for time.
7. **Stage 2 chain hardening** (finding 4), only if you want it for the last two days.
8. **Docs pass:** root README as a project front page, `stage3/README.md` modes, fee re-check record, the approval wording.
9. **Privacy and workflow hardening:** noreply commit email, pinned actions, narrower permissions, delete leftover branches (findings 11, 14, 20).
10. **Bring stage 1's code and the local pre-registration into the repo**, or at least their hashes.

I would build nothing new until stage 2 has returned its verdict.

---

## 6. Open questions only you can answer

1. **Is the local Windows recorder still running, and did it record between 20:43 and 22:18 UTC on Nov 11** (15:43 to 17:18 Toronto)? That decides whether the Nov 11 and Nov 12 events are already rescued.
2. **Coverage reading:** keep "the event must be listed" with a 360 slot denominator, which makes the allowance one hour, or log a deviation before Nov 19 15:25 UTC? You would be deciding with the coverage counts known.
3. **Stage 3 deviation 1:** keep or revert? It lapses to "keep" at Nov 20 00:00 UTC.
4. **The 6¢ figure:** do you accept that stage 3 can reliably detect about 6¢ of mispricing, not the 4¢ in the draft you approved? If 6¢ is too coarse to be worth four weeks, now is the time to say so.
5. **A T1 result strictly between 0 and 1¢:** KILL (what the code does), PASS, or INCONCLUSIVE?
6. **Where will the two one-shot analyses run, and who runs them?** This decides whether finding 2 is a code fix or a hardware choice.
7. **Is a public repo intended**, given your email in the history, the results, and the recorded data? Note that making it private would likely put the recorder over the free Actions allowance **[inferred]**.
8. **Do you accept the GitHub terms risk for 28 days of stage 3**, or do you want a second recorder or a different host?
9. **Should stage 1's code come into this repo?** I could not review it, and its PASS is the reason stages 2 and 3 exist.
10. **Can the local folder be shared with a thread?** Access to `D:\Coding\Projects\BOB` was refused. If an `OVERNIGHT_NOTES.md` or an `overnight/claude` branch exists there, I have not seen it and this review does not cover it.
11. **When should `stage3-pilot` be deleted?** The analysis refuses pilot data, so it is only clutter, but PR #18 reads from it.
