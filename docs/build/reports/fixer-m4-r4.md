# fixer-m4-r4
Fix: keys.global_confidence keeps the R3-M1 gate (no-chord share >= 0.9 -> conf <= 0.3, key:no_tonal_evidence) but exempts
chord-less tonal material (a-cappella): mean top ks/temperley/albrecht correlation >= TONAL_PEAK 0.55, all three profiles exact/relative
with the winner, and S-KEY exact. Band noise (profile peaks ~0.2-0.3) stays gated; the a-cappella synth stem (0.72-0.91) keeps A minor.
Flag key:chroma_only marks the exemption. Unit tests: tests/unit/harmony/test_key_tonal_gate.py.
Tests: fast review M4 + unit harmony/mood pass; ruff clean. Gate M4 halts at pre-existing tests/unit/contract failures (not M4).
Real-song regression: only spans with no-chord share >= 0.9 are affected; real songs are 4.5-22 %, so unchanged by construction.
Re-run via copied integrator folder reported upstream stale; not executed.
