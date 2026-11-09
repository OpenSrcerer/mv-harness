# W4 verify-platform, round 2 (w4verify-platform-r2)

Independent verification of w4fix-platform-r2 (RUNTIME finalize/locks/run, cli) on W4VP-1, plus the minors it also
fixed (W4VP-2..4). No production code was changed. Tests: `tests/review/W4/verify-platform/`; scratch:
`out/_wip/w4verify-platform-r2/`. No lyric text appears here.

## Verdict per finding

| Id | Verdict | How it was checked |
|---|---|---|
| W4VP-1 manifest drops kept files | **fixed** (file listing); two gaps remain (W4VP-7, W4VP-8) and one regression (W4VP-5, major) | fast review test passes. Real copies of integrator rc.2 MEGAFAUNA (`mvh meaning`) and Versatile (`--only meaning,brief,viewer`): manifest.files 111 -> 111 and 118 -> 118, every entry identical to the integrator's, events 42 / 40, `mvh validate` 119 / 126 files and 0 errors, lib eventNames 42 / 40. No test-specific hack: build_manifest reuses `_last_good` and checks existence on disk. |
| W4VP-2 reused-pid lock | **partly fixed** (W4VP-6, minor) | review test passes (an openable process). For a pid the user cannot open (svchost and other services: 135 of 400 live processes here) `pid_started` returns None and the lock stays held forever. |
| W4VP-3 meaning/frames traceback | fixed | the r1 test planted the same lock as the reused-pid test (it contradicted itself, as the fixer said). Corrected to plant a held lock (`started` = now): exit 75, no traceback, for meaning and frames. |
| W4VP-4 cache-used warning on failed ingest | fixed | review test passes; the drop is scoped to `<stage>: the song file ...` warnings of the stage that must run. |

## Regression checks

- **Synth full max re-run** (copy of the r1 rc.3 synth; spectral 1.4.1 made 19 stages re-run): exit 0, file set and
  every manifest entry identical to r1's (111), flags identical, kick_source drums, `mvh validate` 119 files 0
  errors, no `song.lock` or temp file left, no kept-stages warning (all current).
- **Real stale copies** (above): identical file sets; kick_source changes drums -> mix on these pre-D79 folders because
  rc.2 has no meta/drums.json and D79 says mix then (finalize follows the contract; note only, it ends with the rc.3
  re-run).
- **Unit and review suites**: tests/unit/runner, tests/unit/cli and tests/review/W4/platform: 55 pass. The fixer's
  unit file and r1's review tests pass (except the real test that read r1's pre-fix folder; it now reads the r2 copy and
  passes).

## Findings

### W4VP-5 (major, RUNTIME finalize.build_manifest): outputs kept from a DIFFERENT audio are listed (regression of the W4VP-1 fix)
- **Claim.** pack_curves drops a kept stage's curves when they "do not fit the current audio" (another audio is in the
  folder now). build_manifest has no such rule: it lists that stage's events and meta, which were computed from the
  previous audio, and the "outputs and curves ... kept" warning follows right after the "curves ... dropped" warnings.
  The lib loads them as this song's events (kicks of the other audio). Before the fix they were not listed.
- **Evidence.** Tone A (3 s) analysed with `--only ingest,loudness,spectral`; tone B (6 s) analysed into the same
  folder with `--only ingest`: the manifest (duration 6.0) lists events/hits.{kick,mid,high}, events/onsets.* and
  meta/loudness.json of A; curves/index.json is gone; summary.integrated_lufs is A's. The same happens in a full run on
  a new master whenever an upstream stage fails (every later stage is left pending).
- **Fix.** Apply the same rule to the files: skip (and name in a warning) kept stages whose last-good entry was computed
  from another audio (compare the ingest key or pcm_sha256 the entry depends on with meta/source.json; at minimum reuse
  `_fits`).
- **Test.** `test_w4vp_kept_outputs_other_audio.py`.

### W4VP-6 (minor, RUNTIME locks._song_lock_stale): W4VP-2 is only partly fixed
- **Claim.** When the reused pid belongs to a process the user cannot open, `pid_alive` says alive (access denied) and
  `pid_started` returns None, so the lock is held forever. After a reboot the early pids go to exactly such services.
- **Evidence.** 135 of 400 live processes here (77 svchost, csrss, lsass, ...) return no start time. A lock written one
  day before the last boot with the pid of such a process: `mvh analyze` exits 75 after MVH_SONG_LOCK_TIMEOUT=15.
- **Fix.** Also treat a lock as stale when the machine booted after its `started` (GetTickCount64 / /proc/stat btime;
  no process access needed), as r1 suggested.
- **Test.** `test_w4vp_lock_unreadable_pid.py`.

