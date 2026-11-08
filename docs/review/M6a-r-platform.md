# M6a Viewer: R-PLATFORM minor findings

Reviewer: r-platform-m6a (2026-11-08). The blockers and majors are in `docs/build/reports/r-platform-m6a.md`, and each has a failing test
under `tests/review/M6a/r-platform/`. Every item below was reproduced by running the code (probe scripts in
`out/_wip/r-platform-m6a/probe*.py`).

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | `server.py` `ViewServer.resolve` | The hidden-folder rule is bypassed through Windows 8.3 short names. `GET /CACHE~1/ingest/embedded_lyrics.json` returns **200** with the file's content, although `.cache` is meant never to be served. 8.3 name generation is on for C: here (`dir /x` shows `CACHE~1  .cache`). `_INTER~1` is still refused because it starts with `_`. Only clients on localhost can reach this, so the impact is a policy break, not remote exposure. | `probe_server.py`: `cache direct 404`, `cache short (200, b'{"secret": 1}')` | After `resolve()`, check the **resolved** path's parts relative to the folder (`p.relative_to(self.folder).parts`) against the dot/underscore rule, or refuse any segment that contains `~`. |
| m2 | `server.py` `resolve` | A URL with `%00` makes `Path.resolve()` raise `ValueError: embedded null character`. The handler dies, prints a traceback to stderr, and the client gets a dropped connection instead of a 400 or 404. | `probe_server.py`: `nul exc RemoteDisconnected` plus the traceback | Catch `ValueError`/`OSError` in `resolve` and return `None`. |
| m3 | `template.html` | In served mode every load logs a console error for `GET /favicon.ico` (404). The lens asks for no console errors. | CDP run on a complete synthetic folder: `consoleErrors: ["... 404 (Not Found) http://127.0.0.1:<port>/favicon.ico"]` | Add `<link rel="icon" href="data:,">` to the head. |
| m4 | `edit.js` `renderBar` | After a save, the Edit panel says ``Run mvh analyze <folder>`` with the folder **unquoted**. On this machine song folders contain spaces (`ünï cødé ☃ song`), so copying the command into a shell fails. | Edit pane text in the browser: `Run mvh analyze C:\...\ünï cødé ☃ song or press Re-run.` | Show the command with the path quoted (PowerShell-safe `'...'`), or offer a copy button. |
| m5 | `server.py` `write_intent` / `intent_block.py` | The file promises that text outside the managed block is "preserved byte for byte" (docstring and decision V7). In fact `read_text()` converts CRLF to LF, and the whole user file is rewritten with LF on the first viewer save. Notepad and older editors save `intent.md` with CRLF. | `probe2.py`: `user text preserved byte for byte: False b'# My song\nIt is about the sea.\n\n<!-- mvh'` (the input was `\r\n`) | Read with `newline=""`, splice the block in using the file's own line ending, and write the bytes back unchanged outside the block. |
| m6 | `intent_block._validate_section` | `POST /api/intent` with `t1 = Infinity` (Python's json accepts it) answers **200 ok**, but the block renders `inf-...` / `-inf`, which `_SEC_RE` cannot read back. The section's meaning is dropped silently on the next parse. | `probe2.py`: `(200, {... 'sections': {}})` after posting `t1: inf` | Require finite `t0`/`t1` (`math.isfinite`), and reject non-finite numbers for the whole request (same root cause as major F-NAN). |
| m7 | `audio.js` `onAudioError` chain | A standalone `viewer.html` opened without `audio/` (the documented file:// use) logs two `net::ERR_FILE_NOT_FOUND` console errors (`audio/mix.flac`, `audio/preview.opus`) before it falls back to the inline preview. The fallback itself works: audio played from the inline blob in headless Edge. | `standalone.py` CDP run: `consoleErrors` holds the two file-not-found lines and `currentTime` is 2.45 s | When `location.protocol === 'file:'` and an inline preview exists, start with the inline preview, or accept the noise and note it in the help. |
| m8 | `data.js` `boot` | On a folder without `manifest.json` (the `tests/contract/real-*` fixtures as built by the builder's `build_view.py`), served mode requests every name in `EVENT_NAMES`. This logs 34 `404` console errors per load. Real `mvh analyze` folders have a manifest, so only fixture and partial folders are affected. | Claude_Browser on real-megafauna: 34 × "Failed to load resource ... 404" | Use `bundle.files` (the inlined mini manifest) as the list of files that exist when the folder has no manifest. |

## Verified OK (no finding)
- Binds 127.0.0.1 on port 0, and the URL and port are printed as JSON. The idle timeout stops the server (`wait()` returned `idle` after 1.2 s with `idle_timeout=1`). Servers started for this review were stopped.
- Path traversal: `..`, `%2e%2e`, `%2f`, `%5c` backslashes, drive letters, `C%3a`, UNC `\\host\c$`, ADS `::$DATA` and the reserved names `CON` and `aux.json` all return 404. `//?/C:/...` falls through `urlsplit` to an empty path and serves viewer.html, not the file.
- Wrong Host (`evil.com`, a DNS-rebinding name with the right port) gets 403, and a POST without the token gets 403.
- Writes to `overrides.json` and `intent.md` are atomic (`mvh.io.atomic`: temp file, `os.replace`, PermissionError backoff). Concurrent POSTs serialise through a lock and an etag. Hard-linked fixture files are never written through.
- Unicode and spaces in the song-folder path work in served mode (Claude_Browser) and file:// mode (headless Edge, `ünï cødé ☃ song`).
- `viewer.html` is byte-identical across two builds. Real fixture pages are 7.2 MB (newton-vs-nye) and 9.0 MB (megafauna), within the 28 MB cap.
- A complete synthetic folder shows all 11 lanes (sections, meaning, lyrics, beats, hits, bands, loud, instruments, notes, vocal, cues) with no lane errors in both modes. The real-megafauna folder in served mode also shows all 11 lanes, with 382 beats and 9 sections.

## Round 2

Reviewer: r-platform-m6a-r2 (2026-11-08), after fixer-m6a. All seven round-1 majors were checked and are fixed (see
`docs/build/reports/r-platform-m6a-r2.md`). The new majors have failing tests in `tests/review/M6a/r-platform/test_r2_platform.py`.
Probe: `out/_wip/r-platform-m6a-r2/probe.py`.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m6 (still open) | `intent_block._validate_section`, `server.py` `/api/intent` | The round-1 fix rejects the literal `Infinity`, because `loads_strict` runs on every POST body. `1e999` still parses to `inf`, and `/api/intent` never calls `all_finite`. It answers **200 ok** and lists the stages to re-run, but writes `### S02 1.000-inf s`. Neither the viewer parser nor M6b `_VB_SEC` can read that back, so the section's meaning is dropped without warning. | `probe.py`: `intent t1=1e999 (200, ... "sections": {}} ...)`, and the file ends with `### S02 1.000-inf s` | Call `all_finite(body)` for every POST, or `math.isfinite` on t0 and t1 in `_validate_section`. |
| m9 | `edit.js` `commit`/`save` | A second edit made while an earlier save is still in flight is sent with the old etag. One of the two then gets **409** and the toast says "Not saved: overrides.json changed on disk since this page loaded". When the later request lands first (it carries both edits), the toast is wrong because both edits are on disk. `history.pop()` in the failure branch also removes the wrong entry. Saves usually take about 10 ms, so the window is small, but atomic writes slowed by Defender retries widen it. | Claude_Browser: first POST delayed 400 ms, then "+10" and "pin at playhead". Disk had both edits, and the page showed a red "Not saved … changed on disk" toast. | Queue saves: wait for the in-flight save, then rebase the next mutation on its result and etag. Alternatively, disable the edit controls while `st.saving`. |
| m10 | `edit.js` nudge buttons | Nudge buttons use the offset captured when the panel was rendered (`off`). Two clicks on "+10" during one save write +10 once, not +20, with no message. | Claude_Browser: first POST delayed 400 ms, then "+10" twice. One POST was sent. | Compute the new value from `V.ovr` when the button is clicked. |

Rechecked in round 2: m5 (CRLF to LF on the first intent save) is still open, because `write_intent` uses `read_text`, which translates newlines. m8 (34 × 404 on manifest-less
fixture folders in served mode) is still open; Claude_Browser on real-newton-vs-nye logged 30+ 404s. In file:// mode, real-newton-vs-nye, real-megafauna and synth load
with zero console errors, all 11 lanes, and a playhead synced to audio within 20 ms. In served mode, solo of one stem stays within 1 ms of the mix clock.

## Round 3

Reviewer: r-platform-m6a-r3 (2026-11-08), after fixer-m6a-r2. F-R2-INTENT-ENC is fixed for real. F-R2-UNDO is fixed on the
success path, but the new failure branch for Undo is wrong. That is the new major F-R3-UNDO-FAIL, with a failing test in
`tests/review/M6a/r-platform/test_r3_platform.py` and the `undo-fail` scenario in `cdp_viewer.mjs`. Probes are in
`out/_wip/r-platform-m6a-r3/` (`probe_ro.py`, `probe_intent.py`).

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m5 (now fixed) | `server.py` `write_intent` | The file is now read as bytes, so CRLF outside the managed block is preserved. | `probe_intent.py`: `crlf 200 prefix preserved: True` | none |
| m11 | `server.py` `_decode_user_text` / `write_intent` | A UTF-8 file **with a BOM** (Notepad's "UTF-8 with BOM") is decoded with `utf-8-sig`, and the first viewer save writes it back without the BOM. The text outside the block is otherwise intact, but it is not "byte for byte" as decision V7 promises. Harmless to M5/M6b readers. | `probe_intent.py`: `bom+crlf 200 prefix preserved: False b'# Mine\r\n...'` | Remember whether the BOM was present and write it back. |
| m12 | `server.py` `read_intent` / `edit.js` | The new `warning` field from `GET /api/intent` (`intent.md is not UTF-8 ...`) is never shown by the page. The user learns about the encoding only after typing a meaning and pressing save (red toast with 409; the file stays untouched, which is correct). | Claude_Browser on a served folder with a cp1252 `intent.md`: the page loads (fix OK). `Edit.saveIntent` toast: "Not saved: intent.md is not UTF-8; re-save it as UTF-8 (nothing was changed)". The file bytes did not change (`xxd`). `edit.js` has no reader of `V.intent.warning`. | Show `V.intent.warning` as a note at the top of the voices and meaning editors, and disable their Save buttons. |
| m13 | `server.py` `_get` `/api/intent` | `read_intent()` is still outside any try in the GET handler. An `OSError` such as a `PermissionError` on a locked `intent.md` drops the connection, and `boot()` then shows the fatal page, the same failure as F-R2-INTENT-ENC through another exception. The POST path already maps `OSError` to 503. | Code reading: `return self._json(200, srv.read_intent(), head)` has no handler. Not reproduced, because Notepad and VS Code do not hold an exclusive lock. | Wrap it like POST: on `OSError`, return `200 {voices:{}, sections:{}, error}`. |
| m6 (still open) | `intent_block._validate_section` | `t1 = 1e999` still answers 200 and writes `### S02 1.000-inf s`, which no parser reads back. | `probe_intent.py`: `1e999 200`, and the file holds `### S02 1.000-inf s` | `math.isfinite` on t0 and t1. |
| m8 (still open) | `data.js` `boot` | Served real fixtures without `manifest.json` log 34 × 404. | Claude_Browser on real-megafauna in served mode: the 404s are listed in the network log. All 11 lanes are present, there are no lane errors, and audio plays with the playhead synced (A 2.4626 s, V.t 2.4606 s). | as before |

Rechecked in round 3: the edit-mode synth page and the real-megafauna page load and play in Claude_Browser. The ANSI-intent folder loads in edit mode. All 65 tests
in `tests/unit/viewer` and `tests/review/M6a` from rounds 1 and 2 pass. The Claude_Browser pane refused `file://` URLs in this session, so file:// mode was
covered by the headless-Edge tests in `test_browser_viewer.py` (pass).
