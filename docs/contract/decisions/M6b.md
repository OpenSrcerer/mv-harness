# M6b contract decisions (meaning, brief, frames, skill/)

Builder: builder-m6b. Contract v1.0.0-rc.1. Everything here is **additive** (optional fields / optional files owned by
M6b) or an interpretation of a frozen rule; nothing renames, removes or retypes a frozen field.

## Additive fields and files

| # | Where | What | Why |
|---|---|---|---|
| A1 | `events/singing.json` items | optional `conf` (0..1), `source` (`user` \| `voice_spans` \| `draft` \| `nearest` \| `default`), `review` (bool); documented in the envelope `fields` | agents and the viewer need to know which singer guesses are weak |
| A2 | `meaning/meaning.json` | optional top-level `palette_names` (the user's colour words), `field_sources` ({field: user\|draft}), `intent_form` (none\|text\|yaml\|yaml+text), `draft_used` (bool) | provenance of global fields without changing the frozen claim shapes |
| A3 | `meaning.json sections[]` | optional `label`, `field_sources` ({feel, meaning, movement_hint, camera_hint, palette_hint, characters_present, emotion.lyric, emotion.audio: user\|draft\|audio}) | per-field provenance: a section can mix the user's feel with a draft's camera hint |
| A4 | `meaning.json characters[]` | optional `voice_mapping` ({V: user\|draft\|voices\|proposed}) | shows which voice->character links the user confirmed |
| A5 | `meaning.json motifs[]` | optional `note` | the user's note on a motif |
| A6 | `frames/{fps}fps.csv` | after the curve columns, event columns `section_id, beat, downbeat, bar, beat_phase, count, sub, eight_id, line_id, singer, cue_tier, cue_id, hit` (param `events`, default all; `[]` = none) | Deforum/ComfyUI/Blender users have no loader; the columns use the helper membership rules (events by `frame_of`, segments at the sampling instant) |
| A7 | `frames/{fps}fps.deforum.json` (optional output, `format=deforum`) | `{fps, fps_rational, frame0, early, max_frames, keyframes: {channel: "0:(v), 1:(v), ..."}}` | Deforum/ComfyUI schedule strings |
| A8 | frames params | `fps` may be a list of rates or of `{fps, frame0, early}` (several exports per run); `curves: []` = a default video set, `["*"]` = all, fnmatch patterns, `"spectrum128"` = 128 columns `spectrum128.000..127` (hold, u8/255) | one stage run keeps every requested export (a later run with other params would otherwise unpublish the earlier CSV) |
| A9 | meaning params | `lyrics_to_agents` (default true; false blanks `lines.tsv text`, sets `input.json lines_file: null`, no hook quotes in the interview) | NF5 `--no-lyrics-to-agents` |

## Interpretations

1. **Status** (`meaning.json status`): `user` when intent.md contains any recognised answer; else `draft` when
   authored.json exists; else `pending`. A user who answered partly still gets `user`; each claim carries its own status.
2. **Harness facts in claims.** `CLAIM_PROV.status` only allows `user|draft`. Values the harness computes (audio mood word,
   who sings in a section, characters proposed from voices) are written with `provenance.source = "audio"`,
   `status = "draft"`. `field_sources` distinguishes `audio` from an agent draft.
3. **Characters always exist when lyrics exist.** `singing.json character_id` is frozen and required, so every voice
   gets a character: the user's mapping, else the draft's, else `meta/voices.json proposed_character_id`, else a
   user character still without a voice (in order, flagged as an open question), else a new `Cn` named after the
   voice's hint or `Voice Vn` (status draft, source audio). With lyrics but no voices at all, one `C1 Lead voice` on `V1`
   (flag `voices:absent`).
4. **Lead/backing per line.** Spans of one line that overlap (>= 50 % of the shorter) sing together; the lead is the
   character the user/draft marked `lead`, then the highest span confidence, then the longest span, then the lowest voice
   number. Non-overlapping spans (voices trading words) are each `lead`. A lyrics line with `backing: true` is backing
   for everyone. `lines.tsv singer` = characters, lead first, then by voice number (D38).
5. **Lines the voices stage missed** take the nearest span's voice (same section first) with `source: nearest`,
   `review: true`, conf 0.3.
6. **Per-section do_not.** Each `sections[].do_not` holds that section's user rules plus every global user rule, so
   `meaningAt(t).do_not` is complete on its own. Global `do_not` holds only the user's words, verbatim. A draft's do-not
   suggestions become `open_questions` (never rules).
7. **Re-anchoring** (claims carry `t0`/`t1`): every current section lying >= 50 % inside the claim's range receives it
   (a split keeps the note on both halves), else the one section holding >= 50 % of the claim (merge), else orphan.
   Claims addressed by label (`chorus`), occurrence (`chorus#2`), ordinal (`last chorus`) or EDM role (`drop`, via
   `events/edm_roles.json`) are resolved against the current sections; a label/role that matches nothing becomes an
   open question (orphans need an `old_section_id`). An orphan with no known time range has `t_range [0, 0]` and says so.
8. **Specificity** when several user claims fill one section field: id/time > occurrence > ordinal > EDM role > label.
9. **Citations** (`cites.py`): cited ids whose kind the meaning stage can see (sections, lines, words, voices,
   characters, motifs, cues, EDM roles, text/line groups, ids cited by cues) must exist, else they are dropped with a
   problem note; quotes are cut to 10 words; untyped claims become `speculative`; a draft may not type a claim `user`.
   Problems never quote text (NF5).
10. **intent.md format.** Free text is parsed (characters `C1 Name = voice V1`, `L005: C1+C2` line singers anywhere,
    `## Never show` bullets verbatim, `Palette:` hex or colour words, `Intro: ...`/`S03: ...`/`chorus#2: ...`/`Drop: ...`
    section notes, `## The story` -> summary + logline). The YAML template (fenced ```` ```yaml ```` block, written into
    interview.md with the song's ids and times) wins field by field over free text. The **viewer-managed block**
    (`<!-- mvh-viewer:begin v1 --> ... <!-- mvh-viewer:end -->`, grammar of `mvh.stages.viewer.intent_block`, M6a:
    `- V1 = C1 Name` voice mapping, `### S02 label t0-t1 s` sections with feel/meaning/movement/camera/palette/do not)
    is parsed too and wins over both (it is the latest edit in the user's own words); a round-trip test uses M6a's
    writer when installed. Per-line singer fixes: `L012: C2` lines (or YAML `line_singers:`); the viewer's per-line
    voice edits go through `overrides.json voices.lines` (voices stage), which then reach singing.json.
    `mvh.stages.meaning.intent.parse_intent(text)["n_characters"]` is the user's character count for the voices stage.
11. **brief.md numbers.** Every decimal printed is a value of the named file rounded to its printed precision
    (`mvh.stages.brief.trace` checks it); integers and percentages are counts or ratios of the named files (instrument
    coverage x 100, vocal share of a section = union of vocal phrases / section length). The energy cell shows the
    dominant dynamics level and the `mean_lufs` of its longest segment in the section.
12. **brief overflow**: rows collapse by repeat group, then a compact column set, then trailing rows are omitted with a
    pointer to `mvh brief --section` (never above 4k tokens). Missing upstream files degrade the brief (stage status
    `degraded`, fallback `brief:missing_inputs`) instead of failing it.
13. **frames** reads the channels each upstream recorded in its done record (no song-folder reads), takes duration
    from `meta/source.json n_samples / sample_rate`, and never writes NaN (raises if one would reach the CSV).

## Module verbs (D35)

- `mvh brief <folder> [--section S05] [--lyrics]`
- `mvh frames <folder> --fps 24 [--fps 24000/1001] [--frame0 1] [--early] [--curves a,b] [--events default|none|a,b] [--format csv|deforum] [--replace]`
  (adds to the exports recorded in `.cache/_run.json`; runs `--only frames`)
- `mvh meaning <folder> [--draft agent|anthropic|off] [--overwrite-draft] [--no-lyrics-to-agents]`
  (re-runs meaning, brief and viewer; `--draft anthropic` writes authored.json via claude-opus-5-5 first)

## Fixer round
- Intent: a file whose first non-comment line is a template key (or that starts with `# mvh-intent`) is the unfenced YAML template. Key-shaped lines read as free text give a warning.
- Template: harness voice proposals are comments (`# the harness proposes voices: V1`), `lead_backing` is empty; all-empty character entries are not user answers.
- Voices-stage proposals never add a voice to a character whose voices the user named.
- Draft free text with more than 10 consecutive lyric words is cut (`cites.cut_lyric_runs`); problems never quote text.
- brief.md and `--section` label draft-sourced fields from `field_sources`: `Draft: logline`, `Palette (draft)`, `(draft)` on feel/movement/camera/etc.

## Round 2 (fixer-m6b-r2)

- `meaning.json` `characters[].field_sources` (additive): `{name, description: "user"|"draft"}`; a user character whose
  name/description the draft filled is `draft` for that field. brief.md marks it `(draft name + description)`; the interview
  template prefills only the user's own answers. `voice_mapping` defaults to `proposed` (never `user`).
- Interview template: every prefill is empty (`lead_backing: ""`); harness proposals live in comments, so the untouched
  template is not an answer.
- intent.md unfenced template: found as a region (marker `# mvh-intent` or >= 2 template keys with no other `key:` line and no
  value that a `#` would truncate); the rest of the file is free text. Free text never reads template-shaped lines.
  Unknown top-level keys in a YAML block give a warning. Do-not labels (`**Never show**`, `Never show: ...`, `Don'ts`) are rules.
- `mvh frames` always checks the runner status of `frames` after the run and exits 1 with `not_run` when it is not done.

Change request for W3: `song.meaningAt(t)` (lib/mvh.js, lib/mvh_load.py) should return `field_sources`.