### W4VP-7 (minor, RUNTIME finalize.build_manifest): kept stages lose their flags, warnings and summaries
- **Claim.** The kept files are listed, but `degraded:<stage>`, `fallback:*`, the stage warnings and the summary.stages
  entry still come only from a record of this run, so they vanish while the degraded outputs they describe stay listed.
  The last-good entry that already gives the file list carries them.
- **Evidence.** MEGAFAUNA copy: flags 17 -> 8 (degraded:vocals, degraded:voices and the vocals_stem / asr_no_vad
  fallbacks gone), warnings 7 -> 1, summary.stages 3 -> 0. Versatile: flags 8 -> 5, warnings 6 -> 1, summary.stages
  7 -> 0. On a tone, identity's warning and summary vanish once identity is stale.
- **Test.** `test_w4vp_kept_stage_flags.py` (fast + real).

### W4VP-8 (minor, RUNTIME finalize.build_manifest): a kept on-demand stage is listed without a status
- **Claim.** After `mvh frames --fps 24` and a later `mvh analyze` that changes an upstream, frames/24fps.csv (from the
  previous analysis) is listed but status.stages has no frames entry (non-analyze stages are skipped there unless
  current), against the amended D34 ("status.stages gives their status").
- **Evidence.** r2 synth copy after `mvh analyze --param meaning.foo=2`: `mvh status` frames stale (upstream changed:
  meaning); manifest lists frames/24fps.csv, status.stages has no frames key; only the generic kept warning names it.
- **Test.** `test_w4vp_kept_ondemand_status.py` (real, read-only on the r2 synth copy).

### Notes (no test)
- Duplicate entries are possible in principle: publish() lets a current stage publish a path still recorded for a
  kept stage ("another stage publishes this path now"), and build_manifest would list it twice. Not observed (no
  output moved between stages in rc.3).

---
# W4 verify-platform, round 1 (w4verify-platform-r1)

Independent verification of the W4 platform fixer (w4fix-platform: M6a + RUNTIME) on the six findings W4D-1..4 and
W4P-1..2. No production code was changed. Tests live in `tests/review/W4/verify-platform/`; scratch runs in
`out/_wip/w4verify-platform-r1/`. No lyric text appears here.

## Verdict per finding

| Id | Verdict | How it was checked |
|---|---|---|
| W4D-1 stale folder deletes curves | **curves: fixed; manifest half: NOT fixed (W4VP-1, major)** | review test passes; real `mvh meaning` on a rc.2 copy of MEGAFAUNA and `--only meaning,brief,viewer` on Versatile: every curve and events file is byte-identical and index.json differs only in schema_version. The manifest, however, drops every events, meta and audio file of the stale stages (see W4VP-1). |
| W4D-2 RECIPES kick | fixed (by the M6b side, not by w4fix-platform) | RECIPES.md now uses `song.pulse('kick', t)` / `song.kicks().inFrame(...)` and says that `drums.kick` and `hits.kick` are not the kick. `kicks()`, `Events.inFrame` and `pulse('kick')` exist in `src/mvh/assets/mvh.js`. |
| W4D-3 palette fallback | fixed (M6b side) | The RECIPES chain ends at `song.manifest.summary.palette` and the text explains why. SKILL.md itself does not repeat the rule (the suggested fix asked for it); minor, no test. |
| W4D-4 serving and shipping | fixed (doc by the M6b side; `mvh pack` and RUNS §8 by w4fix-platform) | RECIPES covers Range, file:// and stems/.cache. `mvh pack` on integrator MEGAFAUNA gives 166 files and 42 MB; lib/mvh.js loads it with 42 events and the drums kick (647 kicks). |
| W4P-1 input relocation and rename | fixed; one message is wrong (W4VP-4, minor) | Review tests pass. On a tone: rename and relink are cache hits, and the slug is kept. A missing input reuses the cache. `meta/source.json file_name` keeps the first name, as RUNS §5 documents. With a forced ingest and a missing input, the warning says the cache was used although ingest failed. |
| W4P-2 held file and concurrent runs | fixed; two edge cases (W4VP-2, W4VP-3, minor) | Review tests pass. A held index.json gives rc 0 and validates. On the real synth (all real stages), a second `mvh analyze` started 20 s after the first printed the waiting message and waited for the first run. A song.lock left by a power cut whose pid was reused by another process blocks forever; `mvh meaning` and `mvh frames` print a traceback on SongBusy. |

Test-specific hacks: none found. `pack_curves`, `song_lock` and `_content_equivalent` are general mechanisms, and
nothing in them keys on test names, tone lengths or paths.

## Regression checks

- **Curve packing.** `curvefile.pack` reads the integrator's committed cache entries (latest.json) for synth,
  MEGAFAUNA, Versatile, Jeremy and Newton. Its output is byte-identical to the integrator's `curves/*` (all 7 files
  on every song), and `index.json` is identical except for `schema_version`
  (`out/_wip/w4verify-platform-r1/repack.py`).
