# r-ml-m3a-r2: R-ML review of M3a Separation, round 2

Reviewer: r-ml-m3a-r2 (lens R-ML), 2026-11-09. Verdict: **fail** (5 majors: 2 re-opened, 3 new and caused by the fix
round's drum rules). No lyric text appears anywhere. Minors are in `docs/review/M3a-r-ml.md` under "Round 2".

## What I ran
- Fresh ROCm end-to-end run of the synthetic song (`--only ingest,separate_fast,separate_hq,stem_activity,drums`):
  `out/_wip/r-ml-m3a-r2/synth`. The same song resampled to 48 kHz: `out/_wip/r-ml-m3a-r2/synth48`.
- `ingest,separate_hq` on the 17-29 s synthetic excerpt with its side scaled to -24 dB and -18 dB under mid:
  `out/_wip/r-ml-m3a-r2/narrow24`, `narrow18`.
- Probes of `drums.core.drumsep_hits` on the generator's clean sub-stems (`scripts/dyn_probe.py`, `dark_probe.py`,
  `route_probe.py`), sample-rate cross-checks (`sr_cross.py`, `miss48.py`), real runs of the fixer (jeremy, newton).
- Review tests: 3 of the 4 round-1 tests pass; the F2 test still fails. Module unit tests: 42 passed, 10 skipped.

## Round-1 findings
| id | status | evidence |
|---|---|---|
| F1 drums on separated stems | fixed at 44.1 kHz, but it does not generalise | fresh run: kick 1.000, snare 0.993, hat 0.918, tom 0.857, cymbal 0.769 (the same as the fixer's numbers); crashes are cymbals. See N1-N3. |
| F2 classifier path | **not fixed** (re-reported) | hat 0.793, cymbal 0.444. The conf cap of 0.45 is invisible to the choreo and cues packs (`t, drum, vel`) and to the `drums.*` curves. |
| F3 karaoke on mono | fixed for exact mono only (**re-opened**) | side -24 dB (correlation 0.992): lead -11.1 dB, backing -6.3 dB, split true, no flag. |

## Majors (each has a failing test)
1. **F2** `tests/review/M3a/r-ml/test_drums_classifier_path.py`: the classifier path is still below the PLAN §7 gates
   (hat 0.793, cymbal 0.444). Its low-confidence marking lives in `conf`, `evidence` and `summary`, which the
   consumers do not read.
2. **F3-R** `test_r2_karaoke_near_mono.py`: the `is_mono` cliff is at -30 dB. A near-mono master at -24 dB inverts
   the split silently (lead SDR 2.08 dB, vs 8.31 dB in stereo). No "backing louder than lead" sanity flag exists. In
   real stereo songs backing sits 9-22 dB under lead.
3. **N1** `test_r2_drums_soft_passage.py`: the new `cym_gate_db=12` is song-wide. A passage played 13 dB softer loses
   every cymbal (0/9), even on clean sub-stems. Kick, snare and hat survive down to 20+ dB.
4. **N2** `test_r2_drums_dark_hihat.py`: the hi-hat to cymbal relabel uses an absolute brightness of 11 dB. The
   synthetic hats measure 18.5 dB, but the real hi-hat stems measure 10.45 dB (newton) and 4.93 dB (jeremy: 138 hits
   relabelled, 210 dropped). When the clean hi-hat stem is darkened to ~5 dB, all 32 open hats become cymbals and 32
   hats are dropped (hat F1 0.783).
5. **N3** `test_r2_drums_separated_synth_48k.py`: the same song at 48 kHz scores tom 0.545 and cymbal 0.514. The
   detector does not depend on the sample rate; the cause is the DrumSep output, which changes between the two runs.
   The 44.1 kHz pass rests on 1-2 hits per class.

Re-run the slow tests cheaply with `MVH_REVIEW_M3A_SYNTH48=out/_wip/r-ml-m3a-r2/synth48` and
`MVH_REVIEW_M3A_NARROW=out/_wip/r-ml-m3a-r2/narrow24` (or let the fixtures run: ~2 min and ~4 min on ROCm).

## What holds
- separate_hq invariants on the fresh run: sum -35.3 dB, gains within 0.03 dB on the gated stems, exactness -150 dB.
  The 48 kHz run gives the same invariants (-35.1 dB).
- The mono path (skip karaoke, `lead := vocals`, silent backing, flag and fallback tag) is clean.
- `variant_order` is validated. The normalisation and amplification params are honoured. `gain_gate` fails w <= 0.
- The ROCm run is reproducible: the fresh synthetic run gives drum F1 identical to the fixer's run on my round-1 stems.
