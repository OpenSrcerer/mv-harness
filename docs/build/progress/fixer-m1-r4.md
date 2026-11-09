# fixer-m1-r4 progress (W3 M1 fix round 2)
- Started. Inputs: docs/build/reports/r-dsp-m1-r4.md (R4-M1 kick designs over held bass, R4-M2 sidechain duck = S06,
  R4-M3 quiet section rel_db global; minors m20-m24), tests/review/M1/r-dsp/test_rdsp_r4_kicks.py, tests/integration/M1.
- Scratch harness: <scratchpad>/m1r4/ (copied from fixer-m1-r3 cases.py/evalk.py, extended with r4 cases).
- Harness (scratch m1r4): cases.py (+R4 cases r4s_/r4d_/r4q_/r4f_), evalk.py <mod> [NAMES|EXTRA|R4|names], featdump.py + ana.py +
  ruleeval.py (fast rule eval on dumped features), realk.py <mod> (real songs vs DrumSep kick rows, all / strong vel>=0.5),
  run.sh / run1.sh (env wrappers). Baseline reproduced (acoustic .588, 808 .551, duck .667/0/.118, quiet .857).
- m23 FIXED: dynamics role_score clipped to 1 after ranking (stage.py).
- Draft kick5.py: new routes "duck" (attack>=4.5, click>=15, glide or raw glide>=1.6, no adds needed), "click" (acoustic:
  click>=15, attack>=3.5, low_ex>=3, body_ex>=4.5, body_add>=3), "808" (glide>=1.15, attack>=3, body_ex>=5.5, body_add>=5,
  low_ex>=2.5); two-sided local +-8 s body reference (min of medians, >=4 events per side, else global); fine timing window
  extended to +25 ms (earliest local max >= 0.6 x window max) -> fixes 808 21 ms-early events. Precise LP-energy onset timer
  tried: worse (+-10 ms), dropped. Result: all NAMES/EXTRA pass, all 6 r4 review signals pass in harness.
- Final design (in kick5.py, then PORTED to src/mvh/stages/spectral/dsp.py + __init__ params + stage.py summary, version
  1.2.0): routes sweep/duck/body/click/808 + iterative "roll" (burst>=12 dB, glide>=1.1, 40-150 ms after an accepted kick;
  fixes m21 fixture-kick 16ths@180 under crash); NMS priority = score + 0.5*ls (a hat click 21 ms early no longer times
  an 808); faint-thump filter = body_db minus local mix level (quieter of RMS 1.5 s before/after) vs median - 12 dB
  (R4-M3: quiet intro/fade kept); pad_s 0.1 of zeros (m20); dedupe by kick_conf; KickEvidence.glide_raw; conf() + clicky.
  Harness: NAMES/R4 required/EXTRA all pass except pre-existing gbpm140 (.940, baseline .947) and my own harder extras
  (subthump/bass .7/duck without click+glide). Real vs DrumSep (est->drum/drum->est): synth .98/.99, newton .98/.98,
  versatile .94/.89 (base .97/.88), megafauna .47/.15 (base .49/.14), jeremy .91/.79 (base .90/.79).
- S06 analysis: at MEGAFAUNA strong DrumSep kicks the MIX low band does not rise (median body -1..-2 dB; per-kick dips of
  -13..-19 dB from -10..+20 ms): no mix-only evidence -> CR (fusion in consumer / M3a bleed filter / test on strong rows).
- NEXT: run review M1 + unit spectral tests, update unit tests, decisions M1.md, reruns, gate, report.
- PORT revised (after real-song checks): NMS priority = (own <=400 Hz or 90-200 Hz step >= 2 dB, score) lexicographic;
  dedupe by onset score (dedupe by kick_conf / primary route moved Versatile kicks 20 ms early: early pre-ring anchors
  read stronger); faint filter = mix-relative (R4-M3) AND (body within 12 dB of song median kick OR kick_conf >= 0.7)
  (Versatile intro non-kicks). Harness: all NAMES/R4-required/EXTRA incl gbpm140 + d16f_180_crash pass. Real:
  synth .98/.99, newton .98/.98, versatile .96/.88, megafauna .49/.15, jeremy .90/.79 (= baseline within .01).
  Params in __init__: kick_duck_click_db, kick_cb_*, kick_s808_*, kick_roll_*, kick_quiet_conf, kick_level_win_s,
  kick_nms_low_step_db, kick_pad_s. NEXT: pytest review+unit, new unit tests, decisions, reruns, gate.
- Tried + reverted: power-step (no-Hilbert) fine timing and forward climb (no effect); NMS on power step (worse).
- Unit tests added: tests/synth/m1/kicks.py (independent kick designs/mixes); test_spectral.py
  test_kick_designs_and_mix_situations x10, test_clickless_808_over_a_held_bass_note (xfail strict: known limit),
  test_kick_on_the_first_sample, test_kick_routes_and_conf_are_reported; test_dynamics role_score <= 1. All pass.
- NEXT: decisions M1.md, real reruns (out/_wip/fixer-m1-r4/<slug>), gate, report.
- decisions M1.md updated (M1-S12/S13 revised, M1-D10, CR-M1-4 revised, CR-M1-5 superseded, CR-M1-6 fused kick). Reruns launched: out/_wip/fixer-m1-r4/rerun.ps1 (rerun.done.log).
- gate launched in bg: out/_wip/fixer-m1-r4/gate.log (unit contract tests fail: vocals deps gained 'lyrics' at 08:41 by another agent -> CONTRACT.md generated region stale; not M1). cmp script: out/_wip/fixer-m1-r4/cmp.py
- report draft written (docs/build/reports/fixer-m1-r4.md, results placeholder). Waiting on reruns + gate.
- reruns done (cmp.log): kick agreement up on all songs vs integrator; loudness identical; mid/high identical; dynamics same boundaries synth/newton/versatile, megafauna 11->12 parts (28.7 drop hint lost), jeremy 10->13 (outro breakdown hints); impacts same strength, a few t shifts. kicks.py import order fixed (ruff). Waiting gate e2e/determinism.
- DONE: gate rc=1 (unit contract, ruff determinism.py, contract gen, determinism of separation stems: none M1; M1 unit/review PASS, e2e PASS). Report written docs/build/reports/fixer-m1-r4.md.
