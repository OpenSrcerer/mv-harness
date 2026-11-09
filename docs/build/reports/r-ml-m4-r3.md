# r-ml-m4-r3 report (R-ML review of M4, round 3)

Verdict: pass-with-fixes.

## r2 findings
- B1 (S-KEY gate KeyError): FIXED. `core.analyse_key` writes `methods.skey` whenever S-KEY ran (`voted`, `p_max`, `windows`).
  Real S-KEY on white/pink/synth noise: no crash. Test `tests/review/M4/r-ml/test_skey_gate_crash.py` passes (fast and real).
- M1 (noise gets a confident key): FIXED for the named cases. `keys.global_confidence` counts ks/temperley/albrecht as one
  "profiles" source; under two sources conf is capped at 0.25 with `key:no_tonal_evidence`. General rule, not a test hack.
  `tests/review/M4/r-ml/test_key_gating_noise.py` passes.
- No regression on real songs (jeremy .836, megafauna .50, versatile .50, newton-vs-nye .902; synth A minor .515).

## New findings
- MAJOR R3-M1: the lv-chordia no-chord share is still not used as tonal evidence. Band-limited (300-700 Hz) noise, lv 100 % N,
  real S-KEY p_max 0.41 (votes): F minor conf 0.80, flags ['key:methods_disagree'] only. Failing test:
  `tests/review/M4/r-ml/test_key_gating_band_noise.py` (stub S-KEY at 0.41 -> 0.792; real S-KEY -> 0.802).
- Minors m12 (no_tonal_evidence label on tonal a cappella), m13 (one 2 s spurious chord counts as a source), m9 still open:
  `docs/review/M4-r-ml.md` Round 3.

## Gate
`scripts/gate.ps1 M4` stops at `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` (rhythm is no longer a stub;
not an M4 defect, for the W3 integrator).