- **Real stale folders (rc.2 copies, scoped runs).** Curves and events are byte-identical, no `.tmp` or
  `song.lock` is left behind, and `mvh validate` reports 0 errors, but it checks only 20 files (see W4VP-1).
- **Fixer's rc.3 Newton full run.** 25 stages done and frames pending (on demand). No temp files or lock are left
  behind. The manifest lists 116 files and 42 events, and `kick_source` is drums.
- **Unit suites.** tests/unit/runner, cli and io: 60 pass. The W4 review tests for dogfood and platform pass
  (17 with the fixer's unit file).
- **Real synth, full max run, with a second run on the same folder** (`out/_wip/w4verify-platform-r1/synth*`):
  - run B, started 20 s after run A, printed the waiting message and waited;
  - both runs exit 0. After A finished, B ran 25 cache hits;
  - `mvh validate` checks 119 files and finds 0 errors. No `.tmp` file or lock is left;
  - against the integrator's synth, the file set is the same plus `meta/drums.json` (D79), and the 240 curve
    channels are identical. The degraded stages are the same (notes) and kick_source is drums.

## Findings

### W4VP-1 (major, RUNTIME finalize.build_manifest): the manifest omits the kept outputs of stale stages (W4D-1 half fixed)
- **Claim.** pack_curves keeps a stale or pending stage's curves "matching the events and meta files it keeps in the
  folder", but `build_manifest` lists only the outputs of stages that are current in this run. CONTRACT D34 says
  `files[]` lists the published stage outputs. After the W4D-1 flow (a version bump, then `mvh meaning <folder>`), the
  manifest lists the kept curves and none of the events, meta or audio files that stay on disk next to them.
- **Evidence.** On a copy of integrator MEGAFAUNA after `mvh meaning`:
  - `manifest.files` drops from 124 entries to 12, and the events entries from 42 to 0;
  - `mvh validate` checks 20 files, so the kept files are never validated;
  - with `lib/mvh.js` (`libcheck.mjs`), `song.eventNames` drops from 42 to 0;
  - `kickSource` changes from drums to mix and `song.kicks()` from 647 to 188 kicks. This part comes from the rc.2
    meta/drums.json, which has no kick_source, together with the empty event list.

  On a tone, after loudness goes stale, the manifest lists the loudness curves but not meta/loudness.json.
- **Fix.** For stages that are not current but are still published (the same `_last_good` rule pack_curves uses),
  list their published files too. They could carry a `stale: true` marker, or the stage could be named in a warning.
- **Test.** `tests/review/W4/verify-platform/test_w4vp_stale_manifest.py`: one fast test, and one real test that reads
  the stale-megafauna copy.

### W4VP-2 (minor, RUNTIME locks.song_lock): a power-cut lock whose pid was reused blocks the folder forever
- A lock counts as stale only when its pid is dead. It has no age limit, and the code never checks when the process
  holding that pid started. After a reboot, Windows can reuse the recorded pid for an unrelated live process. Every
  `mvh analyze`, `meaning`, `frames` and viewer Re-run then waits forever, while RUNS §6 says "stale locks clear
  themselves".
- **Fix.** Treat the lock as stale when the live pid's process started after the lock's `started` time
  (GetProcessTimes), or when the machine booted after it. Also print how to remove the lock.
- **Test.** `test_w4vp_song_lock.py::test_power_cut_lock_with_a_reused_pid_does_not_block_forever`.

### W4VP-3 (minor, RUNTIME/M6b CLI): `mvh meaning` and `mvh frames` print a traceback on SongBusy
- `cmd_meaning` and `cmd_frames` call `rr.analyze` without catching `locks.SongBusy`. With MVH_SONG_LOCK_TIMEOUT set,
  they exit 1 with a traceback, while `mvh analyze` exits 75 with a clear message.
- **Test.** `test_w4vp_song_lock.py::test_meaning_and_frames_report_a_busy_folder_cleanly` (meaning and frames).

### W4VP-4 (minor, RUNTIME run.py): "the cached canonical audio is used" printed while ingest failed
- With the input missing and `--force ingest`, `resolve()` adds the content-equivalent warning before the forced run
  fails. The warning stays in manifest.warnings and on stdout next to the failure.
- **Test.** `test_w4vp_missing_input_messages.py`.

### Notes (no test)
- `mvh validate` on a `mvh pack` output reports 17 errors (the manifest still lists stems/ and viewer.html). This is
  expected for a web subset, but pack could write a pruned manifest or a note.
- SKILL.md does not repeat the cover-art palette fallback (W4D-3 suggested fix). It is present in RECIPES.md, which
  the test accepts.
