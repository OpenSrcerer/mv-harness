# w4fix-platform report (W4 fixer, platform group M6a + RUNTIME, round 1)

## Findings and outcome

| Id | Severity | Outcome | Test |
|---|---|---|---|
| W4D-1 | major | fixed (runtime) | tests/review/W4/dogfood/test_w4d_stale_folder_keeps_curves.py passes |
| W4P-1 | major | fixed (runtime) | tests/review/W4/platform/test_w4p_input_relocation.py 2/2 pass |
| W4P-2 | major | fixed (runtime) | tests/review/W4/platform/test_w4p_finalize_held_and_concurrent.py 2/2 pass |
| W4D-2 | major | not my path: change request to M6b (skill/) | tests/review/W4/dogfood/test_w4d_skill_docs.py (1 test) still fails |
| W4D-3 | major | not my path: change request to M6b (skill/) | same file (1 test) still fails |
| W4D-4 | major | runtime half done (`mvh pack`, RUNS.md §8); doc half is a change request to M6b | same file (1 test) still fails |

`skill/mv-harness/**` belongs to M6b (PLAN §672, builder-m6b). It is not in this fixer's owned paths, so the three
skill-doc tests stay failing until the M6b owner (w4fix-words, or the W4 integrator) applies the text below.

## What changed (all in owned paths)

