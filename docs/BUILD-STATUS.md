# Build status (resume point)

**BUILD COMPLETE (2026-11-10).** The final gate is green except for known, documented review items (docs/build/W4-final-gate.md, docs/SEAMS.md).
Next is the user: review a song in the viewer (`mvh view out/<slug>`), then author its meaning (meaning/interview.md → meaning/intent.md).

If a session expires, a new session reads this file first, then PLAN.md §12, then `docs/build/progress/*.md`.
Every build agent keeps a checkpoint log at `docs/build/progress/<agent>.md` and resumes from it when restarted.
Final reports go to `docs/build/reports/<agent>.md`.

## Model policy
- **Opus** (inherits the session model) for the critical work: the contract architect, the runtime and lib builders, the
  DSP/ML/words module builders, every reviewer, the integrator and the completeness critic.
- **Sonnet** for mechanical or bounded work: env installs, benchmark and fixture capture, fixers, the viewer and harmony
  builders, and dogfooding.

## Workflows
| WF | Agents | Status | Run ID / script |
|---|---|---|---|
| A: W0 spike + W1a contract | env-main (sonnet) → bench-music (sonnet) ‖ bench-words (sonnet); env-sep (sonnet); contract-architect (opus) | **done, gate PASS** (see docs/SPIKE.md) | wf_f9a3f942-cb7 |
| B: W1b foundation | runtime (opus), lib (opus), fixtures (**opus**, upgraded: it is the ground truth for every module) → R-CONTRACT (opus) ‖ R-PLATFORM (opus) → fixer (sonnet, only if blockers/majors) | **done, gate PASS** (orchestrator re-ran `scripts\gate.ps1 W1b`: 9/9 steps) | wf_363e7f56-9f5 |
| C: W2 modules | pipeline over 8 modules: builder (opus; M4, M6a sonnet) → lens reviewer(s) (opus; M6b gets R-CONTRACT + R-WORDS) → fixer (sonnet) → re-review (opus), up to 2 fix rounds | **done** 03:30 (after 1 usage-limit stop and 2 power outages; continuations wf_7901936d-843, wf_041717a6-9b1). M3b clean; 2 blockers + 21 majors open → `docs/build/W2-open-findings.md`, CRs → `W2-change-requests.md`. Commit fd6621a | wf_bb5257ef-656 · `C:\Users\OpenSrcerer\.claude\projects\C--Users-OpenSrcerer-Desktop-playground\cfc48f00-d046-409f-8e46-ef42c153038f\workflows\scripts\mvh-c-modules-wf_bb5257ef-656.js` (relaunch with resumeFromRunId in the same session, or relaunch the script in a new one: agents resume from progress files) |
| D: W3 integration | integrator (opus) → per-module fixer (opus M1/M2/M5/M6b, sonnet others) → opus verifier ×≤2 ‖ completeness critic (opus) → integrator-r2 (opus) | **done** 14:40 (35 agents). Gate: unit 992 pass, e2e/lib-node/determinism pass, 39 review fails all owned by W4. R19 round trip passes. All songs max-run + validate. Commit 3c3974a. Orchestrator viewer check: docs/review/W3-orchestrator-viewer.md | wf_e97bbb13-9a4 |
| E: W4 final | ud1-meaning ‖ ud2-kick (opus) → R-ADVERSARY (opus) ‖ R-DOGFOOD (sonnet) ‖ R-PLATFORM (opus) → 3 fixers by ownership (opus) + opus verifier ×≤2 | **done** 00:10 (17 agents). UD1 + UD2 implemented; most reviewer findings fixed and verified. Commit 1e61bb1. The orchestrator then fixed the harmony NaN crash (blocker W4V2-HARMONY-NAN) and synced the skill's CONTRACT copy. **Open:** the stem stages (DrumSep kick, stem activity, vocals) and the spectral onsets still follow the master level (W4V2-GAIN-*); rap songs over-labelled chorus; real-song folders under out/_wip/integrator are stale (rc.2) and need fresh max runs. **The weekly usage limit is at 90 %**, so further agent work waits for the user's go-ahead. The hourly cron is deleted. | wf_e472123d-042 |
| F: final fixes | ffix-gain (opus) ‖ ffix-form (opus) ‖ ffix-small (sonnet) → fverify (opus) | **done** (4 agents, about 3 % weekly). Form and small fixes pass; gain mostly fixed, trade-offs F-V2..F-V7 in SEAMS. Commit fe64620. Then fresh local re-runs: out/_wip/integrator/rerun.ps1 (5 songs) and r-adversary/run_queue.ps1 (10 inputs). A third power outage at 12:16 stopped them; restarted at 21:17 (logs out/_wip/orchestrator/rerun-*.log). NEXT: once both finish, run the review tests on the fresh folders, then the final gate, commit, and hand the viewer review to the user | `docs/build/workflows/F-fixes.js` |

