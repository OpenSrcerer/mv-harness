# fixer-m3a-r2 report (M3a Separation, fix round 2)

## Findings and fixes
- **N1 (cymbal / tom leak gates were song-wide)** fixed in `drums.core.drumsep_hits`: gates are now relative to the kit's own level
  at the instant (kick / snare stroke at the same instant, else the loudest within +-0.75 s), against the 2nd loudest such
  value of the ride + crash stems (3rd for toms). The `weak` bleed rule for ride / crash / tom uses the same local value. A hit
  is a leak only when it is far under the kit AND (tight tier) under the song's own strokes (8 dB). Kit -13 dB in 16.9-20.95 s:
  cymbal recall 0.667 -> test passes (kick, snare, hat 1.0).
- **N2 (absolute brightness threshold)** fixed: the hat-stem relabel / snare-noise rules use `min(11, typ - 7.5)` and
  `min(0, typ - 18.5)` where `typ` is the stem's own typical brightness (median of its stronger half). Darkened hi-hat stem
  (typ ~5 dB): open hats kept, hat F1 >= 0.9, test passes.
- **N3 (48 kHz / run-to-run DrumSep variation)**: (a) ride / crash candidates carry a ring feature (`_ring`: 4-16 kHz over
  100-1000 Hz, and the drop to 150 ms later); a hit past the tight gate (down to 28 dB under the kit) is kept only when it
  rings AND the classifier on the full drum stem also finds a cymbal there; ringing hits are exempt from the hat-copy /
  hat-leak drops; a hat-stem hit at the instant of a kept ringing ride / crash stroke is that stroke's copy. (b) toms the
  classifier finds with no DrumSep tom (and no kick / snare within 25 ms) are added (`classifier_only`, conf <= 0.5).
  Fresh ROCm end-to-end runs (separate_hq re-run, not cache): 44.1 kHz kick 1.000 snare 0.993 hat 0.926 tom 1.000 cymbal
  0.800; 48 kHz kick 0.994 snare 0.980 hat 0.917 tom 0.889 cymbal 0.714 (gates 0.9 / 0.9 / 0.9 / 0.7 / 0.7). Both review
  tests pass. The 48 kHz cymbal margin is thin (0.014): DrumSep's ride stem fades over the 17-24.5 s ride passage and the
  ring / classifier cue is all that recovers it.
- **F3-R (near-mono karaoke)**: `separate_hq` now grades the width (`fit.side_to_mid_db`), flags `sep:lead_backing_suspect` when
  the backing is within 3 dB of the lead or above it, and on a narrow master (side <= 20 dB under mid) drops the split like the
  mono case (`lead := vocals`, silent backing, `lead_backing_split=false`, `sep:lead_backing_narrow`). Per-second lead share
  (`checks.lead_share_frames`) is the split's confidence (minor m8). Review test passes (narrow-24: backing +4.7 dB
  over lead -> split dropped).
- **F2 (classifier path hat / cymbal)**: mitigated, NOT passing. The review test calls `core.classify` directly and requires
  hat >= 0.9 and cymbal >= 0.7 on the clean mixed drum stem (measured 0.793 / 0.444); on one mixed stem hats under snare tails and
  rides under kick strokes are not separable (the ring probe measures -16 dB hf-over-lo at every kick instant). The reviewer's
  own suggested fix ("leave hat and cymbal out ... or scale them ... then update the review test") contradicts the test as
  written. Done: hat / cymbal `vel` x0.45 on that path with the raw value in `vel_raw` (the choreo / cues packs read `t, drum,
  vel` and the envelopes follow vel), fallback `drums:low_confidence(hat,cymbal)` next to `drums:classifier`.

## Real songs
newton-vs-nye end to end (ROCm, `out/_wip/fixer-m3a-r2/newton`): drums 200 kick, 371 snare, 796 hat, 34 tom (19 DrumSep + 15
classifier_only), 14 cymbal (69 before: the ring / confirm rule and the kit-relative gate are stricter on a
song whose strokes are loud; no truth exists to settle it), no separation flags. A first cut of the classifier-only toms
added 160 toms (143 were kick / snare transients): guarded.

## Gate
See open_issues: `tests/unit/contract::test_stub_files_are_stubs` fails because `mvh.stages.rhythm` (M1) is no longer a stub: not
M3a's file (frozen contract test), change request below.
