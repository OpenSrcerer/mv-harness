# fixer-m3b-r4 report (M3b, W3 round 2)
- S04 (MEGAFAUNA presence): verified on a full re-run of out/_wip/fixer-m3b-r4/megafauna: vocal_range.present true (via lyric coverage), 10 phrases, 33 vocal notes. tests/integration/M3b reads out/_wip/integrator/megafauna, so it passes only after the integrator re-runs vocals there.
- Review tests (r-ml round 4): interpolated lyric lines no longer open the voice gate; untagged lyric frames no longer outvote a tagged rap verse. tests/review/M3b 5 passed.
- Regression: jeremy, versatile, newton-vs-nye, synth re-run vs integrator: same present/style; counts within refresh noise (versatile 16->27 notes after upstream refresh).
- Gate M3b: review, validate, e2e, lib-node, determinism PASS. unit FAIL only in tests/unit/contract (PLAN_DEPS lacks vocals->lyrics; CONTRACT.md regen), contract FAIL (same), ruff FAIL in src/mvh/sep/determinism.py (not mine). Log: out/_wip/fixer-m3b-r4/gate.log.
