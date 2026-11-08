# fixer-m4-r2
B1: core.analyse_key now always creates methods["skey"] (top, voted flag) when S-KEY ran, so a gated S-KEY no longer raises KeyError.
M1: keys.global_confidence counts ks/temperley/albrecht as one "profiles" source; fewer than two independent sources caps conf at 0.25 and adds key:no_tonal_evidence + key:low_confidence.
Tests: review M4 + unit harmony/mood (not real/slow) 57 passed; ruff clean. Gate stops at tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (asserts rhythm is still a stub; not M4's).
