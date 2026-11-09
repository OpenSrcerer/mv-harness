# r-platform-m6a-r4: R-PLATFORM review of M6a Viewer, round 4 (W3 verify)

Verdict: **pass-with-fixes**. F-R3-UNDO-FAIL is fixed. There is one new major, in the seam where the voices stage reads the
viewer's voice mapping. There are two new minors (m14, m15) and two earlier minors that are still open (m6, m7).

## F-R3-UNDO-FAIL: fixed (verified with the real server)
- **Code.** `edit.js`:
  - `undo()` passes the entry it popped to `save(doc, 'undo', prev)`.
  - The failure branch pushes back that entry (`if (popped != null) st.history.push(popped)`).
  - `undo()` returns at once while `st.saving` is set.
  - This is a general fix, not one written for the test.
- **Test.** `test_r3_platform.py::test_a_failed_undo_keeps_the_state_it_was_restoring` passes, as do all 15 tests in `tests/review/M6a/r-platform`.
- **Real server.** On a served copy of the integrator's megafauna folder:
  1. I made edits of 10, 20 and 30 ms and set `overrides.json` read-only.
  2. Undo got the real 503 (PermissionError) after 13.2 s. A second Undo sent 50 ms later was ignored.
  3. I cleared the flag. Undo, Undo, Undo then gave 0.02, 0.01 and null on disk (correct).
- **Ctrl+Z.** Two Ctrl+Z presses 5 ms apart now give one Undo. The following ones step 0.02, 0.01, null, with no 409.

## New major: F-R4-VOICE-FLOOR
Mapping voices to characters in the viewer makes the voices stage drop the voices the user did not map.
- **Location.** `src/mvh/stages/voices/intent.py::_merge_viewer_block`, which writes `n_voices = max mapped voice`, and
  `src/mvh/stages/voices/core.py` (`elif n_int:`), which uses that value as an exact k.
- **What D51 promises.** The voices the viewer maps are a FLOOR for the voice count.
- **What happens.** The floor goes into `n_voices`, which `core.run` treats as the user's exact count (`n_source=intent`,
  `K.agglo(E, k)`). On a song with 4 singers:
  - mapping V1 to a character makes the next run cluster everything into 1 voice;
  - mapping V1 and V2 gives 2 voices;
  - mapping V2 and V3 gives 3 voices.
- **Consequences.** The other singers' lines are folded into the mapped voices. Voice ids are reassigned by first appearance,
  so the user's mapping can point at a different cluster. No warning is shown.
- **How likely.** This is the normal workflow: in the Voices panel the user maps the voices they recognise first.
- **Real song.** On newton-vs-nye (4 voices), I mapped V2 and V3 through the served viewer. `parse_intent` then returned
  `n_voices=3`.
- **Test.** `tests/review/M6a/r-platform/test_r4_platform.py` uses a fake ctx with 4 separated singers and a fake embedder.
  It is fast and needs no model. The baseline with no intent finds 4 voices and passes. The 3 viewer-mapping cases fail
  with 1, 2 and 3 voices.
- **Fix.** Keep the viewer floor separate from the user's stated count. For example, `n_voices_min` is used as
  `k = max(floor, estimate)`, and only an explicit count ("3 voices", or a template's `characters:` count) forces k.

## Minors (docs/review/M6a-r-platform.md, Round 4)
- **m14.** `st.saving` is one boolean. With overlapping saves, an Undo pressed between them empties the undo history:
  edit A stays on disk and can no longer be undone. Verified in Claude_Browser with an 800 ms delay injected on the second POST.
- **m15.** An Undo or Ctrl+Z pressed during a save is dropped with no message.
- **m6 (still open).** `t1: 1e999` on `/api/intent` still answers 200.
- **m7 (still open).** A `viewer.html` copied alone logs 2 `ERR_FILE_NOT_FOUND` errors before it falls back to the inline preview.

## W3 regression check on real songs
- **Rebuild.** I copied the integrator's megafauna and newton-vs-nye folders to `out/_wip/r-platform-m6a-r4/`.
  - The runner refused `mvh analyze <folder> --only viewer`, because upstream stages are stale in the integrator cache:
    structure, lyrics and others changed after the integrator's run.
  - So `build_real.py` rebuilt `viewer.html` with the current viewer stage.
- **Served mode (Claude_Browser).** On both songs:
  - all 11 lanes are present, with no console errors and no lane errors;
  - audio plays from `audio/mix.flac`, and the element time and `V.t` agree within 9 ms;
  - newton-vs-nye shows 4 voices over 53 lines.
- **file:// mode.** Claude_Browser refuses `file://`, so I used headless Edge (`file_probe.py`). Inside the song folder,
  both songs are ready, play and stay synced, with no console errors. A copy of the file alone (Unicode folder) shows only m7.
- **D52 `--no-lyrics-to-agents`.** `privacy_probe.py` checked the 62 inlined data files with `inline_lyrics=false`.
  None contains a whole lyric line or more than 10 distinct long lyric words. The probe prints counts only.
- **Override keys.** Every key the viewer writes is in a stage's `override_keys` and is read by that stage.
- **Integration tests.** There is no `tests/integration/M6a`. The M6a seam S10 is covered by
  `tests/integration/M5/test_voices_intent_seams.py`, and that test asserts the parser value (`n_voices == 3`), not the
  clustering. That is why F-R4-VOICE-FLOOR got through.

## Gate (`scripts\gate.ps1 M6a`, log `out/_wip/r-platform-m6a-r4/gate.log`)
- fixture PASS, validate PASS, **e2e PASS** (synth, 1800 s), lib-node PASS.
- unit: viewer 51/51 pass. The contract unit step fails on test_deps_match_plan (vocals now depends on lyrics) and on gen --check (CONTRACT.md out of date). Neither is M6a.
- review: 16 pass. The only failures are the 3 cases of the new F-R4-VOICE-FLOOR test (intended).
- ruff: 2 errors, both in the notes stage (import order). Not M6a.
- determinism FAIL: 46 of 181 files differ upstream (lyrics, voices, lipsync, structure, tempo ...). viewer.html differs only because it inlines them: building viewer.html twice from the same folder gives identical bytes (det.py, newton-vs-nye and synth).

## Files
- Test: `tests/review/M6a/r-platform/test_r4_platform.py`
- Probes: `out/_wip/r-platform-m6a-r4/{build_real.py,intent_roundtrip.py,privacy_probe.py,file_probe.py}`
- Minors: `docs/review/M6a-r-platform.md` (Round 4)

Servers stopped and the browser pane closed. No production code was changed.
