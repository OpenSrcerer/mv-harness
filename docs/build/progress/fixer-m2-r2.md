# fixer-m2-r2 progress
- started; target F4 structure real upstream. test: tests/review/M2/r-dsp/test_structure_real_upstream.py
- boundaries solved (F=1.0 both variants): own score w/ nov_pat,nov_emb, edge damping, dyn gated confirmatory, phrase-grid refinement (split_min_novelty). STAGE has TEMP debug: MVH_DBG_DUMP/MVH_DBG_P env hooks + boundary_components meta + unused w_hom in segment_dp -> remove. probe: out/_wip/fixer-m2-r2/run.sh H D name. NEXT: repeat groups (chorus#1 vs chorus#2 same group, not verse)
- groups done (agglomerative + adjacent penalty), review tests pass; debug hooks removed. NEXT: docstring edit, real tests (MVH_REAL_TESTS=1) + real-song replay sanity, unit tests all M2, gate, decisions/M2.md, report
- docstring/tests/decisions done. NEXT: run gate (log out/_wip/fixer-m2-r2/gate.log), report
- gate run: M2 parts pass; unit fail=stale contract stub test, determinism fail=non-M2 files (separation). report appended. DONE