## Resuming workflow C after an interruption (usage limit, crash, session expiry)
Checkpoint taken 2026-11-08 17:40 with session usage at 92 %. State then:
- **Done** (results in the journal): build M6a, build M6b, review M6a (R-PLATFORM), review M6b (R-CONTRACT).
- **Finishing:** fix M6a r1 (tests pass; the gate is still to run), review M6b (R-WORDS) (report written).
- **Still building:** M1 (report written, nearly done), M2, M3a, M3b, M4, M5. Each one's next step is in its `docs/build/progress/builder-<m>.md`.

Every agent checkpoints to `docs/build/progress/<agent>.md` and resumes from it. Resume scripts (also copied to `docs/build/workflows/`):
- `...\workflows\scripts\mvh-c-modules-resume.js` = `docs/build/workflows/C-modules.js`.
  - Without `args` it sends exactly the same prompts as the running script (verified by a dry run: 34/34 identical), so it hits the cache.
  - It also adds null guards: when an agent dies, its module stops instead of running reviews on nothing, and the log names the resume key.
- **Same session:** `Workflow({scriptPath: <resume script>, resumeFromRunId: 'wf_bb5257ef-656', args: {resume: {M5: 'build', M6b: 'fix:1', ...}}})`.
  - List only the modules whose agents died. Use the step each one died at: `build`, `review`, `fix:<r>` or `rereview:<r>`.
  - Those agents get a "RESUMED: read your progress file" suffix, which changes their cache key so they run live. An agent that died is journalled
    as null, and a plain resume would replay that null.
  - To find the dead agents, read `subagents/workflows/wf_bb5257ef-656/journal.jsonl`: a `started` entry with no `result` (or a null result) is dead.
- **New session:** `resumeFromRunId` does not work across sessions.
  - Run `docs/build/workflows/C-modules.js` with `args: {resume: {<every unfinished module>: 'build'}}`.
  - Before that, delete the finished modules from `MODULES`, judging by their `docs/build/reports/` files.
  - Finished builders re-read their progress files and return quickly.

### Resume log
- 2026-11-08 ~18:00: the 5-hour usage limit killed 12 agents: build M1–M5 (6 builders), fix M6a r1, rereview M6a r2, review M6b R-WORDS, fix M6b r1,
  and both M6b r2 rereviews. Done before the cut: build M6a and M6b, review M6a, review M6b R-CONTRACT.
- 2026-11-08 21:02: no stale processes or locks were left. Resumed the same run (`wf_bb5257ef-656`, task w06t4ot5h) with the resume script and
  `args.resume = {M1..M5: 'build', M6a: 'fix:1', M6b: 'review'}`. M6b's R-CONTRACT review also reruns, which is cheap because its progress file is complete.
  If this run is interrupted too, read the journal again and repeat with the steps that died.
- Lesson: the resume cache only replays the **unchanged prefix** of agent() calls in call order. Once build M1 (the first call) changed, every later
  call ran live, including finished ones: build M6a, build M6b and review M6a. They resumed from their progress files, so they cost tokens but lost no work.
  Next time, put the finished modules first in `MODULES`, or drop them and run only the unfinished ones.

### Power outage (2026-11-09 ~01:00)
- The desktop lost power, so the session restarted. Its cron check-ins were lost and the original run's journal ended in a torn line.
- State at the cut:
  - **Done:** M3b and M6a.
  - **Re-review round 3 in flight:** M1, M4, M5, and M6b R-CONTRACT (M6b R-WORDS round 3 had finished).
  - **Fix round 2 in flight:** M2 and M3a.
- The files survived intact: no NUL bytes or empty files, and `git fsck` is clean.
- 02:50: launched the **continuation** `mvh-c-continue.js` (run wf_7901936d-843, task wjy0gfhs7). It is generated by `gen_continue.js` from the journal.
  - It runs only the remaining steps, feeding in the round-2 findings: fix r2 then re-review r3 for M2 and M3a, and re-review r3 for M1, M4, M5 and M6b.
  - Every agent gets the RESUMED suffix, so it reads its progress file first. Most of them had already written their reports.
  - A safety check-in (cron) is set for 07:47, just after the 5-hour reset.

### Second outage (2026-11-09 ~03:00)
- Before the cut, the continuation run wf_7901936d-843 finished these steps:
  - fix M2 r2;
  - final re-reviews (round 3) of M1, M4, M5 and M6b R-CONTRACT, with 4, 1, 4 and 5 blockers/majors still open.
- Still unfinished: fix M3a r2 (its report was written) and the round-3 re-reviews of M2 and M3a.
- 03:08: launched `C-continue2.js` (run wf_041717a6-9b1, task wxwmx1xvb) for just those 3 steps.
- An **hourly** safety check-in now runs at :17 past each hour while the session is alive. It resumes whatever an outage or limit stopped.

