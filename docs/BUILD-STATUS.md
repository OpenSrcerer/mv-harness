# Build status (resume point)

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
| C: W2 modules | pipeline over 8 modules: builder (opus; M4, M6a sonnet) → lens reviewer(s) (opus; M6b gets R-CONTRACT + R-WORDS) → fixer (sonnet) → re-review (opus), up to 2 fix rounds | running | wf_bb5257ef-656 · `C:\Users\OpenSrcerer\.claude\projects\C--Users-OpenSrcerer-Desktop-playground\cfc48f00-d046-409f-8e46-ef42c153038f\workflows\scripts\mvh-c-modules-wf_bb5257ef-656.js` (relaunch with resumeFromRunId in the same session, or relaunch the script in a new one: agents resume from progress files) |
| D: W3 integration | integrator (opus) → module fixers (sonnet) ‖ completeness critic (opus) | pending | — |
| E: W4 final | R-ADVERSARY (opus) ‖ R-DOGFOOD (sonnet) ‖ R-PLATFORM (opus) → fixers (sonnet) | pending | — |

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
