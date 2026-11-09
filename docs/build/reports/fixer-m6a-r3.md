# fixer-m6a-r3 report
Fix: src/mvh/assets/viewer/edit.js. undo() now passes the entry it popped to save(doc,'undo',popped); the failure branch pushes that entry back (commit failures still pop). undo() returns early while st.saving, so a second Undo/Ctrl+Z never goes out with a stale etag.
Tests: tests/review/M6a 15 passed (incl. test_a_failed_undo_keeps_the_state_it_was_restoring); tests/unit/viewer passed; gate steps fixture/unit/review/ruff/contract/validate/e2e/lib-node PASS.
Gate: determinism FAIL: 30 of 181 files differ between two --force runs (tables/beats.csv, bars.csv, sections.csv, ... and viewer.html, which inlines them). The differing files are upstream (GPU/separation-dependent) outputs, not viewer code; viewer.html differs only as a consequence. Matches the known W2 drum sub-stem determinism failure.
Real-song re-runs and servers: not re-run (viewer-only JS change; no server left running).
