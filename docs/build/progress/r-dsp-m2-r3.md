# r-dsp-m2-r3 progress (independent reviewer round 3, M2 Rhythm, lens R-DSP)

## Done
- started (fresh; no prior r3 progress). Target: verify F4-r2 fix (structure with real upstream), look for regressions.
- outage #1 at ~02:58: synth full rerun and replay_all were interrupted; probes/p_sens.py was corrupted (all blanks) -> rewrite.
- 2nd start (after outage): read fixer-m2-r2 report (changes: nov_pat/nov_emb, edge damping, dyn gated, phrase-grid split
  split_min_novelty=0.5 tuned on synth, agglomerative groups w/ repeat_adjacent_penalty 0.85).

## Next
- run tests/review/M2/r-dsp (incl -m real), read structure fix, rerun synth full pipeline, real-song replays.

## Commands that worked
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
