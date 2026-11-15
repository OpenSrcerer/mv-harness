# UD3: grouped meaning, draft suggestions, and the viewer's whole-song box

User decision UD3 (approved 2026-11-15), merged into docs/CONTRACT.md as **D81**. It extends the meaning input format
of UD1 / D78 without changing what already parses. Grammar reference: the docstrings of
`src/mvh/stages/meaning/intent.py` (template, suggestions, viewer block), `anchor.py` (groups) and
`src/mvh/stages/viewer/intent_block.py` (the block the viewer writes).

## Why
- A song has 20 to 30 sections. Answering feel / movement / camera for each one is too much work, and most sections of
  one type get the same answer.
- A draft (`meaning/authored.json`) existed, but the user could not review it where they write: the template opened
  empty and the viewer's forms showed nothing.
- The viewer could only edit one section and the voice mapping. The song-level fields existed only in the template.

## Decisions
- **UD3-1 Groups.** Under `sections:` two group keys exist next to the section ids:
  `every section` (also `all`, `all sections`, `each section`, `default`, `whole song`) addresses every section, and
  `every <label>` (also `each <label>`, `all <label>`) addresses the sections whose label is `<label>` (plural and alias
  forms as in `anchor.norm_label`; never the EDM role). An answer is inherited downwards: `every section` < `every
  <label>` < the single section (specificity 0 < 1 < 5). The older bare keys (`chorus`, `drop`, `last chorus`,
  `chorus#2`) keep their meaning.
- **UD3-2 The template lists the groups first.** `every section`, then one `every <label>` entry per label with two or
  more sections (and any group the user answered), each with feel / meaning / movement / camera / palette. A value the
  user gave for a group is written back at the group; a section's entry holds only the section's own answer, so
  inheritance is never frozen into the sections. The template is still a fixed point of build -> template -> build.
- **UD3-3 The `# suggestion` marker.** `mvh meaning --suggest` types the draft's values into the EMPTY fields of the
  template and ends each such line with the comment `# suggestion` (two or more spaces before the `#`). A marked line is
  not the user's answer: the parser reads its value as empty and lists its key path in `suggested`
  (`meaning.json intent_suggested`), so the draft keeps applying as a draft. Deleting the marker makes the line the
  user's, with or without changing the text. Marked lines belong to the tool: `--suggest` refreshes them, and empties
  them when the draft no longer suggests a value. Nothing else in the file changes (fields the user filled in, free
  text, the viewer block). A suggestion shared by every section of a group is written once, at the group. Do-not rules a
  draft suggests become marked list items under `do_not`; they are not rules until unmarked. `mvh meaning` reports how
  many lines are still marked, so an edited line whose marker was left in place does not look silently ignored. A file
  created by `--init` / `--edit` gets the suggestions when a draft exists; an existing file only with `--suggest`.
- **UD3-4 The viewer edits the same fields.** The managed block gains `### Song` (logline, summary, setting, tone,
  `theme` lines, palette, `do not` lines), `### Every section` and `### Every <label>` (feel, meaning, movement, camera,
  palette). The block is the latest edit, so its values win over the template; do-not rules are a union (neither place
  can drop the other's rule). The patch protocol of `POST /api/intent` gains `song` (replaces the whole-song record,
  `null` clears it) and `groups` (`{all | <label>: {...} | null}`).
- **UD3-5 Suggestions in the viewer.** Each field of the three forms (whole song, a group, one section) shows where its
  value comes from: saved from the viewer, the user's template, inherited from a wider group (a placeholder, never
  saved into the narrower level), or a draft suggestion. Saving writes a field only when it is the viewer's own value,
  the user changed it, or the user accepted the suggestion. An unreviewed draft never becomes the user's.
- **UD3-6 Dismissing.** `POST /api/draft {dismiss: [{scope: song | section | group, ...}]}` deletes the named fields
  from `meaning/authored.json` (draft section entries are matched to the current sections by `anchor_claim`). The
  user's intent.md is not touched. The meaning stage re-runs (authored.json is one of its external inputs).
- **UD3-7 The drafting agent** is asked (request.md, SKILL.md) to give sections of the same type the same wording unless
  they truly differ, so the user reviews one suggestion per type.

## Additive fields of `meaning/meaning.json`
| Field | Meaning |
|---|---|
| `sections[].field_scope` | for each field whose source is `user`: `all`, `type` or `section`, the level the user answered at |
| `section_defaults[]` | one entry for `all` and one per section label: `key`, `section_ids`, `feel`, `meaning`, `movement_hint`, `camera_hint`, `palette_hint`, `field_sources`. A field is the user's group answer (`user`), or the draft's when every section of the group has the same draft value (`draft`) |
| `suggested_do_not[]` | do-not rules the draft suggests; never applied until the user adds them |
| `intent_suggested[]` | key paths of the template lines still marked `# suggestion` |

Agents keep reading `sections[]`: every section already carries its inherited values, so nothing changes for a reader
that ignores the new fields.

## Versions and tests
meaning 1.2.0, viewer 1.1.0. Tests: `tests/unit/meaning/test_groups_suggest.py`,
`tests/unit/viewer/test_song_groups_draft.py`, `tests/unit/viewer/logic.test.mjs` (meaningField, meaningFieldWrite).
