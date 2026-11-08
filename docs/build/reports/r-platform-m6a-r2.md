# r-platform-m6a-r2: R-PLATFORM review of M6a Viewer, round 2

Date: 2026-11-08. Lens: Windows platform and the viewer (paths and Unicode, the local server, file:// mode, a real browser).
Verdict: **fail**. The seven round-1 majors are fixed for real. Two new majors were found, each with a failing test.

## Round-1 findings, re-verified

The round-1 tests pass (`tests/review/M6a/r-platform`: 10 passed). I also checked that each fix is real and not tuned to its test:

| id | status | how it was verified beyond the test |
|---|---|---|
| F-PLAYHEAD | fixed | `setPlaying(true)` calls `requestDraw`, and `frame()` re-arms while `A.playing`. Claude_Browser on synth and real-newton-vs-nye (served): after 3 s, V.t matched audio time within 1 ms. Headless Edge in file:// mode (synth, real-newton, real-megafauna): within 20 ms. With one stem soloed, the stem stays within 1 ms of the mix. |
| F-OPTIONAL-EVENTS | fixed | `data.js` `markAbsent` and a guarded `ev()` treat events that were not ensured as empty (the same as mvh.js `EMPTY_EVENTS`). `visemes` is still loaded when the manifest lists it (kind `events`, `events: visemes`). |
| F-FATAL-ABSENT | fixed | real-newton-vs-nye and real-megafauna both load in file:// mode with zero console errors, 11 lanes and no lane errors. |
| F-SAVE-LOST | fixed | `api()` catches network errors, and the page reverts the edit and shows a toast. The server answers **503** after about 13 s of `PermissionError` retries when `overrides.json` is held open (probe), and leaves no `.tmp` files behind. |
| F-NAN | fixed | `loads_strict` rejects NaN; `all_finite` catches `1e999` and returns 400; the file is written with `allow_nan=False`. |
| F-CLOBBER | fixed | Invalid JSON on disk gives GET 200 with `error`, and POST answers **409**. The file stays byte-identical. In Claude_Browser the page shows the error at load and again on each edit. |
| F-INTENT-LS | fixed | `_LINE_SEPS` covers every separator that `str.splitlines()` splits on (bytes checked: `\x0b \x0c \x1c-\x1e \x85 U+2028 U+2029`), and `parse` splits on `\n` only. The M6b reader (`meaning/intent.py`) uses `splitlines()`, which is consistent because values written by the viewer contain no separators. |

## New majors

1. **F-R2-UNDO** (major), `src/mvh/assets/viewer/edit.js` `undo()`. Undo removes two history entries per click (`st.history.pop()` after `await save(...)`, while `save()` never pushes). From the second Undo on, each Undo goes two steps back, and `overrides.json` is rewritten with a state the user never chose. In headless Edge, three +10 ms edits followed by Undo, Undo left nothing on disk instead of 10 ms. Claude_Browser showed 0.07 → 0.06 → 0.04 → 0.02.
   Test: `tests/review/M6a/r-platform/test_r2_platform.py::test_undo_restores_the_previous_state_each_time`.
2. **F-R2-INTENT-ENC** (major, Windows), `src/mvh/stages/viewer/server.py` `read_intent`/`write_intent`. `meaning/intent.md` is the user's own file. When it is saved as cp1252 ("ANSI") or UTF-16 (two Notepad options), `UnicodeDecodeError` escapes the handler, so `GET /api/intent` gets no response and a traceback goes to stderr. The edit-mode viewer then shows only "The viewer could not load this song / TypeError: Failed to fetch". This was reproduced in Claude_Browser and in headless Edge, while file:// mode of the same folder works. `POST /api/intent` also drops the connection, and the page then says "server unreachable".
   Tests: `test_r2_platform.py::test_intent_md_in_a_windows_encoding_does_not_kill_the_api[cp1252|utf-16]` and `::test_edit_mode_loads_when_intent_md_is_not_utf8`.

Minor findings, Round 2 section of `docs/review/M6a-r-platform.md`:
- m6 is still open: `/api/intent` with t1 = `1e999` answers 200 and writes `1.000-inf s`, and that section's meaning is then dropped.
- m9: concurrent saves can get a 409 with a misleading "Not saved" message.
- m10: nudge buttons use stale values.
- m5 and m8 are still open.

## Commands that worked
- Build folders: `out/_wip/r-platform-m6a-r2/build.py`, which uses `rp_support.build_song_folder` and `tests/unit/viewer/build_view.py real-newton-vs-nye`.
- Serve: `powershell.exe -NoProfile -File scripts/run.ps1 python -m mvh.cli view <folder> --no-open --no-rerun` (run in the background, URL printed as JSON).
- Tests: `powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q tests/review/M6a/r-platform` gives 4 failed (the new ones) and 10 passed. Ruff is clean.
- The `undo` scenario was added to `tests/review/M6a/r-platform/cdp_viewer.mjs`.

Both servers (ports 60752 and 60753) were stopped. No real lyric text was printed.