## User decisions (2026-11-09). Implemented in W4 (workflow E) phase 0 by dedicated agents; integrator-r2: do NOT start them, just avoid conflicting changes
- **UD1, meaning input format: APPROVED.**
  - meaning/intent.md is read in exactly two ways.
    1. **The interview template.** One documented grammar, round-tripped exactly, accepted fenced or unfenced. It is the ONLY source of structured
       fields: characters, voice mapping, per-section feel/meaning/movement/camera/palette, and do-not rules (the only hard constraints).
    2. **Free text.** Everything outside the template is passed to agents as the user's prose notes, marked user-authored, never parsed into fields
       and never turned into do-not rules.
  - Plus the viewer's machine-written managed block (D-M6a grammar).
  - Remove the heuristic markdown guessing (bold labels, "Avoid…" headings, colon labels).
  - Rewrite the review tests that assert heuristic parsing of free-form markdown to the new rule. Template-variant and round-trip tests stay.
  - Tell the user in SKILL.md / interview.md: "use the template for anything that must be obeyed".
- **UD2, kick source: APPROVED (2026-11-09).**
  1. **Agent-facing kick = the drum-stem kick.** These read drum_hits (drum=kick) whenever the drums stage produced it: the lib (mvh.js / mvh_load.py
     kick events and kick helpers), brief.md kick counts, the viewer kick lane, and the frames export.
  2. **Fallback = hits.kick from the mix**, used when the drum stems are absent (draft profile, separation failed). It is marked lower quality.
  3. **The manifest records which source is in use**: `kick_source: drums|mix` (a contract decision).
  4. **QA:** compute the agreement between the two timelines (share of mix kicks within ±30 ms of a stem kick, and the reverse) and raise a QA flag
     when it is low.
  5. **Re-tune hits.kick for precision over recall** (fewer invented kicks). The M1 review tests that demand full recall on hard textures are
     rewritten to the fallback's precision target instead of chased.
  6. The continuous hits.kick curve (the viz-style pulse in vizState) is unchanged.
  7. rhythm, dynamics and structure keep using the mix kick internally as one input among several: no DAG change.

## Hold (user, 2026-11-09 00:30)
When workflow C finishes: run the module gates, update this file, then **STOP**. Do not start workflow D or E until the user says the new usage
window has started.
Update 00:35: the user asked me to watch for the reset myself. A session-only one-shot check-in (cron dee6a425) fires at 02:07 local; the 5-hour window
resets at about 02:00. It does the following:
- Re-checks usage, and reschedules itself 15 minutes later if the window hasn't reset.
- Resumes any C agents that died.
- Runs the gates, then **auto-launches workflow D**.
- ~~Holds before E~~. Update 00:40: the user approved spending the limits to finish. Run D and then E through to done, and schedule a check-in at
  each limit reset (cron 85d048eb at 02:07; later ones via CronList). Commit + push after each workflow (see Git).
If this session has exited, the check-in is gone: a new session should follow these steps manually.

## Git
The user approved commits and pushes on 2026-11-09 00:40 ("start pushing commits to git to save our work remotely, the repository is private").
- 04fe399 (2026-11-09 00:40): first commit, pushed to origin/master. 739 files, about 9.7 MB. Workflow C was mid-run.
- Procedure, through WSL only:
  1. List the files with `git ls-files --others --exclude-standard`, plus the modified ones.
  2. Check for files over 300 KB and media or model extensions.
  3. Run `python -I scripts/lyricscan.py <filelist>`. It must report 0 files with matches. It builds 5-grams from the cached real-song lyrics and
     prints paths and counts only.
  4. Commit with the Co-Authored-By trailer, then `git push`.
  The WSL script lives in the scratchpad: commit.sh uses `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`.

## Log
- 2026-11-08: plan reviewed and finalised; test songs added; build started with workflow A.
- 2026-11-08: workflow A done (5/5 agents). ROCm works for the sep worker. Gate PASS: docs/SPIKE.md amends PLAN; models.lock.json
  merged to 28 entries; .gitignore fixed (`build/` was hiding docs/build; nested sep venvs; generated fixtures). Workflow B launched.
  Still uncommitted: ask the user before the first commit.
- 2026-11-08: workflow B done (6/6 agents; 1 blocker + 10 majors found by reviewers, all fixed; CONTRACT decisions now D1-D46).
  Gate W1b PASS. Real-song fixtures rebuilt. Workflow C launched (ultracode on: added a re-review after each fix round).
  Routed leftovers: models.lock schema mismatch → M3a; lyrics deps += ingest → M5; merge_cues → M2 cues; lines.tsv 'C1+C2' → M6b.
  Modules record decisions in docs/contract/decisions/<module>.md for the W3 integrator to merge into CONTRACT.md.
- 2026-11-09: W3 integrator-r2 done (docs/build/reports/integrator-r2.md). D67-D77 added; fresh max runs of all 5 songs (analyze 0 / validate 0) in
  out/_wip/integrator/<slug> (phase-1 folders in out/_wip/integrator/_phase1); R19 round-trip test passes; gate: unit PASS, determinism PASS,
  review 39 fails = W4 items only (UD2 M1 kicks 11, UD1 M6b intent 23, critic W3C-3/W3C-4/grooves/backing 5). docs/RUNS.md written; SEAMS updated.
