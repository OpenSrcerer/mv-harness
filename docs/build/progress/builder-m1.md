# builder-m1 progress (M1 Signal: spectral, loudness, dynamics)

## Status
- [x] read PLAN, SPIKE, CONTRACT, catalog, runner spec/ctx, spike main/bench-music, proto.py/seg.py, viz/js/audio.js
- [ ] spectral: dsp.py + stage.py + tests
- [ ] loudness: r128.py + stage.py + tests
- [ ] dynamics: stage.py + tests
- [ ] real songs x4 + synth runs, report, gate

## Commands that work
- Git Bash: `export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>` (cwd = repo)
- `python` is NOT on the Git Bash PATH; always go through scripts/run.ps1.

## Design notes (decided)
- Band dB "dBFS" = 10*log10(mean square) like the fixture (full-scale sine = -3.01 dBFS); physical bands use mid+side power
  (= mean over L/R), viz values use the mid (AnalyserNode downmix) with |X|/N Blackman (Web Audio periodic window).
- Hit events: viz attack-episode semantics (attackV > 0.3 while armed), offline ref = centred +-8 s median of attack peaks,
  kick gate max(-46, p95 - 30); t refined on a 400 Hz zero-phase (Hilbert) band envelope; envelopes shifted by the median
  detection lag, flash rule applied, released curve recomputed from the raw one.
- dynamics cannot read allin1 (not a dep): code path guarded with try/except UndeclaredDependency + CR; bar-grid fallback.

## Gotchas

## Milestone 1 (spectral + loudness first versions run on synth)
- spectral: src/mvh/stages/spectral/{__init__,dsp,stage}.py done; synth song 3 s. Kick events: drums stem F1 1.0 @10 ms,
  groove w/o bass 1.0, full synth mix recall 0.93 @10 ms (precision 0.43: bass notes are kick-band hits, kick_conf field).
- refinement = step contrast of 400 Hz dB envelopes (low band k=4 + 0.5 x click >=1 kHz k=2); plain steepest-diff fails in mixes.
- loudness: src/mvh/stages/loudness/{__init__,r128,stage}.py; synth matches truth (-20.376 LUFS, LRA 7.165), ebur128 diff -0.08.
- run: `mvh analyze out/_wip/builder-m1/synth --only <stage> --force <stage> --no-network` (first a full analyze to cache deps)

## Milestone 2 (dynamics first full version; all songs run through tests/synth/m1/harness.py)
- dynamics: src/mvh/stages/dynamics/{__init__,detect,segment,stage}.py. Harness: `python -m tests.synth.m1.harness
  <canonical.wav> <bars.json> out/_wip/builder-m1/harness/<slug>` (FakeCtx, real StageWriter; no runner needed).
- Fixed: Foote sign (novelty was all zero), silence frames held in features, features clipped +-3.
- Segmentation = global novelty peaks + local splits of >30 s parts + agglomerative same-level merge to ~1 part/20 s;
  major impacts (after silence or score >= 0.5 x max) are unmergeable boundaries. Levels scaled by clip(range/8,0.5,1).
- Real songs: MEGAFAUNA drops hinted at 96.1 (after silence) and 141.6 (+48 dB bass); Versatile major impacts 51.0, 84.0,
  162.0; Jeremy 10 parts (verse/chorus at 40.1/76.5/113.0); newton 9 parts. ebur128 diffs -0.01..-0.08 LU.
- scratch scripts: $SCRATCH/realrun2.sh (all songs), evdyn.py, evimp.py

## Milestone 3 (spectral unit tests green: tests/unit/spectral/test_spectral.py + viz_parity.cjs)
- viz parity runs the REAL viz/js/audio.js in node (vm sandbox, stub analyser): band map, bandsRaw, eKick,
  _hitEnvelope (causal path), _flux all match. Per-bin dB floor changed to -1000 (viz floors only the band at -200).
- Weak kick-band hits need kick_conf >= 0.75 (Versatile had 727 weak bass-line hits). viz-strength counts vs W0 ref:
  megafauna 488/464, versatile 211/208, jeremy 622/617, newton 205/199.
- GOTCHA: tests.synth.dsp one-shots are truncated (kick 0.45 s at -20 dB) -> broadband click -> spurious flux onsets
  ~40 ms before the next kick. tests/synth/m1/signals.py fades them (150 ms raised cosine). The contract synth fixture
  has the same artefact (report it to the fixtures owner).

## Milestone 4 (all unit tests green incl. real; decisions doc; gate running)
- tests: tests/unit/{spectral,loudness,dynamics}/ (31+24+17 incl. 12 real, opt-in MVH_REAL_TESTS=1). All pass.
- docs/contract/decisions/M1.md written (M1-S*, M1-L*, M1-D*, CR-M1-1..3).
- dynamics extra: decay tails (strength>=0.5, d>=2 s) and major impacts are unmergeable part boundaries; silence
  threshold floored at -69.5 LUFS (all-silent song); silence_min_s 0.5.
- Runner e2e on synth: spectral+loudness ran via `mvh analyze ... --only`, validate 0 errors. dynamics via runner needs
  rhythm current -> chain separate_fast,allin1,rhythm,dynamics queued for a heavy slot (other modules hold them).
- gate: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate.ps1 M1` (log in scratchpad gate.log)
- NEXT: wait gate + chain, write docs/build/reports/builder-m1.md, return.

## Milestone 5 (resumed 21:02; report already written at 17:26)
- gate.log (17:51) was cut off during e2e: unit FAIL only in tests/unit/contract stub test (rhythm not a stub, not M1),
  ruff FAIL only in tests/unit/vocals + tests/unit/voices (not M1). M1 paths: ruff clean.
- Re-running gate -> scratchpad gate5.log. NEXT: add the gate result section to the report and return.
- gate5 (21:03-): unit FAIL only contract stub test (spectral 27+4s, loudness 20+4s, dynamics 13+4s pass), ruff PASS,
  contract PASS, validate PASS, e2e PASS (1616 s, real pipeline; spectral 3.0 s, loudness 2.8 s, dynamics 2.6 s), lib-node PASS.
  determinism running.
- gate5 done: determinism FAIL 36/179 files, none M1 (M1 stages twice -> byte-identical, checked by md5 in the wip folder).
  Report has the Gate section. DONE.
