# builder-m2 progress (M2 Rhythm: allin1, rhythm, structure, choreo, cues)

## Done (all five stages implemented, version 1.0.0)
- allin1: analyze(stems_input=StemsInput(...)) on own float32 WAVs; activations [T x 13] 100 Hz; embeddings stems-concat
  pooled to 10 Hz (768 dims). Reader for both real and stub copies: `mvh.stages.allin1.read.load_allin1`.
- rhythm: beat_this + madmom RNN/DBN + allin1 + DSP; per-tracker latency calibration vs attacks (synth: beat_this
  -20 ms, allin1 +10 ms, madmom 0 ms = truth); tempo arbitration (consensus + drum metrical + salience + prior);
  beat-only HMM (madmom-infer state space, own obs model: the port's np.asarray(ndmin) breaks on numpy 2.5);
  nearest-transient snap (>= 15 dB, +-25 ms); pulse flags + virtual grid; 2-of-3 downbeat vote + meter HMM.
  Synth: beats F1 1.0, downbeats F1 1.0, tempo err 0.03 BPM, median 1.2 ms, pickup + 3/4 bar exact.
- structure: DP boundaries on per-bar score, HPSS kick rate, repeat groups (adaptive threshold), allin1 vs
  structural labels, phrases, EDM roles (synth: build bars 13-16 and drop at bar 18 exact).
- choreo: with truth upstream counts/accents/holds exact, hit points 17/17, groove partition 0.99.
- cues: merge_cues, compact kinds/sources, in-pulse tier-4 beats only, moments.
- Dev harness: tests/synth/m2/ctx.py (FixtureCtx + overlays), run_chain.py, score.py.

## Done since (found on resume at 21:00)
- Real chain rhythm/structure/choreo/cues done on all 4 songs: out/_wip/builder-m2/real_final.log (+ per-slug folders).
- Unit tests exist for all 5 stages (all pass); docs/contract/decisions/M2.md written.
- Gate run #1 (out/_wip/builder-m2/gate.log, 17:57) FAILED only on external causes: tests/unit/contract
  test_stub_files_are_stubs asserts rhythm is a stub (not ours -> CR), ruff errors in tests/unit/vocals + voices
  (other modules), e2e: stem_activity (M1/M3a) KeyError 'min_present_drum_s' so choreo/cues pending in run 1 ->
  determinism diff meaningless.

## Next
1. Gate run #2 started 21:05 in background -> out/_wip/builder-m2/gate2.log (-KeepTemp). Check our files' determinism.
2. Write report docs/build/reports/builder-m2.md; return structured summary.
- 21:15 added tests/unit/rhythm/test_real_songs.py (-m real, 4 songs, chain rhythm->cues, snapshot tolerances);
  running in background -> out/_wip/builder-m2/real_test.log.
- 22:00 real test run #1 failed only on a test bug (arbitration key is `rows`); outputs kept in
  out/_wip/builder-m2/realtest/{0..3} (megafauna, versatile, jeremy, newton); assertions refactored into
  check_chain(root, slug) and PASS on all 4 kept runs (identical to the own-allin1 results).
- 22:40 gate2: unit FAIL (external CR M2-5 only), ruff/contract/validate/e2e/lib-node PASS. Full-pipeline synth:
  rhythm perfect; structure weaker than unit tests (the fixture allin1 stub encodes the truth; real allin1 on the
  synth finds 2 segments): boundary F 0.62, false drop at bar 5. Fixes: structure `drop_context_bars` 2 (jump vs
  the 2 bars before; kills the false drop, real-song roles unchanged) and `merge_repeat_max_bars` 8 (adjacent
  same-group sections merge up to 8 bars). Debug copy of the gate song: out/_wip/builder-m2/gate_song (+_intermediate
  layout so FixtureCtx can read it); scratch sims in scratchpad m2_sim.py. Real chain re-run -> real_final2.log.
  gate2 determinism is invalid for M2 (structure edited mid-run) -> need gate3 after.
- 23:55 gate3 done: fails only on external causes (contract stub test, ruff in tests/review/M4, determinism of
  separation-derived files); no M2 file differs between runs. Report final. Remaining: structured return only.
- Report draft written: docs/build/reports/builder-m2.md (fill in gate2 result).
- 21:20 rhythm: new QA flag `tempo_trackers_disagree` + warning when tracker tempi are not octave-related (M2-D16).

## Commands that work
- Git Bash: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python -m tests.synth.m2.run_chain <slug|synth> --stages a,b --reuse`
- Background real runs: `out/_wip/builder-m2/run_real.sh <stages> <slugs...> > out/_wip/builder-m2/real1.log`
- Scratch scripts: C:/Users/OPENSR~1/AppData/Local/Temp/claude/.../scratchpad/m2/ (score2.py, cmp_choreo.py, cmp_cues.py, dbg_*.py)

## Gotchas
- Real fixtures lack dynamics, drums, stem_activity, choreo, cues; spectral partial (no hit/onset events): every stage
  degrades gracefully (own HPSS drums, own chroma, own intensity) and flags it.
- moments.d is required-nullable in the catalogue but the events envelope requires a number when d exists -> write 0.0 (CR M2-1).
- Heavy slots are often both held by other agents: real runs wait.
