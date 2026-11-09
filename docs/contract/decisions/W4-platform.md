# W4 platform (RUNTIME, M6a): decisions

Owner: w4fix-platform (W4 round 1). No file format or schema changed; the folder contract (CONTRACT §§1-7) is
untouched. These are runtime behaviours plus one additive helper in `src/mvh/contract/curvefile.py`.

## Decisions

- **W4-P1 (W4D-1) Stages that are not current keep their curves.** `finalize.pack_curves` packs, for every stage this
  run left stale, pending (not run) or failed, the channels of its last committed cache entry (`latest.json`
  pre_key), as long as that entry still exists, the stage is still published and every kept channel has the length
  the current `meta/source.json` implies at its file's rate (`conventions.n_curve_frames`). This matches the events
  and meta files such stages already keep in the folder. A curve file is deleted only when no stage, current or kept,
  produces it. The manifest warns `curves of stages not current in this run kept from their previous run: ...`.
- **W4-P2 (W4P-2) Held curve files.** `curvefile.pack(entries) -> (index, {path: bytes})` and
  `curvefile.index_bytes(index)` are new (additive; `assemble` is now pack + write and keeps its signature and
  output). The runner writes the curve files itself through `mvh.io.atomic.write_bytes` (unique temp names, retried
  replace), skips files whose bytes did not change, and on a PermissionError keeps the previous file and swaps the
  previous `curves/index.json` entries for that file into the new index, with a warning. `curvefile._atomic_write`
  (used by `assemble`) now uses a unique temp name, retries the replace and never leaves the temp file behind.
- **W4-P3 (W4P-2) One run per song folder.** `mvh.runner.locks.song_lock` (`<song>/.cache/song.lock`, O_EXCL,
  `{"owner","pid","started"}`) is taken by `run.analyze`, so `mvh analyze`, `mvh meaning`, `mvh frames` and the
  viewer's Re-run serialise on a folder. Reentrant within a process; stale only when the owner pid is dead (no age
  limit: a run can wait hours for heavy slots). The waiter prints one message. `MVH_SONG_LOCK_TIMEOUT` (seconds)
  bounds the wait: `locks.SongBusy`, `mvh analyze` exits 75. `StageCache.prune` is unchanged: under the song lock
  every other staging dir of a stage is a leftover of a dead run.
- **W4-P4 (W4P-1) The song file is keyed on its content.** `Runner._external_hashes` records `param:input` as
  `{"sha256"}` (no file name); `param:lyrics` keeps `{"sha256","name"}` because its extension picks the parser
  (`run.CONTENT_ONLY_PARAMS`). `Runner._content_equivalent`: when a stage with a content-only input has no entry under
  its new pre_key, its latest committed entry is reused if the key inputs differ only in that input's name (older
  folders, keyed with the name) or the recorded file is missing. The reused entry keeps its pre_key and key, so nothing
  downstream re-runs, and a forced re-run writes into the same entry and keeps the key. A missing file adds a manifest
  warning naming the file and the relink command. When the stage must actually run and the file is missing, it fails
  without starting, with `Relink it: mvh analyze "<new path of the song file>" --out "<folder>"`.
  Consequence: `meta/source.json file_name` keeps the name of the analysis that made the entry.
- **W4-P5 (W4D-4) `mvh pack <folder> <dest>`** is a new core verb (`CORE_VERBS`): it copies the web subset of a song
  folder (everything but `.cache/`, `stems/`, `viewer.html` and hidden files; `--with-stems`, `--with-viewer`,
  `--force`). RUNS.md §8 documents serving (HTTP with Range; file:// cannot `load()`) and shipping.

## Round 2 (w4fix-platform-r2)

- **W4-P6 (W4VP-1) The manifest lists the kept outputs of stages that are not current.** `finalize.build_manifest`
  lists, for every stage this run left stale, pending or failed, its published outputs (`_published.json`) that are
  still on disk, under the same `_last_good` rule pack_curves uses (last committed entry exists, stage still
  published). Entries are unchanged in shape (no per-file marker: `status.stages` already carries the stage status and
  the token budget matters). The kept-curves warning moved from pack_curves to build_manifest and now covers files and
  curves: `outputs and curves of stages not current in this run kept from their previous run: <stages>`. CONTRACT D34
  amended. A file a validation failure unpublished is never listed (the stage leaves `_published.json`).
- **W4-P7 (W4VP-2) A song lock whose pid was reused is stale.** `locks.pid_started(pid)` (Windows GetProcessTimes,
  Linux /proc) gives the process creation time; a live pid whose process started more than 2 s
  (`PID_REUSE_SLACK_S`) after the lock's `started` cannot be its owner (the owner writes the lock after it starts),
  so the lock is removed. Unknown creation time (access denied): the lock is treated as held, as before.
- **W4-P8 (W4VP-3) Every verb reports a busy folder the same way.** `cli.main` catches `locks.SongBusy` for every
  verb (module verbs `mvh meaning`, `mvh frames` included): one message, exit 75, no traceback.
- **W4-P9 (W4VP-4)** When a stage whose input file is missing must run (`--force ingest`) and fails with the relink
  command, the runner drops the "the cached canonical audio is used" warning resolve() added for it.

## Change requests (other owners)

- **M6b (skill/mv-harness, owner of SKILL.md and references/RECIPES.md): W4D-2, W4D-3, W4D-4.** The failing test is
  `tests/review/W4/dogfood/test_w4d_skill_docs.py`. The text to add is in `docs/build/reports/w4fix-platform.md`
  ("Proposed skill text").
