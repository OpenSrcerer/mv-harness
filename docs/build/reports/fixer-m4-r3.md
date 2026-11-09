# fixer-m4-r3
R3-M1 fixed: keys.global_confidence takes the lv-chordia no-chord share of the span (keys.no_chord_share_in). Share >= 0.9 caps key confidence at 0.3 and adds key:no_tonal_evidence + key:low_confidence whatever S-KEY says; chords/phrase count as sources only when chord-covered share >= 0.25. core.analyse_key passes it for global and region keys.
Tests: tests/review/M4 pass (gate review PASS), tests/unit/harmony pass (incl. new test_key_no_chord_gate.py).
Gate M4: ruff (2 errors outside M4 paths), contract gen --check (CONTRACT.md out of date), determinism (29 files differ, whole-pipeline) fail; not M4 files.
Real-song re-run comparison not done in this round (time).
