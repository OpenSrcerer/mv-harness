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
3. **Correct**: in the viewer's edit mode, move or relabel sections, fix the BPM or downbeat, nudge or pin lyric
   lines, map voices to characters, pin cues. **Re-run** repeats only the stages your edit affects.

   *One word off?* Zoom in until the words show under the line, then drag the word (its right edge changes its
   length), or click it and use the buttons in the Edit tab or the `<` / `>` keys (10 ms steps). Ctrl+click or
   Shift+click selects several words to move together. Words stay inside their line's bar; drag the bar's edge to
   make it longer or shorter (the words stay put; the edge stops at the first or last word).

   *Two singers merged into one voice?* Select the words the other singer sings, press **move these words to a new
   bar**, re-run, then pick **+ new voice** under "sung by" for the new bar. A voice that should not exist can be
   merged into another from its card under "Voices → characters".

   *Lyrics out of sync in one part?* Select the first line of that part, put the playhead where it really starts and
   press **pin start at playhead** (or **pin at start of** the section). Do the same for each pass, for example each
   time the hook starts, then re-run: the lines between pins are placed again and their words snap to the singing.
4. **Write the meaning**: `mvh meaning out\my-song --edit` creates `meaning\intent.md`, opens it in your editor, and
   applies it when you close the file. The viewer's Edit tab has the same fields. You can answer once for a whole
   group of sections, and review an agent's draft instead of writing every field. See
   [Writing the meaning](#writing-the-meaning).
5. **Hand it to a video agent**: `mvh pack out\my-song <dest>` copies what a page or video project needs (no stems or
   cache). Point the agent at that folder and at [skill/mv-harness/SKILL.md](skill/mv-harness/SKILL.md). For
   frame-based tools, `mvh frames out\my-song --fps 24` writes one row per video frame.

## Writing the meaning

The harness measures the song; you say what it means. Your answers live in one file, `out\<slug>\meaning\intent.md`.
Until it has an answer, the song's meaning status is `pending`.

There are two places to write it. They hold the same fields and save to the same file:

| Place | Command | Good for |
|---|---|---|
| Your editor | `mvh meaning out\my-song --edit` | Writing everything in one go, as text |
| The viewer | `mvh view out\my-song`, **Edit** tab | Writing while you listen: the whole song, a group of sections, or one section |

```powershell
uv run --frozen --no-sync mvh meaning out\my-song --edit
```

That one command:

1. creates `meaning\intent.md` from the song's template if the file does not exist yet (an existing file is never
   replaced);
2. opens it in your editor and waits until you close the file;
3. applies your answers: `meaning.json`, `meaning.md`, `brief.md` and the viewer are refreshed, and the status becomes
   `user`.

Run it again whenever you want to refine the meaning. The questions to answer are in `meaning\interview.md`: what the
song means to you, the world and characters, how each section should feel and move, the top moments, colours, and
what must never appear.

**The editor** is the first of these that exists: `--editor "<command>"`, then the `MVH_EDITOR`, `VISUAL` or `EDITOR`
environment variable, then VS Code (`code --wait`), then `nvim` / `vim` / `vi` in a terminal, then Notepad. For
example, to always use Vim: `$env:MVH_EDITOR = 'vim'`.

### Answer once for many sections

A song has 20 to 30 sections, and you do not have to describe each one. Under `sections:` the template starts with
groups. An answer is inherited downwards:

1. `every section`: the default for the whole song;
2. `every drop`, `every chorus`, …: one entry per section type that occurs more than once;
3. a single section (`S04`): only what differs from its group.

```yaml
logline: "A small light carried through an empty world"
setting: "Abandoned city at dusk"
palette: [#140c28, #4f1aa7, amber]
do_not:
  - never show faces
sections:
  every section:
    camera: "slow, never handheld"
  every drop:
    feel: "the light flares up"
    movement: "slow rise, arms opening"
  S13:   # drop#5 1:41.8-1:50.9
    t0: 101.781
    t1: 110.901
    feel: "the last and biggest flare"
```

### The file has two kinds of content

- **The template** (the YAML block) is what agents must obey. Fill in what you care about; an empty field means "no
  answer". `do_not` holds the only hard rules and is copied word for word to every agent. Keep each section's `t0` and
  `t1` lines, so your notes follow a section if you move its boundaries later.
- **Free text** anywhere outside the template is passed to agents as your notes, exactly as written. It is never
  turned into fields or rules.

What you save in the viewer goes into a marked block at the end of the file (`## Viewer corrections`). That block is
the latest edit, so it wins where the template sets the same field.

### Drafts: let an agent fill the gaps, then review

You can have the gaps drafted instead of writing every field. A draft is a set of suggestions in
`meaning\authored.json`. It never overwrites your answers, and it cannot create a `do_not` rule.

1. **Write the song-level lines first** (logline, setting, the rough story). A draft made from those describes your
   video; a draft made from the audio alone gets the pacing right but the imagery is generic.
2. **Get a draft.** Point a video agent at `meaning\request.md`, or run `mvh meaning out\my-song --draft anthropic`
   (needs `ANTHROPIC_API_KEY`).
3. **Review it**, in either place:
   - **Viewer:** each suggested value is prefilled and marked `suggestion`. Accept it, change it, or dismiss it.
     A suggestion you leave alone is not saved as yours.
   - **Editor:** `mvh meaning out\my-song --edit --suggest` types the suggestions into the empty fields of the
     template. Each such line ends with `# suggestion`. Delete that marker on the lines you accept (change the text
     first if you like). A line that still has the marker is not your answer.

Until you accept a suggestion, agents still see it, labelled as a draft. To remove one for good, dismiss it in the
viewer.

### Other ways to work on it

| You want to | Do |
|---|---|
| Only create the file, and edit it yourself | `mvh meaning out\my-song --init`, edit `meaning\intent.md`, then `mvh meaning out\my-song` |
| Put a draft's suggestions into the file without opening an editor | `mvh meaning out\my-song --suggest` |
| See what agents will read | `meaning\meaning.md` (fields that are still a draft are marked) and `brief.md` |

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
| `mvh meaning <folder> --edit` | Creates `meaning\intent.md` if needed, opens it in your editor, then applies it |
| `mvh meaning <folder>` | Applies changes to `meaning\intent.md` (`--init` only creates the file) |
| `mvh meaning <folder> --suggest` | Types a draft's suggestions into the empty fields of `meaning\intent.md`, marked `# suggestion` |
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
| The words are right but a part is out of sync | Pin the first line of each pass in the viewer (Edit tab, Lyrics) and re-run. |
| Separation is slow | It fell back to the CPU; `mvh doctor` says why. |

More in [docs/RUNS.md](docs/RUNS.md): profiles, timings, the correction loop, known-weak areas, and how to serve a
song folder to a page.

## Documentation

- [docs/RUNS.md](docs/RUNS.md): how to run it, in detail
- [skill/mv-harness/SKILL.md](skill/mv-harness/SKILL.md): how a video agent uses a song folder
- [docs/CONTRACT.md](docs/CONTRACT.md): the output contract (every file and field)
- [docs/SEAMS.md](docs/SEAMS.md): known limitations
- [PLAN.md](PLAN.md): the design
