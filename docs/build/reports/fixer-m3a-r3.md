# fixer-m3a-r3 report
R3-1 (ride 8ths lost): drums.core.drumsep_hits cymbal_rise_db 8.0 -> 4.0 (decision M3a-R3-1 in docs/contract/decisions/M3a.md).
tests/review/M3a/** and tests/integration/M3a/** all pass. New unit test test_dense_ride_patterns_keep_their_strokes (8ths 120/140/150 bpm with accents, 16ths 90 bpm).
Real-song drums rerun (integrator max upstream, --only drums --force) vs integrator: kick/snare/tom unchanged, hat -0..-14, cymbals up
(versatile 24->32, jeremy 169->275, megafauna 151->180, newton-vs-nye 14->31): the added strokes are ride strokes; not verifiable without truth.
Gate: unit step failed only on tests/unit/contract (catalog deps 'lyrics' extra in test_deps_match_plan; CONTRACT.md out of date) = other agents' concurrent contract edits, not M3a.
