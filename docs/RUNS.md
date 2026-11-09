# Running mv-harness

How to analyse a song, what it costs, how to correct the result and re-run, and where the outputs are known to be weak.
Numbers come from the W3 integration runs (integrator-r2, 2026-11-09; contract 1.0.0-rc.2) on this machine:
Windows 11, 8 cores budgeted, AMD RX 9070 (ROCm, gfx1201) for the separators. No lyric text appears here.

## 1. Commands

All commands run from the repo root in PowerShell, after sourcing the environment once per shell:

```powershell
Set-Location C:\Users\OpenSrcerer\Desktop\playground\mv-harness
. .\scripts\mvh-env.ps1            # add -Offline to forbid network access (LRCLIB, MusicBrainz, model downloads)
uv run --frozen --no-sync mvh doctor --quick       # ffmpeg, envs, ROCm, whisper, Rhubarb, models, disk
uv run --frozen --no-sync mvh analyze "songs\My Song.flac" --profile max          # -> out\<slug>\
uv run --frozen --no-sync mvh validate out\<slug>
uv run --frozen --no-sync mvh view out\<slug>      # viewer; edit mode saves corrections (section 5)
```

From Git Bash: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python -m mvh.cli analyze ...`.
In Windows PowerShell 5.1 never add `2>&1` to a native command (it turns stderr lines into errors).

| Verb | What it does |
|---|---|
| `mvh analyze <song or folder>` | Runs the stage DAG into `out/<slug>/` (or `--out DIR`). Options: `--profile max\|draft`, `--lyrics FILE` (.lrc/.srt/.vtt/.txt; kept for re-runs, `-` forgets it), `--intent FILE` (copied to `meaning/intent.md`, never replaces a different one), `--meaning-draft agent\|anthropic\|off`, `--no-lyrics-to-agents`, `--param stage.key=JSON` (repeatable, kept for re-runs), `--only a,b`, `--force [a,b]`, `--from stage`, `--no-network`, `--threads N` (per stage, default 3, max 6), `--cores N` (budget shared by concurrent stages, default 8), `--no-heavy-locks`. Prints progress on stderr and one JSON line on stdout. |
| `mvh status <folder>` | done / stale / pending per stage, with the reason (a changed param, version, override, input or upstream). |
| `mvh validate <folder>` | Schema-validates every file of a song folder against the contract. |
| `mvh view <folder>` | Serves `viewer.html` on 127.0.0.1 with a token; edit mode writes `overrides.json` and the managed block of `meaning/intent.md`, and can start a re-run. `viewer.html` also opens read-only from file://. |
| `mvh brief <folder> [--section S05]` | Prints brief.md, or a <= 1.5k-token zoom of one section. |
| `mvh frames <folder> --fps 24 [--frame0 1] [--curves "*"] [--format deforum]` | One row per video frame (`frames/24fps.csv`, `frames/24_f1fps.csv` with `--frame0 1`). |
| `mvh meaning <folder>` | Re-merges `intent.md` + `authored.json`, re-anchors claims to the current sections, refreshes singing / lines / brief. |
| `mvh models fetch\|verify\|list` | The pinned models of `models.lock.json`. |
| `mvh doctor` | Environment check. |

## 2. Profiles

`max` (the default) is the product: every model, ensemble and cross-check. `draft` is for a quick look; it changes only:

| Stage | draft | max |
|---|---|---|
| separate_fast | htdemucs_6s (demucs-onnx) | htdemucs 4-stem (demucs-onnx; feeds allin1) |
| lyrics | `asr: ffmpeg_whisper`, no stable-ts fallback | faster-whisper large-v3 + CTC alignment + stable-ts fallback |
| lipsync | no visemes (mouth-open curves only) | visemes per voice (Rhubarb) |
| identity | no MusicBrainz verification or credits | verification + credits |

Everything else (separate_hq with DrumSep, allin1, S-KEY, lv-chordia, CED, CLAP, ...) runs in both profiles, so draft is
only moderately faster (the table in section 3). Never compare a draft folder with a max folder: the stage cache keys
differ, so switching profile on a folder re-runs the affected stages.

## 3. Timings, disk and the heavy slots

### Wall time per song

| Run | Song length | Profile | Conditions | Wall time | analyze / validate |
|---|---|---|---|---|---|
| Jeremy | 5:17 | draft | almost alone on the machine | 1070 s (17.8 min) | 0 / 0 |
| Jeremy | 5:17 | max | 5 songs at once, 2 heavy slots | 2949 s (49 min) | 0 / 0 |
| MEGAFAUNA | 3:37 | max | 5 songs at once | 2815 s (47 min) | 0 / 0 |
| Versatile | 3:48 | max | 5 songs at once | 2826 s (47 min) | 0 / 0 |
| Newton vs Nye | 2:50 | max | 5 songs at once | 2715 s (45 min) | 0 / 0 |
| synthetic | 0:57 | max | 5 songs at once | 2737 s (46 min) | 0 / 0 |
| any of the five | - | max | re-run, nothing changed | 4-5 s (25/25 cache hits) | 0 / 0 |
| synthetic / Newton | - | max | after a boundary + cue + voice + meaning edit (R19 test) | 192 s / 203 s of stage time (11 stages re-run) | 0 |

The five concurrent max runs took 50 minutes in total. Run alone, one max song costs roughly the draft time plus the
max-only work (lyrics alignment, visemes, notes): about 20-30 minutes for a 5-minute song.

### Seconds per stage

These are `seconds` from run.json: wall time including the runner's heavy-slot wait, with the wait alone in parentheses.
The max columns ran concurrently, so most of their large numbers are queueing. The draft column ran almost alone.

| Stage | Jeremy draft | Jeremy max | MEGAFAUNA max | Versatile max | Newton max | synthetic max |
|---|---|---|---|---|---|---|
| ingest | 3 | 4 | 3 | 3 | 3 | 2 |
| identity | 0 | 1 | 1 | 1 | 1 | 1 |
| loudness | 5 | 7 | 6 | 6 | 5 | 3 |
| separate_fast | 77 | 190 | 431 (wait 370) | 511 (wait 446) | 73 (wait 34) | 20 |
| allin1 | 58 | 95 | 51 | 50 | 38 | 15 |
| separate_hq (sep worker; its waits are inside) | 899 | 1900 | 2355 | 2568 | 1085 | 1464 |
| spectral | 8 | 7 | 8 | 6 | 6 | 3 |
| rhythm | 94 | 1269 | 256 (wait 194) | 437 (wait 372) | 237 (wait 188) | 171 (wait 154) |
| dynamics | 5 | 6 | 6 | 5 | 4 | 2 |
| harmony | 29 | 346 | 162 (wait 134) | 1363 (wait 1336) | 324 (wait 302) | 451 (wait 438) |
| stem_activity | 11 | 13 | 12 | 7 | 7 | 5 |
| drums | 12 | 15 | 12 | 8 | 7 | 5 |
| instruments | 110 | 984 | 86 | 219 (wait 148) | 713 (wait 637) | 123 (wait 92) |
| notes | 10 | 643 | 128 (wait 116) | 9 | 1469 (wait 1462) | 1091 (wait 1081), degraded |
| structure | 24 | 31 | 21 | 23 | 15 | 6 |
| lyrics | 104 (transcribed) | 161 | 185 (wait 54) | 9 (instrumental) | 146 | 39 |
| mood | 3 | 3 | 3 | 369 (wait 366) | 219 (wait 216) | 17 |
| vocals | 19 | 19 | 14, degraded | 8, degraded | 7 | 7 |
| voices | 9 | 9 | 95 (wait 88), degraded | skipped (instrumental) | 699 (wait 691) | 1073 (wait 1067) |
| lipsync | 5 (no visemes) | 142 | 70 (wait 46) | 1 | 43 | 16 |
| choreo, cues, meaning, brief, viewer | <= 1 each | <= 1 each | <= 1 each | <= 1 each | <= 1 each | <= 1 each |
| frames | on demand | on demand | on demand | on demand | on demand | on demand |

Jeremy max's waits were not recorded separately: a no-op re-run replaced `seconds` with `computed_seconds`, which keeps
only the wall time. Without waits, separate_hq is the dominant cost (about 2.8x the song length, mostly DrumSep on the
CPU, D47). Lyrics come next (ASR + alignment, about 0.5x the song length), then notes and instruments. Every other stage
takes seconds.

### Disk per song folder (hard links counted once)

| Song | Folder | of which stems | .cache (shares the published files) |
|---|---|---|---|
| Jeremy max | 2.26 GB | 1.41 GB | 2.23 GB |
| Jeremy draft | 2.48 GB | 1.41 GB | 2.45 GB |
| MEGAFAUNA | 0.87 GB | 0.39 GB | 0.84 GB |
| Versatile | 1.80 GB | 1.21 GB | 1.77 GB |
| Newton vs Nye | 1.12 GB | 0.67 GB | 1.10 GB |
| synthetic | 0.26 GB | 0.07 GB | 0.20 GB |

Jeremy and Versatile are loud masters, so their stems also get float WAV twins (peaks above 1.0); that is why they carry
1.2-1.4 GB of stems. Plan on 1-2.5 GB per song, plus about 12 GB of models.

### Heavy-slot behaviour
- Two machine-wide heavy slots (`%LOCALAPPDATA%\mvh\locks\heavy-0.lock`, `heavy-1.lock`) plus `gpu.lock`. Every stage that
  loads a model or runs a separator takes a slot (the heavy slot first, then the GPU lock); at most 6 threads per slot.
  Several `mvh analyze` processes (or test runs) on one machine share the two slots and queue (`waiting for a heavy
  slot ... retry every 2s` on stderr). A lock whose pid is dead or that is older than 3 h is stale and is removed by
  the next acquirer, so a crash or power cut never blocks later runs.
- `run.json stages.<name>.seconds` is wall time including the runner-level slot wait; `wait_s` is that wait alone
  (D64). Waits inside the sep worker (per model step) stay inside `seconds`. On a cache hit `computed_seconds` repeats
  the time of the run that computed the entry.
- One song alone: the slots are free and the stage times are close to the computed times. Five songs at once (the W3
  runs): the separators queue, so per-song wall time grows to the totals in the table, but the machine is busy the
  whole time.

### Disk
- A song folder holds the stems (FLAC; loud masters also get float WAV twins of stems whose peaks exceed 1.0), the
  curves, events, tables, meta, lyrics, meaning, viewer.html (inlined data, <= 28 MB) and `.cache/` (one directory per
  stage key). Public outputs are hard links into `.cache/`, so they cost no extra space.
- Re-runs with changed params keep the old cache entries; delete `out/<slug>/.cache/<stage>/<old key>` (or the whole
  folder) to reclaim space. Models live in `%LOCALAPPDATA%\mvh\models` (about 12 GB).

## 4. CPU vs ROCm

- The separators (separate_fast, separate_hq) run in a separate worker env, `envs/sep/.venv-rocm` then
  `envs/sep/.venv-cpu`: the first variant that works wins (`MVH_SEP_VARIANTS=cpu` or `config.json "sep_variants"`
  or the stage param `variant_order` change the order). `run.json stages.<sep stage>.variant` records which one ran.
- RoFormer vocal / karaoke models run on the GPU (bit-reproducible with the math SDPA backend and
  `ROCBLAS_USE_HIPBLASLT=0`, which the worker sets: D74). DrumSep (MDX23C) runs on the CPU by default
  (`separate_hq.drumsep_device = "cpu"`, D47): MIOpen picks its convolution kernels by free GPU memory, so GPU DrumSep
  is not reproducible when another program holds GPU memory. `"auto"` puts it back on the GPU (faster, not
  bit-reproducible).
- Everything in the main env (ONNX models, whisper int8, S-KEY, CED, CLAP, RMVPE, allin1) runs on the CPU.
- Without ROCm everything runs on the CPU. The RoFormer models are then much slower (not timed in W3; DrumSep on the CPU alone runs at about 1.45x the song length with 6 threads).

## 5. Re-running and correcting

- **Caching.** Every stage's output is cached under a key of its name, version, contract version, resolved params,
  model hashes, upstream keys, the override keys it reads and the hashes of its external inputs (input file, lyrics
  file, intent.md, authored.json). `mvh analyze <folder>` re-runs only stages whose key changed; a no-op re-run takes
  seconds (all cache hits) and re-finalises the folder. Code changes are NOT in the key: after editing a stage's code,
  bump its version or use `--force <stage>` (or `--from <stage>` for it and everything downstream).
- **`--only a,b`** runs just those stages; their dependencies must be cached and current, otherwise the runner says
  which upstream is stale and runs nothing for that stage.
- **Corrections (R19).** Open `mvh view out/<slug>`, switch to edit mode and:
  - move / add / remove section boundaries and relabel sections (`overrides.json structure.boundaries/labels`, anchored by
    time). Edits are applied locally: no boundary the user did not touch moves (D68);
  - shift the beat grid, set the BPM or the downbeat phase (`rhythm.beat_offset_s`, `rhythm.bpm`,
    `rhythm.downbeat_phase`);
  - nudge lyric lines / words (`lyrics.lines`, `lyrics.words`), assign a line to a voice (`voices.lines`);
  - pin cues (`cues.pinned`);
  - map voices to characters and write per-section feel / meaning / movement / camera / palette / do-not rules (the
    managed block of `meaning/intent.md`; mapped voices are a floor for the voice count, D69).
  The server answers each save with the stages it affects; "re-run" starts `mvh analyze <folder>`, which re-runs only
  those stages. `tests/integration/test_override_roundtrip.py` checks the whole loop on real runs.
- **By hand.** `overrides.json` and `meaning/intent.md` are user inputs: the runner never writes or deletes them. Edit
  them, then `mvh analyze <folder>` (or `mvh meaning <folder>` for intent-only changes, which is faster). Stage params
  are human-correction hooks too, e.g. `--param harmony.key_override='"A minor"'`, `--param vocals.present=true`,
  `--param vocals.style='"singing"'`, `--param notes.piano_mode='"..."'`; they are kept for later re-runs.
- **Lyrics.** Give the text with `--lyrics file.lrc|.txt` when LRCLIB has no entry or the wrong one; it is kept for
  re-runs. `--no-lyrics-to-agents` keeps lyric text out of the agent-facing files and viewer.html.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `waiting for a heavy slot` for a long time | Another mvh process or test holds both slots (`%LOCALAPPDATA%\mvh\locks\*.lock` show the owner pid). Stale locks (dead pid, > 3 h) are removed automatically. |
| A stage is `stale` in `mvh status` | Its key changed (params, version, override, upstream); `mvh analyze <folder>` re-runs it. |
| `--only x` ran nothing | An upstream of x is stale; run without `--only`, or `--from <upstream>`. |
| Results did not change after a code edit | Code is not in the cache key: `--force <stage>` or bump the stage version. |
| Separation falls back to CPU | ROCm venv missing or failing; `mvh doctor` shows why; `run.json` records `variant`. |
| Lyrics grade D, `lyrics:lrclib_offline` | Offline run without a cached LRCLIB answer: run online once, or pass `--lyrics`. |
| identity `identity:offline` | MusicBrainz unreachable: tags only, no credits. |
| A file is open in another program | The runner warns (`stale ... is open in another program; not removed`) and continues; close it and re-run. |
| Power cut / crash mid-run | Re-run the same command: finished stages are cache hits; stale locks clear themselves. |
| `viewer.html` shows an error banner | Lane errors are listed in the banner; the data files are intact. Re-run `--force viewer` after fixing the input. |
| Two runs differ | Expected only for `drumsep_device: "auto"`; with defaults every file but run.json and `.cache` is byte-identical (gate step "determinism"). |

## 7. Known-weak areas and how the outputs flag them

Agents must read `manifest.json` `warnings` / QA flags and the per-item `conf` / `review` fields; brief.md repeats the
important ones in its status line.

| Area | How it shows in the outputs | What an agent should do |
|---|---|---|
| Kick timeline (S06; W4, UD2) | There are two kick sources: `events/hits.kick.json` (from the mix) and `events/drum_hits.json` drum=kick (DrumSep). On MEGAFAUNA they agree on only 49 % / 15 %: the DrumSep kick stem carries hat bleed (many rows with vel < 0.5). | Prefer drum_hits kicks with vel >= 0.5, and treat hits.kick as the viz-style pulse. W4 makes the drum-stem kick the agent-facing one, with a `kick_source` manifest field and an agreement QA flag. |
| Groove ids on noisy kits (S17) | `events/grooves.json`: MEGAFAUNA has 45 ids for 63 bars, Versatile 36 for 80. Jeremy and Newton cluster well. | On such songs, repeat moves by section and phrase rather than by groove id. |
| Half-time feel (S18) | `meta/tempo.json feel` stays `normal` on half-time grooves (Newton: snare on beat 3). | Check the snare `beat_in_bar` in `events/drum_hits.json` before choosing the dance pulse. |
| Hi-hat timing on dense rock mixes (S19) | Jeremy's hat rows scatter off the 16th grid, so the hat row of grooves and `drums.hat` flicker. | Use kick/snare accents; do not cut on hats for such songs. |
| Lyrics grade | `lyrics/lyrics.json` has `grade` A-D with `gate.checks` G1-G8, per-line `conf` / `grade`, and the manifest status repeats `lyrics_grade`. `alignment.vocals_after_last_line_s` plus a warning mark a voice that goes on after the last line (Jeremy's wordless outro). Offline runs without a cached LRCLIB answer transcribe instead (`lyrics:lrclib_offline`, `lyrics:transcribed`). | Grade D: treat word timing as approximate and do not lip-sync tightly. Pass `--lyrics` when LRCLIB has nothing. |
| Processed / karaoke-split voices | `fallback:*:vocals_stem` flags (lead_vocals nearly silent, so the full vocals stem was used: MEGAFAUNA), `degraded:vocals`, `degraded:voices`, `meta/vocal_range.json` `conf` (MEGAFAUNA 0.44) and `basis`. | When the range conf is low, use the range as a hint only. |
| Voices / singers | `meta/voices.json` `n_source` (intent > hints > estimate) and `k_selection`; `review` flags in `events/voice_spans.json` and `events/singing.json`. Newton's 4 voices rest on a near-tie. | Give the character count in intent.md, or map voices in the viewer (a floor, D69). |
| Key | `meta/key.json` `conf` and `flags` (`key:models_disagree`, `key:skey_differs`, `key:fifth_ambiguity`, `key:relative_ambiguity`, `key:modulation`, `key:chroma_only`, `key:no_tonal_evidence`, `key:low_confidence`), repeated in brief.md. | With conf < 0.5, do not build palette rules on the key. `--param harmony.key_override` fixes it. |
| Tempo / downbeats | `meta/tempo.json` `qa` flags: `tempo_trackers_disagree`, `feel_changes`, `downbeat_phase_off:<tracker>:<n>`, `no_pulse_regions` (free-time passages exist: `events/pulse_regions.json`). | Check the grid in the viewer; fix it with the `rhythm.*` overrides. |
| Separation | `meta/separation.json` and the run.json `variant`; presence votes and cross-model conf in `meta/stems.json`. | A stem marked absent is silence, not missing data. |
| Structure labels | `events/sections.json` `conf`; allin1's labels on long repeated vamps (Jeremy: many sections labelled chorus). | Relabel in the viewer (`structure.labels`). |
| Identity | `fallback:identity:offline` (no MusicBrainz verification or credits). | Run online once to get credits. |
| Notes | `degraded:notes`, `fallback:piano:basic_pitch` (piano transcribed by basic-pitch). | Piano notes are approximate. |
| Manifest size | `manifest:stage_summaries_trimmed` on every real song (the manifest sits at about 2.75-2.85k of its 3k-token cap). | Read the per-stage files for details. |
| Model licences | run.json `licences`: five separation models are still recorded as unclear or unverified. | Check them before publishing a video commercially. |
