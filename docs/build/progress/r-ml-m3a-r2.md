# r-ml-m3a-r2 progress (round 2 R-ML reviewer of M3a)

## Done
- started; read round-1 progress/review + fixer report (F1/F3 claimed fixed, F2 partial)

## Next
- inspect fixer code (drums/core.py, separate_hq, sep/fit.py, hq_worker); rerun review tests; fresh e2e synth run; probe regressions

## Milestone 1 (probes on oracle sub-stems, scripts in out/_wip/r-ml-m3a-r2/scripts)
- runs.sh (bg): fresh synth 44.1k e2e -> out/_wip/r-ml-m3a-r2/synth, 48k full song -> synth48 (log runs.log)
- dyn_probe.py: kit 13 dB softer in 17-21 s -> all 9 cymbals there dropped (cym_gate_db=12 vs stem's 2nd loudest), kick/snare/hat fine to 20 dB -> NEW MAJOR
- dark_probe.py: hihat stem brightness ~5 dB (= jeremy's measured typical 4.93) -> all 32 open hats relabelled cymbal, 32 hats dropped weak_dull (absolute cym_bright_db=11) -> NEW MAJOR
- real counts: jeremy relabelled_cymbal 138, weak_dull 210, typ_bright 4.93; newton 52 relabelled, typ 10.45

## Milestone 2 (runs done)
- fresh synth 44.1k: kick 1 snare .993 hat .918 tom .857 cym .769 (= fixer) -> F1 test passes
- synth48 (same song at 48k): hat .908 tom .545 cym .514; detector is sr-robust (sr_cross.py), the separation differs (ride stem -2.8 dB) -> F1 fragile: NEW MAJOR (48k)
- narrow24 (side/mid -24 dB, corr .992, is_mono False): lead -11.1 backing -6.3 dB, SDR 2.08, split true, no flag -> F3 not fully fixed (MAJOR)
- narrow18: lead -8.2 backing -8.0, SDR 4.28
- F2: test still fails (hat .793 cym .444); mitigation conf<=0.45 invisible to choreo/cues packs (project t,drum,vel; curves drums.*) -> re-report major
- next: write tests (cymbal gate dyn, dark hat, 48k, near-mono), run review dir, write docs

## Milestone 3 (tests written, verified failing)
- tests/review/M3a/r-ml/test_r2_drums_soft_passage.py (N1), test_r2_drums_dark_hihat.py (N2), test_r2_drums_separated_synth_48k.py (N3, fixture synth48_e2e),
  test_r2_karaoke_near_mono.py (F3 reopen, fixture synth_narrow_e2e; verified fresh: fails 103 s). conftest/util extended. ruff clean.
- F2 existing test still fails. Old F1/F3 tests pass.
- docs/review/M3a-r-ml.md Round 2 section written (r2-m1..m3)
- next: confirm 48k fixture fresh run (bg, out/_wip/r-ml-m3a-r2/t48.log), write report, StructuredOutput

## DONE
- 48k fixture verified fresh (fails identically, 147 s). Report docs/build/reports/r-ml-m3a-r2.md written. Only StructuredOutput left.
