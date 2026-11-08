# fixer-m4 report
F1 (S-KEY probability recovery + gating/weighting), F2 (CQT tuning unit), F3 (no confident key without two independent methods; silence/quiet windows gated) fixed in src/mvh/stages/harmony/{keys,core,chroma}.py.
tests/unit/harmony + tests/review/M4: 74 passed. Gate M4 (before final tweak): review PASS; remaining FAILs are other modules (ruff in sep/fit.py, drums/core.py, M5 review test; contract test_stub_files_are_stubs for rhythm; determinism drum_hits/manifest/viewer).
Note: score uses linear p because log p let a 1e-4 runner-up dominate and shifted the modulation boundary 8.5 s.
