# W1b review: R-CONTRACT ("the video agent")

Reviewer: r-contract · 2026-11-08 · lens PLAN §11 R-CONTRACT · scope: W1b foundation (runtime, lib, fixtures) against
PLAN.md, docs/SPIKE.md and docs/CONTRACT.md (D1-D36).

**Verdict: pass-with-fixes.** No blockers. Five majors, each with a failing test. A Remotion, three.js or Blender agent can
already build a choreographed, character-driven video from one output folder. The synthetic fixture is faithful and
internally consistent, and the two loaders agree with each other and with `conventions.py` even on frame rules the golden
set does not cover. The majors are about the API and the contract: some documented calls silently return incomplete or
wrong data for cues, duets, chords and 24/30 fps renders.

## What I did (all re-runnable)

- **Walking skeleton.** `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 mvh analyze
  tests/contract/synth/_truth/synth-song.flac --out out/_wip/r-contract/synth --no-network` exited 0 in about 9 s.
  `mvh validate` reports 118 files and 0 errors. Note that `--out` is the song folder.
- **Opened it as a video agent.** I read manifest.json and brief.md, used `lib/mvh.js` from the copied `lib/` in Node
  (`loadSync`, plus `load()` in URL mode with a custom fetch to simulate a browser or Remotion), and used `lib/mvh_load.py`
  from the copied `lib/`. Every helper works after `ensure('helper:X')` in URL mode.
- **Parity beyond the golden set.** I ran 2,074 probe times: every event time ±1e-9 and ±4 ms, word boundaries, before 0
  and after the end. I also used 10 extra frame rules: 120, 144 and 200 fps (more than one frame per curve sample),
  [60000, 1001] with frame0 1 and early, 7.5 fps, 1 fps, frame0 -3, frame0 1000, 59.94 early, and 24 fps with frame0 1 and
  early. These covered count, barPhase, lyricAt, singerAt, vocalAt, meaningAt, pulse (beats unit, attack, smooth), osc,
  spectrumWindow, `curve.frame` (incl. NaN pitch, hold, 1 Hz), inFrame, vizState and textureData at widths 1, 7, n and
  n+1. **JS vs Python: 0 differences. Python loader vs `conventions.py`: 0 differences.**
- **Flash rule at video frames.** All 369 drum hits and every count accent land in the max of their own frame at 24,
  23.976 (frame0 1, early), 25, 30 and 60 fps: 0 misses.
