# fixer-m3a progress
- DONE F3: mono/dual-mono input -> karaoke skipped (worker param skip_steps), lead:=vocals, backing silent, lead_backing_split=false, flag sep:lead_backing_mono (fit.is_mono, separate_hq).
- DONE F1 (drumsep path): core.drumsep_hits: air-band detector for hihat stem, pre-echo drop, click bleed, cymbal relabel from hihat shape, ride twin, cymbal leak gates, tom gate. Scores on reviewer sep stems (out/_wip/r-ml-m3a/synth): kick 1, snare .99, hat .918, tom .857, cymbal .77. Script: out/_wip/fixer-m3a/score.py
- TODO F2 classifier path (core.classify) -> meet gates or emit only kick/snare + low conf; minor m6/m7/m1/m4; tests; gate.
- DONE F2 partial: classify: tom rule (tonal), air-band events, template-excess for lone kick/snare strokes; measured on generator drums: kick .977 snare .967 tom 1.0 hat .79 cymbal .44 (hat/cymbal gates NOT reachable: hats masked under snare tails, rides under strokes). Stage marks hat/cymbal low confidence (CLASSIFIER_RELIABLE).
- DONE minors: m6 variant_order validation + worker thresholds honoured, m7 gain polarity, m4 conf*vel factor.
- Unit tests updated (tests/unit/drums, tests/unit/separate_hq).
- NEXT: run gate (log out/_wip/fixer-m3a/gate.log), real e2e newton + 1 song, write report docs/build/reports/fixer-m3a.md, decisions M3a.md addendum.
- DONE: gate run (see report), real e2e newton+jeremy, report written.
