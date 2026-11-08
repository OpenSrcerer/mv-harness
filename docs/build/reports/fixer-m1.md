# fixer-m1 report
Fixed: B1 (kick doubling: click-evidence refractory, full-weight click in kick onset score, envelope-less events dropped, kick_conf with click evidence relative to the song's kick click), M1 (quiet-master gate from sample peak, not the kick band), M2 (Segment.t_event; role_hints credits the unsnapped impact).
Tests: tests/review/M1 + unit spectral/dynamics/loudness: 68 passed, 12 skipped. Review step of the gate: 27 passed. ruff clean.
Gate: unit step fails on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (rhythm stage is no longer a stub: other module). E2E/determinism steps were still running (machine contended by other agents) when this report was written.
