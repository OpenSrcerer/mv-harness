# r-platform-m6a: R-PLATFORM review of M6a Viewer

Reviewer: r-platform-m6a (independent; the builder's report was read only after these findings were formed, to locate code).
Scope: the `viewer` stage, `src/mvh/assets/viewer/`, `mvh view` (server and edit-mode POSTs). Lens: Windows paths and Unicode, the local
server, file:// mode, and the viewer in a real browser.

**Verdict: pass-with-fixes.** 0 blockers, 7 majors (10 failing test cases in `tests/review/M6a/r-platform/`), 8 minors
(`docs/review/M6a-r-platform.md`).

## How it was run
- Song folders were built with the real viewer stage against the fixtures: `out/_wip/r-platform-m6a/{synth, real-newton-vs-nye, real-megafauna, "ünï cødé ☃ song"}`.
  Served mode used `mvh view <folder> --no-open`, with the page driven in Claude_Browser (screenshots, console, network).
- The Claude_Browser pane cannot open large `file://` pages (it renders file URLs as size-capped static snapshots). So file:// mode and the regression tests use
  **headless Edge** driven over the DevTools protocol from node (`tests/review/M6a/r-platform/cdp_viewer.mjs`, no dependencies).
  The pytest wrappers build the song folder with the real stage, start the real `ViewServer` and assert on what the browser saw.
- Probes for the server and the intent block: `out/_wip/r-platform-m6a/probe_server.py`, `probe2.py`, `probe3.py`.
- Run the tests with `uv run --frozen --no-sync python -m pytest -q tests/review/M6a`. The suite takes about 20 s and fails 10 of 10 now.
  The browser tests skip only when node or Edge/Chrome is missing.

## Major findings (each has a failing test)

| id | location | claim | test |
|---|---|---|---|
| F-PLAYHEAD | `audio.js` `setPlaying`, `view.js` `frame` | Pressing **Play** (button or Space) never starts the render loop. `frame()` re-arms `requestAnimationFrame` only while it is already running, and `setPlaying(true)` does not call `requestDraw`. The audio plays, but the playhead, the clock, the "now" footer, follow-scrolling, section loop and stem drift correction all stay frozen until the pointer moves over a lane. Seen in Claude_Browser: the audio was at 29.9 s while `V.t` was 0 and the clock showed `0:00.000`, and hovering a lane made it jump to 30.9 s. Seen in headless Edge: audio at 2.47 s, viewer at 0.00 s. This also happens on a complete folder. | `test_browser_viewer.py::test_playhead_follows_audio_after_pressing_play` |
| F-OPTIONAL-EVENTS | `data.js` `boot` (ensures only the manifest's events), `lanes.js:792` `items('visemes')` | `lipsync/visemes.json` is optional (catalog `required=False`, and lipsync is a Should). When it is absent, the manifest (or the inlined mini manifest) does not list it, the viewer never ensures it, and `song.events('visemes')` throws on every draw. The Vocal range lane is painted "lane error: mvh: 'events:visemes' is not loaded", with console errors on each redraw. Expected for instrumental songs or when Rhubarb fails. | `test_browser_viewer.py::test_missing_optional_visemes_does_not_break_a_lane` |
| F-FATAL-ABSENT | `data.js` `buildModel` (`items('singing')`, `items('voice_spans')`, `items('cues')`) | When an events file the model reads is absent, the whole page fails: "The viewer could not load this song". From file:// this hits both real W0 fixtures in headless Edge (real-megafauna, real-newton-vs-nye: `'events:singing' is not loaded`) and any partial or degraded folder. The stage still reports `status: ok` (confidence 0.75 to 0.8, `lanes_without_data` lists the lanes). Served mode on those fixtures only works because they have no manifest.json, so every name is probed. | `test_browser_viewer.py::test_file_mode_loads_when_an_events_file_is_absent` |
| F-SAVE-LOST | `edit.js` `api` / `save` | When the POST to `api/overrides` fails at the network level, `fetch` rejects inside `save()` before its error branch runs. This happens when the server was stopped (Ctrl+C), hit its idle timeout after the tab was frozen or the PC slept, or when `atomic.write_bytes` gives up on a locked `overrides.json` and the connection drops. The edit stays applied in the page (pending grid preview), the bar shows `saving…` forever, and no error toast appears, while `overrides.json` was never written. The user believes the correction was saved. | `test_browser_viewer.py::test_failed_save_is_reported_and_not_shown_as_applied` |
| F-NAN | `server.py` `do_POST` / `check_overrides` / `write_overrides` | `json.loads` accepts `NaN`, `Infinity` and `1e999` (which becomes inf). The schema's `number` and `minimum` checks let them through (`NaN < 1` is False), and `json.dumps` writes them back. `overrides.json` becomes non-standard JSON, and the **viewer itself then fails to load in edit mode**: `r.json()` of `api/overrides` throws "Unexpected token 'N'" (seen in Claude_Browser). Strict readers fail too. Reaching it needs a client holding the token, but the server is the validation gate. | `test_server_platform.py::test_post_overrides_rejects_non_finite_numbers` (4 cases) |
| F-CLOBBER | `server.py` `read_overrides` / `write_overrides` | `overrides.json` is also written by hand (CONTRACT §1). If the user's file does not parse (a trailing comma), `read_overrides` returns `{}` with a valid etag and GET reports no error. The first edit in the viewer then atomically **replaces the hand-written corrections**: bpm and section labels are lost without a word. | `test_server_platform.py::test_unparseable_overrides_on_disk_is_not_silently_overwritten` |
| F-INTENT-LS | `intent_block._one_line` vs `parse` | To keep each value on one line, `_one_line` replaces only `\r` and `\n`. `parse` then splits the block with `str.splitlines()`, which also breaks on U+2028/U+2029, NEL U+0085, VT, FF and U+001C–1E (common in text pasted from web pages and Word). The user's authored meaning is silently truncated at the separator, and the rest can inject a line: in the probe, `feel: "calm<NEL>- do not: show the moon"` became a new do-not rule. The user's meaning is the top goal of the harness (PLAN §1, §8). | `test_server_platform.py::test_intent_values_with_unicode_line_separators_survive` |

### Suggested fixes
- F-PLAYHEAD: call `requestDraw('playhead')` in `setPlaying(true)`, or start the loop on the media element's `play` and `playing` events, and keep it re-armed while `A.playing`.
- F-OPTIONAL-EVENTS / F-FATAL-ABSENT: never call `song.events(name)` for a name the folder did not list. Add a helper `evs(name) = song.isLoaded('events:'+name) ? song.events(name).items : []`, or ensure the full `EVENT_NAMES` list and treat 404s or absent inline entries as empty (mvh.js already maps a missing file to `EMPTY_EVENTS`). A smoke test that loads the page with each optional or absent events file removed would catch regressions.
- F-SAVE-LOST: wrap `fetch` in `api()` with try/catch, return `{ok:false, status:0, j:{error:'server unreachable (mvh view stopped?)'}}`, and let the existing error branch revert `V.ovr` and toast. Do the same in `saveIntent`. The server should also answer 503 with a JSON error when `atomic.write_bytes` raises, instead of dropping the connection.
- F-NAN: parse bodies with `json.loads(..., parse_constant=<raise>)`, and reject any non-finite float (walk the doc, `math.isfinite`) with a 400 before validating. Write with `allow_nan=False`.
- F-CLOBBER: when `overrides.json` exists but does not parse or is not an object, return `{"overrides": {}, "etag": ..., "error": "overrides.json is not valid JSON: <line/col>"}`. The page shows that error and the server refuses POSTs (409 or 422) until the file is fixed, or it moves the broken file to `overrides.json.broken-<ts>` before the first write and says so.
- F-INTENT-LS: in `_one_line`, normalise every character `str.splitlines()` splits on (`re.sub(r"[\r\n\v\f\x1c-\x1e\x85  ]+", " / ", ...)`). In `parse`, split only on `\n` (`text.split("\n")`, stripping `\r`). Readers in M5 and M6b must use the same rule.

## Minor findings
In `docs/review/M6a-r-platform.md`:
- m1: Windows 8.3 short name `CACHE~1` serves `.cache`.
- m2: `%00` in a URL crashes the handler.
- m3: favicon 404 console error.
- m4: the re-run command is shown with an unquoted path.
- m5: CRLF in `intent.md` is converted to LF, although the docstring says the file is preserved byte for byte.
- m6: `t1 = Infinity` silently drops a section.
- m7: a standalone `viewer.html` logs two file-not-found console errors before the inline audio fallback.
- m8: a folder without a manifest logs 34 console 404s.

## Verified OK
- 127.0.0.1 on port 0 and the idle timeout.
- Host, Origin and token checks.
- Path traversal in 10 variants.
- Atomic, etag-guarded writes.
- Unicode and spaces in paths, in served mode and file:// mode.
- Deterministic HTML.
- Size cap.
- All 11 lanes on the complete synthetic folder (both modes) and on real-megafauna (served), with no lane errors.
- The inline-audio fallback of a standalone `viewer.html` plays.

Details are in the minors file.

## Contract notes / change requests
None for the frozen contract. F-INTENT-LS matters to the W3 integrator: the M5 and M6b readers of the managed `intent.md` block must split lines exactly as the writer does.

## Files written
- `tests/review/M6a/r-platform/{conftest.py, rp_support.py, cdp_viewer.mjs, test_browser_viewer.py, test_server_platform.py}`
- `docs/review/M6a-r-platform.md`, `docs/build/progress/r-platform-m6a.md`, this report
- `out/_wip/r-platform-m6a/**`: built folders, probes, the headless Edge profile and DOM dumps. All of it can be deleted.

## Re-check after fixer-m6a
I re-ran `uv run --frozen --no-sync python -m pytest -q tests/review/M6a/r-platform` against the code as fixer-m6a changed it. Result: **10 passed**
(all of them failed when the review was written). All 7 majors are fixed in the current code. I did not re-check the minors (m1 to m8).
