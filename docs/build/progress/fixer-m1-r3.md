# fixer-m1-r3 progress (W3 M1 fix round 1)
- Started. Read BUILD-STATUS, W2-gate, SEAMS S06, review tests (tests/review/M1/r-dsp/*), dsp.py select_kick_events.
- Plan: eval harness in scratchpad caching per-signal features; redesign kick selection from first principles; then
  unit tests, real-song reruns from integrator folders, gate, report.
- Baseline: 11 review fails (kicks). Eval harness in scratchpad (/c/Users/OPENSR~1/AppData/Local/Temp/claude/715de6aca1d90ae4/cfc48f00-d046-409f-8e46-ef42c153038f/scratchpad): cases.py (cached cases), evalk.py <module>,
  kick3.py (draft features), k3.py (draft rules). Reproduces old numbers exactly with k_old.py.
- S06 analysis: MEGAFAUNA DrumSep kick list is mostly hat bleed (32nd-note hats at 71 ms, kick-stem level ~-29 dB, coincident
  hat hits); the big ~100 Hz hits are labelled tom/snare by DrumSep. Integration test needs M3a bleed filter -> change request.
- New design (draft k3): candidates = peaks of low step / A-band (90-200) step / 1.5-5k click step; refine timing; NMS 20 ms on
  onset score; features: attack (A/A1 burst above pre and late), added-energy RMS-frequency glide (Glide class), click (1.5-5k),
  body (low_ex/K_ex/added power), viz gate max over +80 ms. Rule: gate & body>=1 & attack>=6 & (glide>=1.25 | click>=6 & attack>=10).
  Result: 23/24 synthetic cases pass; fixture F1 0.933 (R 0.906). Next: fixture misses, then port into dsp.py.
- Draft k4.py (scratch) = kick3.KickFeat + two routes: R1 sweep (attack A/A1 burst>=6 & glide>=1.25 | click>=6 & attack>=10),
  R2 body (K_ex>=7, body_add>=5, dK60>=8, low_ex>=2, fa1>=68 Hz: acoustic kicks, Jeremy) + gate + body + relative level
  (body_db >= median accepted - 12 dB: drops vocal plosives). Timing: refine on 0.5*ls + Ax (max-filtered A step) + 0.5*cs.
  Glide = RMS freq (derivative power) of energy added vs pre (-30..-8 ms), at most half the window subtracted, band 30-160 Hz.
  Synthetic: all 24 review cases pass (fixture F1 0.977); extras 19/20 (gbpm140 0.947). Real vs DrumSep (est->drum / drum->est):
  jeremy .91/.78 (old .82/.76), versatile .98/.77 (old .58/.85), newton .99/.96, synth .97/.99. Jeremy stem recall .941 (old .973).
  NEXT: port into dsp.py select_kick_events replacement + stage.py, unit tests, gate.
- PORTED into src/mvh/stages/spectral/dsp.py (KickAnalysis, GlideMeter, KickEvidence, kick_route, select_kick_events,
  low_band_envelopes, max_step; old kick helpers removed), stage.py (kick path, kick_conf = KickEvidence.conf(), summary routes),
  __init__.py (new kick_* params, version 1.1.0). Scratch k_new.py reproduces the draft. Next: review + unit tests, fix unit
  tests that use removed helpers, gate.
- review M1: all pass (viz flag = episode-overlap semantics). Next unit tests.
- unit spectral 42 pass (new: sub-bass x6, riffs/rolls x8, GlideMeter, max_step; real test now vs kick stem). Running real tests in bg: out/_wip/fixer-m1-r3/real_tests.log
- real tests: 4/4 pass (unit kick-stem x3 + review jeremy). Launched rerun: out/_wip/fixer-m1-r3/rerun.ps1 (log rerun.done.log)
- decisions M1.md updated (M1-S5/S8 revised, M1-S12 kick events, M1-S13 precedence, CR-M1-4 M3a bleed, CR-M1-5 no fusion). Rerun running (threads 3 needed for cache hits; rhythm included in --only since dynamics depends on it).
- gate M1 started in bg: out/_wip/fixer-m1-r3/gate.log
- dsp docstring updated. Waiting on gate (contract unit tests fail: integrator's vocals deps + gen artifacts, not M1) and rerun (rhythm waits for heavy slot). Then write report.
- rerun synth/newton/versatile done: hits.kick agreement up, dynamics parts/roles/impacts/loudness identical. gate: unit FAIL only contract (integrator), review PASS, ruff FAIL (vocals), contract gen FAIL (CONTRACT.md), validate PASS; e2e running. Report draft written.
- all reruns done. megafauna dynamics drop hints 3->2 (28.7 lost; 96.1, 141.8 kept; the 28.7 hit has glide 1.23 < 1.25); jeremy +2 parts, outro breakdown hints. Waiting gate e2e/determinism.
- DONE: gate rc=1 only from non-M1 (contract unit tests / CONTRACT.md gen); all M1 steps + review + determinism PASS. Report written.
