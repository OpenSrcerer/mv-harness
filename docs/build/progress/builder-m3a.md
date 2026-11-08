# builder-m3a progress (M3a Separation)

## Done
- read PLAN, SPIKE, CONTRACT, spike/main.md, spike/sep.md, runner spec/ctx/sepworker/worker

## Next
- explore fixtures (synth truth drums, real sep caches)
- implement stem_activity, drums, separate_fast, separate_hq (+ worker), models_lock schema fix

## Commands that worked

## Gotchas

## Milestone 1 (stem_activity + schema fix)
- models_lock schema fixed in src/mvh/contract/catalog.py (envs enum + optional schema/generated_by/models_dir/bundled/note(s)/source); gen + gen --check + tests/unit/contract green.
- stem_activity implemented (core.py + __init__.py). Real runs with stubbed upstream: vocals conf (htdemucs+SW agreement):
  megafauna 0.30 (unconfirmed), versatile 0.70, jeremy 0.99, newton 0.99.
- Dev helper: scratchpad an.ps1 <slug> <song> <only>  (sets MVH_FIXTURE_DIR=real-<slug>, out\_wip\builder-m3a\<slug>)
- Gotcha: python -c through powershell mangles quotes; write scripts to scratch files.

## Milestone 2 (drums)
- drums core.py + __init__.py done. Synth generator sub-stems (DrumSep path) F1@10ms: kick .977 snare 1 hat 1 tom .80 cymbal 1.
  Classifier path on generator drum stem: kick .954 snare .861 hat .777 tom .27 cymbal 0 (weak; fallback only).
- Real (W0 DrumSep stems, stubbed upstream): megafauna 2612 hits, jeremy 2585 hits; plausible rates after per-stem
  ODF-spread threshold, level-track bleed check, cymbal rise floor 4 dB.
- Scratch dev scripts: score_drums.py, drums_report.py, miss_cls.py (scratchpad).
- Gotcha: an.ps1 must be called with named params (-Slug -Song -Only -Extra "--force") or --force is lost.
- Gotcha: stage cache key does not include code: use --force after code edits.

## Milestone 3 (separate_fast, separate_hq code; tests)
- separate_fast real (mvh.sep.demucs, array route); newton fast stems within -49..-65 dB of W0's. ~280 s incl. slot wait.
- separate_hq: mvh.sep.hq_worker (worker side), stages/separate_hq/worker.py shim, stage builds stems + invariants.
  First synth run started (worker waits on heavy slots held by other agents).
- tests: tests/synth/m3a (run_stage harness via mvh.runner.child.run_stage), tests/unit/{stem_activity,drums}
  pass (real-marked tests skipped unless -m real / MVH_RUN_REAL=1 via conftest).
- stem_activity: split stems (drums_*, lead/backing) judged against their parent stem (decision M3a).

## Milestone 4 (tests + decisions)
- tests/unit/{separate_fast,separate_hq} written (fake worker + fake audio_separator); all M3a unit tests pass; ruff clean on owned paths.
- docs/contract/decisions/M3a.md written (M3a-1..13 + models_lock schema note).
- Real batch: scratchpad all_real.ps1 (-Slugs, -Stages, -Extra) -> logs all_real_sep.log. Started separate_fast,separate_hq on 4 songs (background).
- Heavy slots are heavily contended by other agents (waits of 10+ min per model are normal).

## Next
- verify synth separate_hq real output + determinism (run twice, compare stems hashes)
- stem_activity + drums on all songs with real upstream; report; gate.

## Milestone 5 (real separation on synth; drums tuned for separated stems)
- synth separate_hq real ROCm: sum -35.3 dB, gains pass, inst+voc/lead+back exact (-150), drumsub vs drums -31.4; 154 s worker.
- drums on real-separated synth DrumSep stems: kick .939 snare .966 tom .80 hat .69 cymbal .40 (F1 @10 ms). Fixes:
  cluster min-gap (immediate 10 ms energy within 10 dB, earliest wins), attack search +15 ms, onset_frac 0.15,
  top_ref (3rd loudest) instead of p95. Generator stems unchanged (kick .977 snare/hat/cymbal 1, tom .8).
- hat/cymbal on separated synth limited by DrumSep mis-assignment (synthetic open hats -> ride, snare noise -> hihat).
- hq_worker polls locks every 2 s (other agents starve 15 s pollers).

## Resume 21:02 (session restarted)
- jeremy separate_hq real done 17:42; jeremy separate_fast + versatile both pending -> relaunched all_real.ps1 -Slugs jeremy,versatile (log all_real_sep2.log).
- determinism check: scratchpad m3a_det.ps1 (synth separate_fast,separate_hq twice into out\_wip\builder-m3a\synth_det) -> m3a_det.log.
- KeyError min_present_drum_s seen in M1's 17:51 gate = race with my 17:44 edit (param exists); not a bug.
- NOTE: scratchpad is shared with other agents; my scripts: an.ps1 all_real.ps1 m3a_*.ps1 sep_report.py drums_report.py score_drums.py.

## Milestone 6 (21:20) drums rules for separated stems
- core.drumsep_hits: + strike_rise_db 6 (kick/snare), + rise<10 bleed rule for ride/crash only, + dull hi-hat bleed
  (brightness 12 dB under the stem's typical, other stem louder), + open-hat copies in ride/crash dropped (decay >= 6 dB).
- Real-separated synth F1@10ms: kick 1.000 snare .979 hat .749 tom .80 cymbal .615 (was .939/.966/.688/.80/.40).
  Generator stems: kick/snare/hat/cymbal 1.0, tom .8. Hat ceiling: 36/182 soft closed hats after open hats are no onset
  in the DrumSep hi-hat stem.
- 3 new unit tests (dull bleed, open-hat dup, kick second bump). drums unit 15 pass.
- stem_activity+drums rerun on synth/newton/megafauna/jeremy with real separation (m3a_ad1.log, m3a_ad2.log).
- determinism: synth ingest+separate_fast+separate_hq --force twice -> 0 of 94 files differ (ROCm). 21:30
- 21:37 all four real songs + synth: separate_fast, separate_hq (ROCm), stem_activity, drums done with real upstream.
- gate M3a running (m3a_gate.log): unit FAIL only tests/unit/contract::test_stub_files_are_stubs (rhythm, M2; not mine); ruff/contract/validate PASS.
- real tests: stem_activity 4/4, drums 4/4 pass (-m real); separate_fast/hq real tests running (m3a_realtests.log).
- next: report docs/build/reports/builder-m3a.md, wait gate e2e/determinism.
- real tests: separate_fast 1/1, separate_hq 1/1 pass (-m real).
- 22:35 gate M3a: fixture/ruff/contract/validate/e2e/lib-node PASS; unit FAIL only external contract stub test; determinism FAIL
  23/179 files, none M3a (beats.csv onwards); M3a stems/meta/events identical; fast stems identical across 3 runs.
- report written: docs/build/reports/builder-m3a.md. DONE.
