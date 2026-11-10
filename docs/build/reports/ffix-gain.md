# ffix-gain report: stem and onset events independent of the master level

The fix covers W4V2-GAIN-DRUMS, STEMACT, VOCALS and SPECTRAL. Decisions F-gain-1 to F-gain-6 are in
docs/contract/decisions/F-gain.md.

## What changed

| Area | Change |
|---|---|
| `src/mvh/sep/level.py` (new) | A BS.1770-4 loudness measure built on numpy and scipy, because the sep env has no pyloudnorm. It is within 0.1 dB of the loudness stage, and a pure gain shifts it exactly. |
| `src/mvh/sep/hq_worker.py` | DrumSep runs on the SW drum stem scaled to the mix's -10 LUFS analysis level. The sub-stems are then scaled back by the inverse gain. New param `drumsep_analysis_lufs`; the summary records `settings.drumsep_analysis_level`. |
| drums 1.4.0 | Stems are scaled by the mix gain before every gate. `level_db` is reported back in stem dBFS. A crash-shaped hat-stem stroke now goes to the cymbal relabel instead of being dropped as dull bleed (F-gain-2b). |
| stem_activity 1.1.0 | The -45 dB `active_db` applies at the analysis level, so the effective threshold is `-45 - gain_db` dBFS. `thresholds.active_db` holds the effective dBFS value; new fields: `active_db_at_analysis_level` and `analysis_level`. |
| vocals 1.3.1 | The lead stem is scaled by the mix gain before RMVPE, SwiftF0, CED and the -55 dB gate. `vocal_phrases.mean_db` is reported back in dBFS. |
| instruments 1.1.1 (`lead.py`) | The karaoke-rescue rule now compares lead and vocals energy over the vocals stem's loudest 10 % of frames. The old rule took a p95 over non-silent frames and flipped when FLAC quantisation zeroed bleed. |
| spectral 1.5.0 | `hits.mid`, `hits.high` and `onsets.*` are picked on a second pass at the analysis level. Curves stay absolute. `hits.kick` stays at the master level, because raising the level puts a quiet a cappella's formants through the -46 dB gate. |

Every stage has an `analysis_lufs` param (default -10; `null` gives the old behaviour).

## Proof

The runs are in `out/_wip/ffix-gain/<name>`: copies of the existing W4 folders, re-analysed with `--force separate_hq`.
`cmp_gain.py` runs the 4 W4V2 gain tests on each pair.

- **synth -12 dB:** 4/4 pass. The restored DrumSep sub-stems match at 62-81 dB SDR (before: 11-47 dB).
- **MEGAFAUNA -12 dB and -20 dB:** drums (agent kick and strong hits), stem activity and spectral pass. Vocal notes:
  onset F 0.885 and 0.903 (before: 0.375 and 0.244). Phrase IoU is 0.788 on both copies, a fail.
  - The cause is upstream: the lyrics stage (M5) aligns the first lines (106-116 s) differently at -12 dB.
  - With the base lyrics swapped in (`swap_lyrics.py`), vocals on the -12 dB copy gives phrase IoU 1.000 and note F 1.000.
  - This is CR-F-gain-2.
- **Versatile -12 dB:** 4/4 pass. Before this fix, all four tests failed on this pair.

## Tests and gates

- Owned unit tests pass. Tests added or changed:
  - `tests/unit/drums/test_gain_invariance.py` (new);
  - `tests/unit/spectral/test_spectral.py::test_events_do_not_follow_the_master_level` (new);
  - the onset test is now parametrised over native and analysis level. At the analysis level the high-band recall bar is
    0.6, because the viz dB map compresses flux on louder input: 0.77 -> 0.64 on the -16 LUFS groove.
- Gates with `-SkipE2E`:
  - M1: PASSED.
  - M3b: PASSED.
  - M3a: FAILED in review on one test only, the 48 kHz synthetic cymbal F1 (0.686 against a 0.7 gate; 6 quiet rides under snares). Unit, ruff, contract and validate pass, and the 44.1 kHz crash test now passes.

## Change requests and open issues

- **CR-F-gain-1:** bump separate_hq to 1.1.0. The cache key has no code hash, so old caches keep the master-level DrumSep stems.
- **CR-F-gain-2:** the lyrics aligner should run at the analysis level and adopt `loud_frame_gap_db`.
- **48 kHz synthetic rides:** see the known residual in F-gain.md.

## Test tracks

No downloads were needed. The existing real gain copies covered the fix.
