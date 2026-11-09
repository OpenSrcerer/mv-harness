# W4 final review: R-PLATFORM (r-platform-w4)

Lens: PLAN §11 R-PLATFORM (Windows paths and Unicode, subprocesses and the ffmpeg resolver, env and lock hygiene, the
sep worker, determinism, cache keys, disk, supply chain, doctor, viewer in the browser). Contract 1.0.0-rc.3 (after
ud1-meaning and ud2-kick). Evidence folders: `out/_wip/r-platform-w4/`. No lyric text appears here.

Verdict: **pass-with-fixes**. Determinism, Unicode paths, the CPU sep fallback, cache invalidation and the R19 correction
loop all work on real runs. Two RUNTIME majors (with failing tests) concern the robustness of re-running a song folder.

## Majors (failing tests under tests/review/W4/platform/)

### W4P-1 (RUNTIME, major): a folder cannot be re-run after its song file moved or was renamed; a rename re-runs everything
- The folder records the input as an absolute path (`.cache/_run.json params_ext.input`). After the file is moved,
  renamed or deleted, `mvh analyze <folder>` (RUNS.md §5 and the viewer's Re-run button) fails ingest with
  "StageError: ingest needs an input file (mvh analyze <song>)" and every other stage becomes pending; run.json and the
  manifest then list all 25 stages as pending although the published files are intact.
- Pointing at the renamed file (same bytes) re-runs every stage: `Runner._external_hashes` stores
  `{"sha256", "name"}` for `param:` inputs, so the ingest key changes with the file name and the cascade re-runs the
  whole DAG (about 45 min for a real song). The old ingest entry is pruned, so renaming back re-runs everything again.
  (W1b minor 5, now with the R19 loop on top of it.)
- Evidence: `out/_wip/r-platform-w4/moved/` (ingest failed, then `loudness` re-ran after a rename).
- Test: `tests/review/W4/platform/test_w4p_input_relocation.py` (2 tests, 14 s, both fail).
- Fix: key ingest on the content hash only (the name goes to meta/source.json, not the key); when the recorded input is
  missing but its sha256 matches the cached ingest entry, reuse that entry (warn "input moved; using the cached audio");
  otherwise say which recorded path is missing and how to relink (`mvh analyze <new path> --out <folder>`).

### W4P-2 (RUNTIME, major): a held curve file or a second run on the same folder crashes `mvh analyze`
- finalize packs curves through `mvh.contract.curvefile._atomic_write`: a fixed temp name (`curves/core.f32.tmp`) and
  a bare `os.replace` with no retry and no PermissionError handling (publish got that in W1b M1; this path did not).
  Holding `curves/core.f32` open (a player, an editor, Defender, an agent's preview, another mvh run) makes analyze exit 1
  with a traceback after every stage has finished, and `curves/core.f32.tmp` stays in the song folder.
- There is still no per-song lock (W1b minor 8). The viewer's Re-run button makes a concurrent terminal run realistic.
  Measured on a Newton copy (`out/_wip/r-platform-w4/cachetest`, two `analyze --force cues,choreo,brief,viewer,meaning` at
  once): both exit 1; one crashes in finalize on the shared `core.f32.tmp`, the other fails `meaning` with "publish
  failed: FileNotFoundError" (the other run's commit replaced the cache entry), and the manifest lists meaning / brief /
  viewer as pending. A third clean run repairs it (cache).
- Test: `tests/review/W4/platform/test_w4p_finalize_held_and_concurrent.py` (2 tests: held file; three concurrent runs on a
  tone folder), both fail.
- Fix: `curvefile._atomic_write` -> `mvh.io.atomic.write_bytes` (unique temp, `replace_retry`); finalize treats a held
  curve file like publish does (keep the old file, warn). Add `.cache/song.lock` (the lock helpers) taken by
  `analyze`, `meaning` and `frames`; a second run waits with a message (or refuses with exit 3); `StageCache.prune` removes
  only this run's staging dirs.

## Seam items re-checked (W3 open list), still real
Checked on fresh rc.3 runs (Newton det-a) and on the ud2-kick max folders (rc.2 + UD2 code for M2/M3a, unchanged since):
- S06 (M1): resolved by UD2 as designed: kick_source drums on every song, MEGAFAUNA agreement 0.46/0.25 flagged
  `qa:kick_sources_disagree`. Not a finding.
- S16 (M5, major): Newton per-voice mouths still both open for 2.3 s (critic `test_w3c_per_voice_mouths_do_not_overlap_at_handoffs`
  fails on the fresh run).
- S17 (M2, major): groove ids MEGAFAUNA 48 for 62 groove bars, Versatile 32 for 80 (UD2's kick gate did not cluster them).
- S18 (M2, major): Newton `meta/tempo.json feel = normal`; 76 % of strong on-beat snares on beat 3 (critic feel test fails).
- S19 (M3a, major): Jeremy hats 0.37 on the 16th grid (kick 0.91, snare 0.90); MEGAFAUNA 0.62, Newton 0.85.
- Newton lyrics grade C (M5, minor): G2 0.7479 against 0.75, identical in both fresh runs (deterministic, borderline).
- m5 licences (supply chain, minor): 5 entries still unclear / not verified (demucs htdemucs and htdemucs_6s weights,
  sep kimberley vocals, sep karaoke, sep DrumSep). Recorded in run.json `licences`.

## Verified OK (by running code)
- **Determinism (two full max runs of a real song).** Newton, fresh, two different folders (`det-a`, `det-b`), run
  concurrently with each other and with other agents' runs (heavy-slot queueing, GPU contention): 188 of 188 files
  byte-identical (excluding run.json and .cache; only my own `.seeded` marker differs). analyze 0 / validate 0 (124 files)
  each; 2666 s and 2984 s wall under contention. No absolute paths in public outputs.
- **Unicode / spaces.** Synthetic song from `in dïr ♪/曲 tëst ♪.flac` into `uni üñ ♪ 曲-max/`, full max profile:
  analyze 0, validate 0 (119 files); Rhubarb visemes, sep worker, whisper and the ffmpeg resolver all fine;
  `meta/source.json file_name` keeps the Unicode name; `_scratch` empty afterwards.
- **Sep CPU variant (forced once).** `MVH_SEP_VARIANTS=cpu`, synthetic song, `--only ingest,separate_hq`: done in 2302 s
  (sw_6stem alone 523 s for 57 s of audio on CPU); run.json `variant: cpu`; key device `cpu` (no mixing with the ROCm
  entry). Stems vs the ROCm run: -84 to -106 dB relative difference, except the karaoke lead/backing split (-47 / -43 dB)
  and guitar (-61 dB). Sum invariant identical (-35.33 dB).
- **Cache keys.** A copy of a finished folder at another path: 25/25 hits. `--param cues.top_moments=12` re-ran exactly
  cues, meaning, brief, viewer and the param was kept on the next plain re-run (0 re-runs). `--param
  harmony.key_override="A minor"` re-ran exactly harmony's 12 descendants (key A minor, `key:overridden`). Old entries are
  pruned (one key per stage). The folder path is not in any key.
- **R19 correction loop in the browser** (Claude_Browser, `mvh view` edit mode on a Newton det-a copy): added a boundary at
  48 s, pinned a cue at 100 s, mapped V2 -> C2 "Narrator ☃" through the edit pane; pressed Re-run: exit 0, cache hits up to
  notes, then structure, lyrics, mood, vocals, choreo, cues, voices, lipsync, meaning, brief, viewer re-ran. After reload:
  section S05 starts at 48.78 s (downbeat-snapped), cue at 100.0 s tier 1 sourced from overrides.json, character C2 named
  "Narrator ☃", edit bar "no edits", 0 lane errors on all 11 lanes + overview at 3 zoom windows, validate 126 / 0.
- **Viewer lanes.** All 11 lanes (sections, meaning, lyrics, beats, hits with the UD2 "kick (drums)" row, bands, loud,
  instruments, notes, vocal, cues) draw with 0 lane errors across whole-song and zoomed windows; values panel at 5
  times; edit pane controls present.
- **Server security** (`out/_wip/r-platform-w4/probes/probe_server.py`): bad Host 403; POST without token 403; bad / `null`
  Origin 403; body > limit 413; re-run disabled 403; OPTIONS preflight 501 (so no cross-origin POST); `..`, `%2e%2e`,
  `..%5c`, `::$DATA`, `C:/`, UNC-style paths 404; NaN and 1e999 rejected 400 (M6a m6 fixed).
- **Env and lock hygiene.** `uv lock --check --offline` in sync (uv.lock unchanged); both sep lock copies equal
  `envs/sep/{rocm,cpu}/uv.lock`; doctor: main 141 packages, sep-rocm 63, sep-cpu 80 in sync; ROCm matmul OK
  (torch 2.11.0+rocm7.13.0, RX 9070).
- **Supply chain.** models.lock.json: 28 entries, 81 files, every file has a 64-hex sha256 and a size; `mvh doctor`
  (full) verifies 81/81; HF URLs pinned to commit revisions.
- **Earlier platform review tests** (tests/review/w1b, tests/review/M6a): 39 passed, 1 skipped (16 min).

## Minor findings (no tests)
1. **8.3 short names bypass the viewer's dot-folder filter** (M6a). `GET /CACHE~1/ingest/latest.json` answers 200 with
   the cache record (absolute input path, key inputs); any cache entry is reachable once its key is known (e.g.
   `.cache/lyrics/<key>/...` even under `--no-lyrics-to-agents`). Local-only (127.0.0.1 + Host check), so minor. Fix:
   compare the resolved path's parts (after `resolve()`) against the dot/underscore rule, not the URL's parts.
2. **The viewer's idle timeout kills a running re-run** (M6a). `ViewServer.wait()` shuts down after 900 s without a
   request even while `rerun.running`; the CLI then exits and the Job Object (KILL_ON_JOB_CLOSE) kills the analyze tree.
   Closing the tab after pressing Re-run loses the run (resumable from the cache). Ctrl+C on `mvh view` does the same,
   silently. Fix: do not idle out while a re-run runs; print that Ctrl+C stops the re-run.
3. **The edit bar's "These stages will re-run" lists only the last save's stages** (M6a). After a boundary edit then a pin,
   it showed cues, meaning, brief, viewer; the re-run actually ran structure and 10 more. `st.affected` is replaced on
   each save. Fix: union with the previous list, or call `api/status` after each save.
4. **"Check stages" always lists `frames` as stale** ("never run"): the on-demand stage is counted (M6a, `status()` filter).
5. **RUNS.md §3 "Disk" says re-runs keep old cache entries**; `StageCache.prune` keeps only the newest key per stage, so
   undoing a param re-runs everything it touched (RUNTIME doc).
6. **Vendored wheels are not hash-pinned** (RUNTIME supply chain): `uv.lock` path sources carry no hash and doctor does
   not check `vendor/wheels/*.whl`; the SHAs live only in docs/spike/main.md (prefix). Today: all-in-one-infer c41d6203...,
   demucs-infer ba34e159..., madmom-infer f4013a7a.... Fix: record full SHAs in models.lock-style metadata and verify in doctor.
7. **doctor truthfulness (W1b m6, still)**: full mode prints `hashing <file>` but uses the size+mtime sha cache; "heavy
   locks" is always OK; the ROCm smoke matmul runs without `gpu.lock`; `--quick` drops the ROCm line instead of SKIP.
8. **`ROCBLAS_USE_HIPBLASLT` is set with `setdefault`** in the sep worker: an inherited `=1` silently undoes D74's
   reproducibility. Force it to "0" (or warn) (M3a/RUNTIME).
9. **W1b minors still open**: m1 stale-lock takeover race; m3 `device_class` = first venv present, not the variant that
   ran (a rocm-to-cpu fallback is cached under `rocm`); m4 `--cores` clamps threads into the key; m9 malformed overrides.json
   traceback in `mvh status` (not re-checked); m15 `--force` with `nargs="?"` swallows the song path.
10. **run.json `device.gpu` is null** although ROCm ran (cosmetic).
11. **Slug from a mixed title drops the non-Latin part** (`曲 tëst ♪` -> `test`); `_unique_slug` guards only fully
    non-Latin names. Harmless with `--out`.

## Disk
- Fresh Newton max folder: 1.1 GB (stems + .cache hard links). Unicode synthetic: 0.26 GB. `_scratch` empty after every run;
  staging dirs removed; old keys pruned. mvh home: models 12 GB, plus W0 leftovers in `%LOCALAPPDATA%\mvh\dl` (73 MB of
  commit tarballs no longer used) and `downloads` (Rhubarb zip).
- My evidence folders under `out/_wip/r-platform-w4/` take about 5 GB (det-a, det-b, cachetest, r19, view-newton copies);
  safe to delete after the W4 fixers are done.