- `src/mvh/runner/finalize.py` (`pack_curves` rewritten):
  - Stages this run left stale, pending or failed contribute the curves of their last committed entry (latest.json), the
    same entry whose events and meta files stay in the folder. A kept channel must fit the current timebase
    (`n_curve_frames` at its file's rate) or it is dropped with a warning. A curve file is deleted only when no stage
    produces it any more. The manifest warns which stages' curves were kept.
  - The curve files are written through `mvh.io.atomic.write_bytes` and only when their bytes changed. A held file
    (PermissionError) keeps its previous version. Its previous `curves/index.json` entries go into the new index, and
    a warning names the file. An unlink of a held stale file warns and does not crash.
- `src/mvh/contract/curvefile.py`: additive `pack(entries) -> (index, {path: bytes})` and `index_bytes(index)`;
  `assemble` = pack + write (same signature and bytes). `_atomic_write` now uses a unique temp name and retries the
  replace, and it never leaves the temp file behind. Recorded in docs/contract/decisions/W4-platform.md (W4-P2).
- `src/mvh/runner/locks.py`: `song_lock(song_dir, owner, timeout, poll, say)` (`<song>/.cache/song.lock`): reentrant,
  stale only when the owner pid is dead, one waiting message, and `MVH_SONG_LOCK_TIMEOUT` raises `SongBusy`.
- `src/mvh/runner/run.py`:
  - `analyze()` holds the song lock around Runner init, `_run.json`, run and finalize. That covers analyze, meaning,
    frames and the viewer's Re-run, which all go through `rr.analyze`.
  - `CONTENT_ONLY_PARAMS = ("input",)`: the song file is keyed as `{"sha256"}` only. `param:lyrics` keeps its name.
  - `_content_equivalent`: when the new pre_key has no entry, it reuses the latest committed entry if the key inputs
    differ only in the input's name (older name-keyed folders) or if the recorded file is missing. The entry keeps its
    pre_key and key, so nothing downstream re-runs, and a forced re-run keeps the key too. A missing file adds a
    manifest warning with the relink command.
  - A stage that must run while its required input file is missing fails before it starts. The message names the
    file and gives `Relink it: mvh analyze "<new path of the song file>" --out "<folder>"`.
- `src/mvh/cli.py`: `SongBusy` makes `mvh analyze` exit 75. `mvh analyze <file> --out <folder>` without `--slug` keeps
  the folder's recorded slug, so relinking a renamed song does not rename the folder's slug (found on the real
  Newton rename run). The new core verb `mvh pack <folder> <dest>
  [--with-stems] [--with-viewer] [--force]` copies the web subset of a folder: no .cache/, stems/, viewer.html or
  hidden files.
- `docs/RUNS.md`: §1 lists the pack verb. §5 covers kept files of stale stages, moving or renaming the song, and one
  run per folder. §6 has three troubleshooting rows. The new §8 covers serving (HTTP with Range; file:// cannot
  `load()`; `python -m http.server` has no Range) and shipping (`mvh pack`; lyrics/ holds lyric text).
- `tests/unit/runner/test_w4_platform.py` (10 tests):
  - a held curve file with new bytes keeps its old version and index entries;
  - a scoped run keeps the curves of a stale stage;
  - the song lock re-enters, removes a dead owner's lock and times out against a live owner;
  - a renamed input keeps the ingest key;
  - a legacy name-keyed entry is reused, and a forced re-run keeps that entry;
  - a missing input reuses the cache, and a forced ingest fails with the relink command;
  - pack copies the web subset only;
  - relinking a renamed song keeps the folder slug (10 tests in all).

## Proposed skill text (change request to M6b: W4D-2, W4D-3, W4D-4)

All three tests in tests/review/W4/dogfood/test_w4d_skill_docs.py pass with these edits:

1. RECIPES.md, choreography block (W4D-2): replace
   `const kick = song.curve('drums.kick').frame(frame, fr);` with
   `const kick = song.pulse('kick', t, { attack: 0.01, decay: 0.15 });   // song.kicks(): the ONE kick timeline (manifest.summary.kick_source)`.
   Add the line: "`drums.kick` (stem curve) and `hits.kick` (mix curve) are flash/energy curves only; never cut or
   count on them (UD2: on MEGAFAUNA the kick stem is hat bleed)." In the three.js block, keep `hits.kick` in the
   texture but rename the GLSL uniform comment to "kick flash (hits.kick, a visual curve; cut on song.kicks())".
2. RECIPES.md, "Palette and meaning per section" (W4D-3): replace the palette line with
   `const palette = m.palette_hint.length ? m.palette_hint : meaning.palette.length ? meaning.palette : song.manifest.summary.palette;   // last: the cover-art palette`.
   Add: "While meaning is pending (every new song), both are empty: use the cover-art palette
   (`manifest.summary.palette`, also printed in brief.md) until the user authors one." In SKILL.md §3 add one
   sentence with the same rule.
3. SKILL.md §1 or §5 and RECIPES.md Remotion (W4D-4): add a "Serving and shipping" note:
   - `load()` fetches over HTTP: file:// cannot load a song (viewer.html excepted);
   - the server must support HTTP Range requests or `audio.currentTime` seeks silently stay at 0; `python -m
     http.server` has none, while `npx http-server`, `npx serve`, Vite and Remotion do;
   - copy only what a page loads with `mvh pack out/<slug> public/song`. That is manifest.json, lib/, curves/,
     events/, meta/, lyrics/, meaning/ and audio/mix.flac, never stems/ (hundreds of MB) or .cache/.
   Replace "Copy the song folder to `public/song/`" with "`mvh pack out/<slug> public/song` (no stems/ or .cache/)".
   Add `pack` to the verb list in SKILL.md §1.

## Verification

- W4 review tests:
  - test_w4d_stale_folder_keeps_curves 1/1 pass;
  - test_w4p_input_relocation 2/2 pass;
  - test_w4p_finalize_held_and_concurrent 2/2 pass;
  - test_w4d_skill_docs 0/3 pass (M6b path, change request above).
- Unit tests: tests/unit/runner, io, cli, ingest and contract pass (154, before the slug test). The new test file
  tests/unit/runner/test_w4_platform.py passes 10/10, and cli passes. ruff is clean on src/mvh/runner, cli.py and
  the new tests.
- gate W1b (out/_wip/w4fix-platform/gate-W1b.log): fixture, unit, review (tests/review/W1b), ruff, contract,
  validate, e2e and lib-node all pass. determinism FAILS: 28 of 183 files differ, all of them events, brief, lyrics,
  meaning, manifest and viewer, and no curve file differs. The cause is the other W4 fixers editing dynamics,
  structure, spectral, drums and rhythm (src mtimes 18:00-18:17) between the e2e run and the `--force` run.
- gate M6a (out/_wip/w4fix-platform/gate-M6a.log): unit, review, contract, validate, e2e and lib-node pass.
  determinism FAILS (12 files differ: counts, cues, grooves, hit_points, holds, moments, notes.vocals, singing,
  vocal_phrases, manifest, meaning and viewer). The cause is the same: choreo, drums, vocals and structure were
  edited 18:19-18:27 while the gate ran. ruff FAILS on src/mvh/stages/structure/__init__.py:653, another fixer's
  edit in progress.
- Determinism of the runtime itself (out/_wip/w4fix-platform/det): a 20 s tone through ingest, identity and
  loudness, analysed and then `--force`d, gives 0 of 83 files differ.
- Real song (Newton vs Nye, copy of out/_wip/ud2-kick/newton-vs-nye at out/_wip/w4fix-platform/newton-stale):
  - `mvh meaning` on the stale rc.2 copy (the W4D-1 evidence scenario): all 7 curve files byte-identical, index.json
    differs only in schema_version rc.2 -> rc.3, and validate gives 0 errors. Before the fix, curves/ was emptied.
  - Full re-run on rc.3: exit 0, 25 done, frames pending (on demand), no .tmp left, song.lock released. Ingest is
    now keyed `{sha256}`.
  - The same bytes under a new file name, `--out` the folder: ingest, identity, loudness, separate_fast, allin1,
    separate_hq, stem_activity and instruments were cache hits. Stages re-ran only where other fixers had bumped
    versions meanwhile. validate gives 0 errors.
  - Renamed file deleted, `mvh analyze <folder>`: ingest done from the cache, with the manifest warning naming the
    missing file and the relink command. rc 0, validate 124 files, 0 errors.
- No real folder is on rc.3 except this copy: integrator, ud2-kick and the reviewer folders are all keyed on rc.2,
  so every stage is stale there and a full re-run is due anyway. The ingest key change adds no extra cost.
