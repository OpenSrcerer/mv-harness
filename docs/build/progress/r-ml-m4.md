# r-ml-m4 progress (R-ML review of M4 harmony & mood)

## Done
- Read PLAN/SPIKE/CONTRACT/spike docs; read all of src/mvh/stages/{harmony,mood}.
- S-KEY probe (scratchpad skey_probe.py): 24/24 synthetic cadences correct -> keyMap/preproc OK; max softmax ~0.095 even on clean input.
- Mood mel front end == librosa slaney mel (max diff 6e-7) -> port OK.
- lv-chordia: reads our 22.05k wav via librosa.load(sr=22050); raw CQT magnitude, no log/normalisation (gain-sensitive?).

## Running / next
- out/_wip/r-ml-m4/probe_h.log (harmony: synth, gain -20/-30, noise, drums/vocals stems, 4 real songs)
- out/_wip/r-ml-m4/probe_m.log (mood: synth, gain, noise, sine, quiet, voice, drums, 4 real songs)
- out/_wip/r-ml-m4/analyze_synth.log (mvh analyze --only harmony,mood on a copy of builder synth folder) -> check provenance licences
- double-softmax hypothesis for S-KEY output

## Commands that work
- Git Bash: MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- heavy slots are contended (other agents); run probes in background

## Milestone 2 (findings so far)
- MAJOR S-KEY double softmax: recovered p=log q-mean+1/24 sums to 1; clean cadence p .87 (q .094), noise .13, near-silence impulses .51 -> tests/review/M4/r-ml/test_skey_output.py
- MAJOR chroma tuning applied at 1/3 (semitone tuning passed to 36-bpo cqt); jeremy +0.28 st -> test_chroma_tuning.py (FAILS as expected)
- candidate: S-KEY-only key regions in near-silent tail -> test_key_gating.py (pending run)
- probes OK: lv-chordia gain-invariant (-20/-30 dB identical), noise/drums -> 100% N, no-chord share real 4.5/14.1/18.4/21.9 %, keys match SPIKE.
- mood: front end == librosa slaney; real-song values match SPIKE; -60 dBFS noise -> arousal_conf .79, tags relaxing (minor gating); gain -20 dB changes tags (minor)
- MAJOR (new): digital silence 20 s -> key "C minor" conf 0.75, no flag (edge.log); single-method ensemble gets full credit. Added to test_key_gating.py.
- edge: 0.5/5/10 s inputs run (no crash); mood zeros -> silent conf 0 OK.
- minor findings written to docs/review/M4-r-ml.md (m1-m7)
- next: wait review_run1 (old files), then rerun full tests/review/M4/r-ml -> confirm 5 failing tests; write report
- DONE: review_run2 -> 4 failed as intended (tuning, silence key, 2x S-KEY). Tail test dropped (passed: not a defect).
- Report written: docs/build/reports/r-ml-m4.md; minors docs/review/M4-r-ml.md. Only StructuredOutput remains.
