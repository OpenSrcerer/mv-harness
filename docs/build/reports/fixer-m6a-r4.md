# fixer-m6a-r4
Fix F-R3-UNDO-FAIL in src/mvh/assets/viewer/edit.js: undo() passes the popped history entry to save(doc,'undo',popped); the failure branch pushes that entry back (commit failures still pop). undo() is ignored while st.saving, so a second Ctrl+Z never goes out with a stale etag.
Results: tests/review/M6a + tests/unit/viewer: all pass except test_r4_platform voice-floor (voices stage, not M6a; change request) and test_r2 not_utf8 which failed under gate load but passes alone (timing).
Gate M6a: unit failed on contract collection (not viewer, viewer=0); ruff/contract/determinism failures are outside M6a (determinism = GPU drum stems upstream). Viewer ruff clean. Real-song rerun comparison not performed this round.