- **Fixture audit.** Beats match bars (first_beat, n_beats, t/d). Pulse regions match beat `in_pulse`. Sections, phrases
  and counts tile the bars. Counts restart at every phrase and section start. Word timings fall inside their lines.
  singing, voice_spans, characters and voices all link up. meaning sections match sections in t0/t1/occurrence. Every
  cue, hit point and hold source resolves, and `next_major_in_s` is correct. tables/*.csv match events. mouth_open per
  voice is 0 outside that voice's lines. **Against its own audio:** the onsets of the kick, snare and hihat sub-stems
  match drum_hits (median error 0.02-0.07 ms, no unexplained bursts). The truth voice stems V1 and V2 are active only
  inside their singing spans. Silence Z001 is digital zero. Every stem is sample-aligned with the mix. Every lyric word
  carries energy in lead_vocals. A module builder can test real behaviour against this fixture; it is not copy-only.

## Findings

### F1 · major · cues `next()` cannot reach co-timed cues (the drop is invisible)
- **Location:** `src/mvh/contract/conventions.py` `event_next` / `event_prev` (D28), `lib/mvh.js` `eventNext`,
  `lib/mvh_load.py` `event_next`, CONTRACT §9 ("Cue lookups: `events('cues').next(t, {minTier: 2})`"), and the cues
  fixture (co-timed tier-1 cues).
- **Claim:** `next` returns only the first item strictly after t. When several cues share a time, an agent stepping
  through the list (`t = cue.t`) never sees the second one. The fixture has 22 co-timed groups. Two of them are tier 1:
  the section and build_start at 25.0 s, and the section and **drop** at 34.5 s. The drop is moment rank 1.
  `prev` returns the *last* of a tie and `next` the *first*, so the two are asymmetric.
- **Evidence:** `test_f1_cue_next_iteration_reaches_every_tier1_cue` fails with
  `{'Q0077': (25.0, 'build_start'), 'Q0110': (34.5, 'drop')}` unreachable. `test_f1_moment_rank1_cue_reachable_by_next`
  shows that `next(34.0, minTier=1)` gives only `['Q0109'] (section)`. The JS twin `F1` in
  `rcontract_video_agent.test.mjs` fails the same way.
- **Suggested fix:** pick one. (a) Make `next`/`prev` return every item at the first/last matching time (or add
  `nextAll`/`next_all`), and document the tie rule in D28. (b) Have the cues stage merge co-timed cues of a tier into one
  cue carrying `kinds[]` and `sources[]`, so the drop is not hidden behind a section cue. Then update the CONTRACT §9
  recipe.

### F2 · major · `lines.tsv` drops the second character on duet lines
- **Location:** `lyrics/lines.tsv` (fixture; producer: meaning) and CONTRACT §7 tables (the `singer` column format is
  undefined).
- **Claim:** lines.tsv is the context-safe file an agent reads for words and singers. On the four chorus lines
  (L005, L006, L009, L010), `events/singing.json` has C1 (lead) and C2 (backing). `lyricAt().line.singer` returns
  `[C1, C2]`, but lines.tsv says only `C1`. An LLM agent planning character shots from lines.tsv never puts C2 in a
  chorus. The contract does not say how a multi-singer line is written.
- **Evidence:** `test_f2_lines_tsv_singer_lists_every_character_singing_the_line` fails with
  `{'L005': (['C1'], ['C1', 'C2']), 'L006': ..., 'L009': ..., 'L010': ...}`.
- **Suggested fix:** define `singer` as the lead-first, `+`-joined character list (e.g. `C1+C2`). Optionally add a
  `voices` column (`V1+V2`) or mark backing (`C1+C2(b)`). Then regenerate the fixture and note the format in CONTRACT §7.

### F3 · major · one file, two producers (notes vs vocals)
- **Location:** `catalog.py` outputs `events/notes.{src}.json` and `notes/{src}.mid` for notes, with
  `ids.PITCHED_SOURCES` including `vocals`; `runner/ctx.py match_output`; `contract/fixture.py run_stub`;
  `runner/run.py publish`.
- **Claim:** D6 gives `events/notes.vocals.json` and `notes/vocals.mid` to the vocals stage, but the notes stage's
  declared patterns also match them. In the walking skeleton both stages publish them, and manifest.files lists each path
  twice with different producers. Because `publish` unlinks paths a stage published before and no longer produces, the
  first real notes run in W3 that stops writing vocals would delete the vocals stage's file from the song folder (until
  vocals re-publishes). The fixtures builder already raised the stub half of this as CR 1, with the xfail
  `test_fx_stubs.py::test_each_file_copied_by_one_stage`. The declaration half (`match_output`) and the manifest are not
  covered.
- **Evidence:** `test_f3_notes_stage_does_not_claim_the_vocals_stage_outputs` fails with `{'events/notes.vocals.json':
  ['notes', 'vocals'], 'notes/vocals.mid': ['notes', 'vocals']}`. `test_f3_manifest_lists_each_published_file_once`
  fails the same way on a fresh skeleton run in tmp_path.
- **Suggested fix:** restrict `{src}` for the notes outputs to bass|piano|guitar|other, for example a NOTE_SOURCES
  constant without vocals. Make `check_dag` (or a spec test) reject any concrete path two stages can claim. Make
  `publish` refuse to unlink a path that another stage currently publishes.

### F4 · major · `vizState(t)` silently assumes 60 fps; at 24/30 fps a quarter of onsets never fire
- **Location:** `lib/mvh.js` `Song.vizState(t, fr = null)` and `lib/mvh_load.py viz_state` (`VIZ.DEFAULT_FPS = 60`),
  and the CONTRACT §9 row `song.vizState(t)` (Args: `t`, no frame rule).
- **Claim:** onset flags, beatPulse and frame-pooled hit values are computed for the 60 fps frame around t. A Remotion
  agent following CONTRACT §9 calls `song.vizState(frame / 30)`. A bass onset that falls outside the ±8.3 ms 60 fps
  window around a 30 fps frame time never sets `onset` on any rendered frame. On the fixture 32 of 141 bass onsets are
  lost at 30 fps and 16 at 24 fps; mid onsets lose 45 of 156 at 30 fps. Real music, which is off-grid, will lose more.
- **Evidence:** `test_f4_vizstate_documented_call_never_drops_onsets_at_30fps` fails with "32 of 141 bass-onset frames
  at 30 fps never report onset=True". `test_f4_contract_documents_the_vizstate_frame_rule` fails because the CONTRACT
  row has no frame rule. The JS twin `F4` fails the same way.
- **Suggested fix:** make the frame rule mandatory (throw without it), or let `load(base, {fr})` set a song-wide default
  that every frame helper uses. Document `vizState(t, fr)` in CONTRACT §9, mvh.d.ts and RECIPES.

### F5 · major · overlapping segments are unreachable: duet visemes, chords, instruments
- **Location:** `Events.at` (D28 "latest-starting segment wins") in both loaders, and the CONTRACT §9 note "Notes,
  visemes and sections need no helpers of their own: `events('notes.bass').at(t)`, `events('visemes').at(t)`".
- **Claim:** `at(t)` returns one item. Several files overlap by design, and the fixture shows how many items can be
  active at once: visemes, voice_spans and voice_activity (2, in the duet), notes.other (3, a pad chord), instruments (5)
  and stem_activity (10). The documented viseme recipe returns the backing voice V2 on every duet frame, so the lead
  character C1's mouth shape cannot be reached. `notes.other.at(1.0)` returns one note of a three-note chord. There is
  no query for "everything active at t". The workaround (filter `items` and call the exported `eventAt`) is not
  documented.
- **Evidence:** `test_f5_all_overlapping_segments_are_queryable` fails because `Events` has no `all_at`.
  `test_f5_documented_viseme_recipe_returns_lead_voice_in_duet` fails because `events('visemes').at(17.3)` gives V2
  while the lead singer is V1. The JS twin `F5` fails the same way.
- **Suggested fix:** add `Events.allAt(t)` / `all_at(t)`, returning every item with d > 0 that contains t, sorted by
  t then file order, plus a reference function in `conventions.py` and golden rows. Optionally add `where`/`voice`
  filters, or a `viseme` field in each `singerAt` entry. Then fix the CONTRACT §9 note.

## Minor findings (no tests)

1. **textureData on NaN-aware channels differs from `curve.at` off-grid.** Probed every 1 ms, `vocal.midi` differs in
   929 places, by up to 6.64 semitones at t = 11.3553 (a phrase onset), and `vocal.f0_hz` by up to 115 Hz. CONTRACT §9
   and PLAN §7 say the texture sampling equals `curve.at`. The lib builder noted this as a limitation, not a contract
   deviation. Fix: say so in CONTRACT §9, or mark onset samples so the shader can do a nearest lookup there.
2. **The GLSL path has no frame-pooled variant.** `mvhCurve` lerps at t. A shader that samples `hits.*` or `drums.*` at
   the frame time does not get the `max` frame value that `curve.frame` gives, so a flash can land a frame late.
   Document this, or offer `textureData(ids, {fr})` with pre-pooled per-frame values.
3. **`lib/mvh.d.ts` is not copied into the song folder** (`lib/` has only mvh.js, mvh_load.py and mvh.glsl). A
   TypeScript (Remotion) agent gets no types from the folder. Copy it in finalize and list it in CONTRACT §1/§8.
4. **`vizState.bandBytes` puts R = G = B.** viz `audio.js` packs G = raw and B = peak-hold, and `viz/js/gl.js` exposes
   `bandRaw()`/`bandPeak()` reading `.y`/`.z`. vizState already computes `bandsRaw` and `peaks`, so packing them would
   make those GLSL helpers correct offline. No current scene uses them, and CONTRACT §5 chose R = G = B.
5. **`pulse()` looks only at the previous and the next item.** A weak item right after a strong one cuts the strong
   flash short (for example `pulse('drum_hits')` with a hat 50 ms after a kick). drum_hits mixes all drums, and
   `song.pulse(src)` cannot filter by kind. Document the exported `pulse(t, items)` with pre-filtered items, or add a
   `where` option.
6. **`pulse('cues')` weights tier-4 beat cues as 1** (strength null → weight 1), above section cues (strength 0.55).
7. **Hit points and holds cite less than they claim.** `kinds` lists drum, vocal_onset and chord, but `sources` cites
   only beats and sections, because drum_hits, notes and chords have no ids. A `vocal_note` hold cites a vocal phrase,
   not the note. An agent cannot tell which character's onset or which drum made a hit point. Consider ids or
   `beat:`-style reference keys for those items.
8. **A typo in an events name silently returns an empty Events** (`events('cue')` has `.exists = false`, no error).
   Consider a warning, or a strict option for agents.
9. **Context cost.** `curves/index.json` is 67 KB (about 17k tokens) for a 56 s song, and an agent that wants the
   channel list is likely to cat it. Put a channel-id summary in the brief or the manifest, and add index.json to the
   SKILL "never cat" list. `cues.json` is 30 KB, 63 % of it tier-4 beat references (about 160 KB for a 5 min song).
10. **Fixture semantics.**
    - Repeat group C has `similarity 1.0` for a 4-bar and an 8-bar chorus.
    - The S02 meaning has `emotion {lyric: longing, audio: energetic, agree: true}`.
    - Character C2 has `lead_backing: "both"`, a value that no enumeration lists.
    - Backing words (truth `backing_words`, 30 words) are not in lyrics.json, so `lyricAt().word` follows only the lead
      in duets.
    None of these break anything, but a module builder will copy them as conventions.

## Notes for later modules (not findings)

- RECIPES (M6b): Remotion `load(staticFile('song'), {include: [...]})` works in URL mode, and in my simulation every
  helper is synchronous after `ensure('helper:X')`. For viz scenes, drive `uTime` with song time (recentBeats are song
  times).
- The rhythm, choreo and cues builders can rely on these fixture conventions: pickup = bar 0 with a beat_in_bar 4 pickup
  beat; E000 covers beats -3..0; virtual beats fill the silence bar (32.5-34.5) and the final ring (54.5-56.5) with
  in_pulse false; partial counts E008 (len 7: a 4/4 bar plus the 3/4 bar), E009 (silence bar) and E015.

## Test files

- `tests/review/w1b/contract/test_rcontract_video_agent.py` has 9 tests, all failing now for the stated reasons
  (pytest, about 9 s including one walking-skeleton run in tmp_path).
- `tests/review/w1b/contract/rcontract_video_agent.test.mjs` has 3 tests, all failing now
  (`node --test tests/review/w1b/contract/rcontract_video_agent.test.mjs`).
