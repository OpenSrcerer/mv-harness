# mv-harness

Song analysis for AI agents that make music videos. Give it one song and it writes a folder of timestamped metadata:
beats and 8-counts, sections and drops, drum hits, frequency bands, loud and quiet parts, stems, notes, vocal range,
word-timed lyrics with who sings each line, mood, and the meaning of the song as you tell it. A viewer lets you check
and correct all of it.

It does not render video. Video agents (Remotion, three.js, Blender, ComfyUI, …) read the folder and focus on
characters, choreography and style.

- **Windows 11**, Python 3.12, an AMD GPU is optional (the separators fall back to the CPU).
- Personal use: some models have non-commercial licences (`models.lock.json` lists each one).

## Quick start

Every command runs in **PowerShell from the repo root**. Load the environment once per shell:

```powershell
cd C:\Users\OpenSrcerer\Desktop\playground\mv-harness
. .\scripts\mvh-env.ps1
```

Check the setup. Every line should say `OK`:

```powershell
uv run --frozen --no-sync mvh doctor --quick
```

Analyse a song (put the file in `songs\`; any format ffmpeg reads):

```powershell
uv run --frozen --no-sync mvh analyze "songs\My Song.flac"
```

That takes about 20–30 minutes for a 5-minute song and writes `out\my-song\`. Then open the viewer:

```powershell
uv run --frozen --no-sync mvh view out\my-song
```

If a run stops (power cut, Ctrl+C, an error), run the same `analyze` command again: finished stages are reused.

## First-time setup on a new machine

Skip this if `mvh doctor --quick` already passes.

1. **Install Python and ffmpeg** (once), then open a new PowerShell window:
   ```powershell
   winget install Python.Python.3.12
   winget install Gyan.FFmpeg
   ```
2. **Run the setup script** from the repo root:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
   ```
   It installs `uv` if it is missing, the Python environments (main, plus the stem separators for CPU and AMD GPU),
   and **every model**, then runs `mvh doctor`. Add `-NoRocm` on a machine without an AMD RX 9000-series GPU. It is
   safe to re-run: finished steps are skipped or verified.

**Models.** You never download models by hand. All 28 models (81 files, about 12 GB) are pinned in
[models.lock.json](models.lock.json) with their URL and SHA-256, and are fetched and verified by the setup script.
To fetch or check them on their own:

```powershell
uv run --frozen --no-sync mvh models fetch     # download whatever is missing
uv run --frozen --no-sync mvh models verify    # re-check every file's SHA-256
uv run --frozen --no-sync mvh models list      # every model: present or missing, size, licence
```

**Where things live.** Models, caches and locks are in `%USERPROFILE%\.mvh` (override with `MVH_HOME`). They are
deliberately not under `AppData`: Windows gives packaged apps a private copy of `AppData`, so files downloaded from
inside such an app are invisible to a normal terminal.

## The workflow for one song

1. **Analyse**: `mvh analyze "songs\My Song.flac"`. Lyrics come from LRCLIB; if it has none or the wrong ones, add
   `--lyrics my.lrc` (`.lrc`, `.srt`, `.vtt` or `.txt`). `--profile draft` is a faster first look.
2. **Review**: `mvh view out\my-song`. One timeline shows sections, lyrics and singers, beats and counts, drum hits,
   bands, and loud and quiet parts, with stem solo/mute, zoom and loop.
3. **Correct**: in the viewer's edit mode, move or relabel sections, fix the BPM or downbeat, nudge lyric lines, map
   voices to characters, pin cues. **Re-run** repeats only the stages your edit affects.
4. **Write the meaning**: read `out\my-song\meaning\interview.md`, put your answers in `meaning\intent.md`, then run
   `mvh meaning out\my-song`. Anything that must be obeyed (characters, voice mapping, "never show" rules) goes in the
   template; free text is passed to agents as your notes.
5. **Hand it to a video agent**: `mvh pack out\my-song <dest>` copies what a page or video project needs (no stems or
   cache). Point the agent at that folder and at [skill/mv-harness/SKILL.md](skill/mv-harness/SKILL.md). For
   frame-based tools, `mvh frames out\my-song --fps 24` writes one row per video frame.

## What is in a song folder

| Path | Contents |
|---|---|
| `brief.md` | The summary an agent reads first (under 4k tokens): form, tempo, key, sections, cues, singers, meaning |
| `manifest.json` | Index of every file, with QA flags and warnings |
| `viewer.html` | The viewer (also opens read-only by double-click) |
| `events/` | Beats, bars, counts, sections, drum hits, kicks, cues, chords, vocal phrases, who sings when |
| `curves/` | 100 Hz curves: bands, loudness, kick pulse, stem levels, pitch, mouth-open |
| `lyrics/` | Word-timed lyrics (`lines.tsv`, `.lrc`, `.srt`, `.vtt`, `.ass`, `.json`) |
| `meaning/` | The interview, your `intent.md`, and the merged `meaning.json` |
| `stems/`, `audio/` | Separated stems; the mix and a preview |
| `notes/`, `lipsync/`, `tables/`, `meta/` | Notes per instrument, visemes, choreography tables, per-stage details |
| `lib/` | Helpers for agents: `mvh.js` (+ types), `mvh_load.py`, `mvh.glsl` |

## Commands

| Command | Does |
|---|---|
| `mvh analyze <song or folder>` | Runs the analysis; re-runs only what changed |
| `mvh view <folder>` | Opens the viewer, with edit mode |
| `mvh status <folder>` | Which stages are done, out of date or pending, and why |
| `mvh meaning <folder>` | Applies changes to `meaning\intent.md` |
| `mvh brief <folder> [--section S05]` | Prints the brief, or a zoom on one section |
| `mvh frames <folder> --fps 24` | One row per video frame |
| `mvh pack <folder> <dest>` | Copies the agent-facing files |
| `mvh validate <folder>` | Checks the folder against the contract |
| `mvh doctor` | Checks the environment |
| `mvh models fetch` / `verify` / `list` | Downloads or checks the pinned models |

Prefix each with `uv run --frozen --no-sync`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `uv` is not recognised | Run `. .\scripts\mvh-env.ps1` in this shell first. If it warns that `uv.exe` is missing, run `scripts\setup.ps1`. |
| `model file missing: …` | `uv run --frozen --no-sync mvh models fetch`. Then `mvh doctor --quick` should say `81 files in 28 entries verified`. If the shell was opened before an update, open a new one and load the environment again. |
| `waiting for a heavy slot` for a long time | Another `mvh` run is using both compute slots; it continues when one frees up. |
| A stage failed | Read `out\<slug>\.cache\_logs\<stage>.log`, fix the cause, and run the same `analyze` command again. |
| Lyrics are wrong or missing | Re-run with `--lyrics file.lrc` (or `.txt`). |
| Separation is slow | It fell back to the CPU; `mvh doctor` says why. |

More in [docs/RUNS.md](docs/RUNS.md): profiles, timings, the correction loop, known-weak areas, and how to serve a
song folder to a page.

## Documentation

- [docs/RUNS.md](docs/RUNS.md): how to run it, in detail
- [skill/mv-harness/SKILL.md](skill/mv-harness/SKILL.md): how a video agent uses a song folder
- [docs/CONTRACT.md](docs/CONTRACT.md): the output contract (every file and field)
- [docs/SEAMS.md](docs/SEAMS.md): known limitations
- [PLAN.md](PLAN.md): the design
