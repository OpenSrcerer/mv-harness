# r-platform-m6a-r3: R-PLATFORM review of M6a Viewer, round 3

Date: 2026-11-08. Lens: Windows platform, the local server, edit-mode POSTs and the viewer in a real browser.

## Verdict: pass-with-fixes (one new major)

### Earlier findings
- **F-R2-INTENT-ENC: fixed (real).** `server.py` now reads `intent.md` as bytes (`_decode_user_text`: utf-8-sig, BOM UTF-16, cp1252, then latin-1).
  GET answers 200 with a `warning`, and POST answers 409 without touching the file. Claude_Browser on a served folder with a cp1252 `intent.md`:
  the edit-mode page loads (ready, no fatal page), the save toast says the file is not UTF-8, and the file bytes did not change. The fix is general and not
  test-specific. A side effect is that the CRLF-to-LF minor m5 is now fixed too.
- **F-R2-UNDO: fixed on the success path.** `undo()` pops once. The r2 test passes, and Claude_Browser runs of 3 edits followed by Ctrl+Z gave 0.03, then 0.02, then 0.01.
- **F-R2-UNDO, failure branch: not fixed correctly (new major F-R3-UNDO-FAIL).** The fixer's new branch is
  `if (isUndo) st.history.push(J(clean(prev)))`, where `prev` is `V.ovr` when `save()` starts. That is the CURRENT document, not the entry that
  `undo()` popped. After any failed Undo, the state Undo was restoring is gone from the history. The next Undo writes the current state again ("Saved:
  undo" with no change), and the Undo after that skips a step. This is the same "Undo skips a state" symptom as F-R2-UNDO.
  - Failing test: `tests/review/M6a/r-platform/test_r3_platform.py::test_a_failed_undo_keeps_the_state_it_was_restoring`
    (CDP scenario `undo-fail`: edits 10, 20 and 30 ms, then one Undo POST answered 503, then Undo, Undo). It gives `[0.03, 0.01]` and expects `[0.02, 0.01]`.
    It failed the same way in two separate gate runs.
  - The 503 is the server's real answer on Windows when `overrides.json` is read-only or locked: `probe_ro.py` returned
    `503 could not write overrides.json (PermissionError)` after 13.2 s of `replace_retry` backoff.
  - The same bug can be reached with no server fault: two Ctrl+Z presses 5 ms apart (Claude_Browser, served synth). The second Undo goes out with
    the stale etag and gets 409. The branch pushes the current state, and the following Ctrl+Z presses gave 0.02, 0.02 ("Saved: undo", no change)
    and then null, so 0.01 was skipped. 30 ms apart did not race on this machine.
  - Fix: `undo()` passes its popped entry, e.g. `save(doc, 'undo', prevEntry)`, and the failure branch pushes back that entry, not `J(clean(prev))`.
    Also ignore Undo, or queue it, while `st.saving` (this is the same in-flight issue as minor m9).

### Minors (docs/review/M6a-r-platform.md, "Round 3")
- m11: a UTF-8 BOM in `intent.md` is dropped on the first save.
- m12: the page never shows the new non-UTF-8 `warning`.
- m13: GET `/api/intent` still has no `OSError` handler (a locked file gives the fatal page).
- m6 is still open (`1e999` is written as `inf`). m8 is still open (404 noise on fixture folders without a manifest).

### Checks run
- `pytest tests/review/M6a tests/unit/viewer`: 65 passed before the new test was added. The new test fails as intended.
- Gate `scripts\gate.ps1 M6a` (log: `out/_wip/r-platform-m6a-r3/gate.log`):
  - unit fails only on `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`, which is not M6a's (rhythm is no longer a stub).
  - review fails only on the new r3 test.
  - ruff, contract and validate pass.
- Claude_Browser, served mode:
  - synth (path `sÿnth ☃ r3`): edits and undo work as described above.
  - ANSI-intent folder: loads.
  - real-megafauna: ready, 11 lanes, no lane errors, audio plays and the playhead is synced (A 2.4626 s, V.t 2.4606 s). The only console errors are the known m8 404s.
- The Claude_Browser pane refused `file://` URLs in this session. file:// mode is covered by the headless-Edge tests in `test_browser_viewer.py`, which pass.
- All servers were stopped. No leftover python processes.
- Gate determinism step: FAIL, 52 of 179 files differ between two `analyze --force` runs. The diffs start upstream: `curves/core.f32`, `events/beats.json`,
  and the outputs of the real rhythm, harmony and voices stages. `viewer.html` differs only because it inlines those inputs. `det.py` built viewer.html
  twice from the same synth inputs and the two builds were byte-identical (sha 4431382d8ac5). So the failure is not M6a's; it goes to the owners of those
  upstream stages and the W3 integrator. The gate also ran e2e and lib-node: both PASS.
