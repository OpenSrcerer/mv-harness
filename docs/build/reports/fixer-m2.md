# fixer-m2 report (M2 Rhythm, review round 1)
Fixed F1-F5 with real fixes (no test special cases). All tests/review/M2/** pass (opt-in real test included), unit tests for
allin1/rhythm/structure/choreo/cues pass, ruff clean on M2 paths.
- F1 cues: pin leads merged kind/kinds/sources, strength/lead-in nulled only for tier 4, moments from kinds[].
- F2 rhythm/choreo: metrical window clipped to song length; length-preserving smoothing (smooth_same).
- F3 structure: segment_dp never emits a short first section.
- F4 structure: melodic fingerprint (static-harmony-free chroma) for repeat groups; strong boundaries not merged away.
- F5 rhythm: trackers with a detected constant phase shift vote with it removed, then meter re-decoded.
Gate M2: fixture/review/contract/validate/e2e/lib-node PASS. unit FAIL only tests/unit/contract stub test (CR M2-5, not M2).
ruff FAIL only in src/mvh/sep, drums, tests/review/M5 (other modules). Determinism re-run failed in spectral (M1):
KeyError 'kick_step_db' (concurrent edit of that stage's params), not M2.
Change requests: CR M2-7 move 'pinned' first in CUE_KIND_PRIORITY.
