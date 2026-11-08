# r-ml-m3b progress (R-ML review of M3b notes / vocals / instruments)

## Done
- read PLAN, SPIKE, CONTRACT, spike main + bench-music, all M3b stage code

## Next
- check runner ctx.audio / threads / provenance, library sources (basic-pitch, rmvpe-onnx, swift-f0, CLAP tokenizer)
- run stages on synth + real fixtures; write failing tests for majors

## Gotchas
- CONFIRMED (major) CLAP text: Xenova text ONNX has only input_ids; Clap.text batches with padding -> pad tokens attended.
  cos(batch, alone) 0.84 for "a deep synth bass line"; synth sub-type shares flip (saw pad: batch .51/.49 pad/lead, alone .004/.996).
  probe: scratchpad clap_pad.py
- full synth analyze started -> out/_wip/r-ml-m3b/synth (log synth.log); other modules are real now (slow, heavy-slot waits)
- review tests pattern: see tests/review/M4/r-ml (marker 'real' registered, NOT skipped; heavy slot inside)
- synth e2e (real upstream stages now): bass F1 .858, piano 0 notes (gate: stem active 0.079 < 0.10 of song) ; with
  --param notes.piano_min_active=0.02 -> 25 notes, P .72 (18 correct) => MAJOR (song-fraction activity floor drops short piano parts, also blocks basic-pitch fallback)
- builder fixture cache (truth stems): bass .907 piano .985 vocals range G3-A4 ok
- real runs (FixtureCtx on out/_wip/builder-m3b/fx/<slug>) -> out/_wip/r-ml-m3b/real/<slug>/<stage>; log realrun.log
  jeremy range E3-C#5 (C#5 longest note 0.18 s, conf .45 -> minor: sustained criterion), register tenor (minor)
  megafauna lead_vocals silent in overlay -> present false; vocal_style dominant 'speech' from 7 s voice (minor)
- RMVPE gain-robust to -40 dB; level gate floor -55 dBFS absolute (minor). SwiftF0 +0.008 offset wrong (lib ts are centres; minor)
- CED output verified probability (single output 'logits' in 0..1)
- WROTE tests/review/M3b/r-ml/{conftest.py, m3b_fakectx.py, test_clap_text_padding.py, test_notes_short_piano_part.py}; all 3 fail for the stated reason
- WROTE docs/review/M3b-r-ml.md (minors m1-m9)
- edge runs (mono_44k, stereo_48k) started -> out/_wip/r-ml-m3b/edge/<case>, log edge.log (slow)
## Next
- finish edge check, run ruff on review tests, write docs/build/reports/r-ml-m3b.md, StructuredOutput
- re-confirmed 3 review tests fail; piano test passes when piano_min_active=0.02 (CRNN runs, 8/8) -> fixable
- mono_44k e2e: no voice, other notes 57/61 exact, ok
- WROTE docs/build/reports/r-ml-m3b.md
## Next
- stereo_48k e2e still running (optional check); then StructuredOutput
- stereo_48k e2e: no voice, other notes 57/61, instruments drums+synth_fx; same as mono
