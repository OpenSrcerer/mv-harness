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
- (2nd start) review tests: 19 pass incl. real (test_structure_real_upstream now passes).
- p_sens.py rewritten; out/_wip/r-dsp-m2-r3/p_sens.log: F4-r2 fix robust: F 1.0 + chorus groups C/C for split_min_novelty
  0.45..0.6, w_pattern 0.5..0.9, w_embedding 0.3..0.7, dyn_gate 0.5..1.0, cost_q 70..80, adjacent penalty 0.8..0.9.
  17.0 s boundary comes ONLY from the phrase-grid refinement (disabled/0.7 -> F 0.909). penalty 1.0 -> chorus#1 joins verse group.
- background: synth rerun --from structure (synth.log; runner re-runs separate_hq = cache invalidated by another module),
  replay_all (4 real songs, replay_all.log).
- synth full rerun (--from structure, fresh harmony/dynamics too) DONE: sections 0.99/5.0/9.0/17.0/25.0/34.5/50.52, F 0.923
  (spurious 2+2 intro split at 5.0, both group A). p_full.py: swapping ONLY the real rhythm events into the hd harness gives
  the same 0.923 (fixture rhythm = truth = 3rd circular input). Real bars at 7.018/50.518 are +18 ms (2 frames) off.
  p_jitter.py: constant -10/-20 ms bar shift -> bridge split 2+3, F 0.923. p_pattern.py: fx.bar_pattern slot edges sit ON the
  16th grid -> +1 frame bar shift moves every hit to the previous slot, cos(identical bars) = 0.0. score(5.0)=2.47 vs
  strong_cut 1.4*cost=2.41 (harness 2.34): knife edge. => NEW major (F4-r2 not fixed in the real pipeline / jitter-sensitive).
- p_loop.py: uniform 32-bar loop: refinement adds 3 splits (8-bar -> 4+4, same group) 6->9 sections: candidate minor.
- NEXT: write tests/review/M2/r-dsp/test_structure_rhythm_jitter.py (+ data/synth_real_rhythm.npz), real-song replay compare.
- WROTE tests/review/M2/r-dsp/test_structure_rhythm_jitter.py (+data/synth_real_rhythm.npz): 3 fail (real rhythm F .923,
  -10 ms shift F .923, bar_pattern cos 0.0), 2 pass (precondition rhythm within tol, +10 ms).
- replays r2 vs r3 (probes/cmp_sections.py, cmp_edm.py, sec_energy.py): megafauna drop 141.8-212.7 (r2) -> 141.8-176.1 (r3):
  refinement splits drop 4+4, first-4-bar drive 2.49 raises extension threshold; SPIKE says loud plateau 146-217. NEW major F6.
  versatile S11 129.2 break->outro (group C); jeremy 194.1 verse->chorus; newton 69.6 8->4+8 (76.6 off-grid?) -> check.
- WROTE tests/review/M2/r-dsp/test_structure_drop_extent_real.py (real; running).
- megafauna drop test FAILS (cover 0.45). Control with split_min_novelty 0 ALSO fails -> cause is grouping (151.0 in K not J,
  no merge) + drop-extent rule (drive of FIRST section); removed control, corrected docstring. p_mega.py probes.
- NEXT: newton 69.6/76.6 check, uniform-loop minor, ruff on new tests, minors -> docs/review/M2-r-dsp.md Round 3, report.
- minors appended to docs/review/M2-r-dsp.md (Round 3: r3-m1..m5). NEXT: report docs/build/reports/r-dsp-m2-r3.md, StructuredOutput.
- report written. DONE except StructuredOutput.
