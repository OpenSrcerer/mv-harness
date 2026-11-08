# r-dsp-m2 progress (independent reviewer, M2 Rhythm, lens R-DSP)

## Done
- Read specs + all M2 code. Full `mvh analyze` of synth: out/_wip/r-dsp-m2/synth (rhythm F1 1.0, downbeat F 1.0,
  tempo err 0.033, pickup + 3/4 bar ok; structure poor with real upstream).
- Probes (out/_wip/r-dsp-m2/probes/): replay.py (real songs, W0 cached tracker outputs replayed, no heavy slot),
  p_clicks (models: tempo ok at 60-200 BPM; DSP path halves 160-200), p_waltz (3/4 detected on musical waltz),
  p_edge/p_short (rhythm crashes < 6 s, choreo < 2 s), p_pinned, p_struct_a1, vote_dump (versatile phase flip),
  p_trans (snap to low-band body transient, +13..18 ms).
- Failing tests written + verified (11 fail, 2 real skipped by default; real ones fail with -m real):
  tests/review/M2/r-dsp/{test_cues_pinned, test_short_inputs, test_structure_min_bars,
  test_structure_real_allin1 (+ data/synth_real_allin1.npz), test_rhythm_downbeat_vote_real}.py. ruff clean.

## Next
- DONE: minors doc, report written; structured output returned.


## Commands that worked
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- venv python for quick numpy scripts: .venv/Scripts/python.exe
- pytest: scripts/run.ps1 python -m pytest -q tests/review/M2/r-dsp [-m "real or not real"]
