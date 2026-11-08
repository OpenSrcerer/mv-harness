# fixer-m6a-r2 progress
- DONE: F-R2-UNDO (edit.js undo no longer double-pops history; failed undo restores its entry). F-R2-INTENT-ENC (server.py _decode_user_text: utf-8-sig, BOM utf-16, cp1252, latin-1; GET answers with a warning, POST answers 409 and never rewrites a non-UTF-8 intent.md).
- tests/unit/viewer + tests/review/M6a: 65 passed. ruff clean on viewer stage.
- Gate: unit step fails only on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (rhythm no longer a stub; not M6a's).
