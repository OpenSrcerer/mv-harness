# r-contract progress (W1b independent review, video-agent lens)

## Done
- Read PLAN, SPIKE, CONTRACT (all), spike/main §1-2.

## Next
- Run walking skeleton into out/_wip/r-contract/synth; probe lib in Node + Python; parity edge cases; fixture audit; failing tests.

## Commands that work
- Git Bash: powershell.exe -NoProfile -File scripts/run.ps1 python ...

## Gotchas

## Milestone 1 (skeleton + probes)
- Skeleton: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 mvh analyze tests/contract/synth/_truth/synth-song.flac --out out/_wip/r-contract/synth --no-network` (exit 0, ~9 s). NOTE: --out is the SONG folder.
- JS/Python parity probe on exotic frame rules (120/144/200 fps, 7.5, 1, frame0 -3/1000, early) = 0 diffs (scratchpad probe).
- Candidate majors: (1) cues next() hides co-timed cues (drop, build_start unreachable by next-iteration);
  (2) lines.tsv singer drops 2nd character on duet lines; (3) notes stub/outputs pattern notes.{src} claims notes.vocals + notes/vocals.mid (double producer; publish can delete vocals' file);
  (4) vizState(t) default 60 fps loses ~25% onset flags at 24/30 fps; CONTRACT §9 documents no fr arg;
  (5) events('visemes').at(t) returns only one voice in duets (lead voice viseme unreachable via documented recipe).
- Minors: texture vs curve.at for NaN channels off-grid (6.6 semitones), mvh.d.ts not copied to lib/, bandBytes G/B not raw/peaks, pulse prev/next only, index.json 67 KB.

## Milestone 2 (DONE)
- Tests written and verified failing: tests/review/w1b/contract/test_rcontract_video_agent.py (9 fail), rcontract_video_agent.test.mjs (3 fail). ruff clean.
- Review: docs/review/w1b-r-contract.md; report: docs/build/reports/r-contract.md. Verdict pass-with-fixes, 0 blockers, 5 majors, 10 minors.
- Run: `powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/w1b/contract` and `node --test tests/review/w1b/contract/rcontract_video_agent.test.mjs`.
- Gotcha: false alarm on the flash rule from a naive floor/ceil check (18.4*100 float); conventions.flash_samples handles it.
