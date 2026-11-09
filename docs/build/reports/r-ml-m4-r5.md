# r-ml-m4-r5: R-ML review of M4 (harmony, mood), round 5 / W3 verify

Verdict: **fail**. R4-M1 is fixed for the case it was filed on, but the fix opens a new hallucination path (R5-M1). It also
only partly fixes the a-cappella case (R5-M2). Both have failing tests, with a fast stub variant and a real-model variant.

## R4-M1 verification
- The fix is real code, not a test hack: `keys.global_confidence` keeps the no-chord gate but adds the
  `tonal_without_chords` carve-out. The conditions are profiles unanimous (exact or relative), mean top correlation
  >= `TONAL_PEAK` 0.55, and S-KEY's top key exactly equal to the winner. It adds `key:chroma_only`.
- `tests/review/M4/r-ml/test_key_gating_a_cappella.py` passes (stub and real). `test_key_gating_band_noise.py` still passes.
- Probes with real S-KEY and real lv-chordia (`out/_wip/r-ml-m4-r5/probe5.log`, `probe6.log`):
  - The synthetic vocal stem gives A minor 0.67.
  - Five of six transpositions keep their key (0.66-0.97).
  - Band, brown and riser noise, TTS speech, a sine, single square/saw notes and a sustained triad pad all stay gated.

## New majors
- **R5-M1** (regression from the R4-M1 fix): a random 12-tone line gets "C minor" at 0.666 with only
  `key:chroma_only` / `key:relative_ambiguity` and no low-confidence flag. Before the fix it was capped at 0.3.
  - Inputs: lv-chordia is all N; S-KEY says C minor at p 0.238, barely voting.
  - Root cause: the Pearson profile correlation ignores how flat the chroma is. This line has normalised entropy 0.984 and
    peak/mean 1.48, against 0.90 and 2.6-2.8 for the tonal stems (`sum_entropy.py`).
  - Test: `tests/review/M4/r-ml/test_key_gating_atonal_line.py` (stub: conf 0.853; real: 0.666).
- **R5-M2** (R4-M1 partly fixed): the same a-cappella stem transposed +3 semitones (C minor) is labelled
  `key:no_tonal_evidence` at 0.3.
  - Inputs: all three profiles say C minor on a peaked chroma; S-KEY votes the fifth, G minor (p 0.337).
  - The carve-out requires S-KEY to agree exactly and all three profiles to agree. A sung F-minor line (S-KEY F minor p 0.668,
    KS F minor, Temperley/Albrecht Db major) is gated the same way.
  - Test: `tests/review/M4/r-ml/test_key_gating_a_cappella_fifth.py` (stub and real both fail on the flag).

## Suggested fix (both)
- Measure tonality on the chroma DISTRIBUTION, not by correlation. Use the peak/mean or entropy of the long-term chroma sum:
  atonal lines are 1.4-1.7 / 0.98+, band noise 2.4 / 0.93-0.96, tonal a-cappella 2.6-3.2 / 0.85-0.91. Combine it with
  profile agreement.
- Require S-KEY p_max >= ~0.35 to confirm, or accept a fifth or relative S-KEY vote with a lower cap.
- Keep `key:no_tonal_evidence` for the flat or split cases only.
- Cap the carve-out at about 0.8.

## W3 regression check
- Real mixes through `core.analyse` with the integrator's beats (`probe_real.log`) are identical to `out/_wip/integrator`
  for jeremy, megafauna, versatile and newton-vs-nye.
- The jeremy lead-vocal A-minor region is restored to 0.83.
- Mood re-run on jeremy and megafauna matches the integrator to within 5e-5 with the same tags (`mood_check.log`).
- `mvh analyze --only harmony` on copies of the integrator folders refuses to run: rhythm is stale after the W3 M2 changes.
  This is upstream, not M4.
- There is no `tests/integration/M4/`.

## Minors
The minors are in `docs/review/M4-r-ml.md`, Round 5:
- m19: the chroma-only key has no confidence ceiling.
- m20: the relative key is not flagged on a chroma-only key.
- m18, m14, m17 and m9 are still open.

## Commands that worked
- `powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-ml-m4-r5/probe6.py atonal:28:60 shift:3:0` (with MVH_RUN_OFFLINE=1)
- `... python -m pytest -q -m real tests/review/M4/r-ml/test_key_gating_atonal_line.py tests/review/M4/r-ml/test_key_gating_a_cappella_fifth.py`

## Test run
`pytest --timeout=0 tests/unit/harmony tests/unit/mood tests/review/M4` (real models included): 103 passed. The only 4 failures
are the new R5 tests, which fail as stated (`out/_wip/r-ml-m4-r5/pytest_unit.log`). The first run with the default 600 s
pytest-timeout was killed while `tests/unit/harmony/test_keys.py` waited for a heavy slot. That is machine contention, not M4.
ruff on `tests/review/M4/r-ml` is clean.
