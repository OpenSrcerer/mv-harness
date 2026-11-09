# UD1: the meaning input format (W4 phase 0, ud1-meaning)

User decision UD1 (docs/BUILD-STATUS.md, approved 2026-11-09), merged into docs/CONTRACT.md as **D78**. Grammar
reference: the docstring of `src/mvh/stages/meaning/intent.py` ("mvh-intent v2"). It supersedes the intent grammar of
docs/contract/decisions/M6b.md (v2/v3: heuristic markdown reading) and amends D51 / D69 (what the voices stage reads).

## The rule
`meaning/intent.md` is read in exactly two ways, plus the viewer's managed block:

| Part | What it is | What it gives |
|---|---|---|
| Viewer block `<!-- mvh-viewer:begin v1 --> ... <!-- mvh-viewer:end -->` | machine-written by `mvh view` (M6a V7) | voice -> character (`- V1 = C1 Name`), per-section bullets; wins as the latest edit |
| Template regions | the interview's YAML block, fenced or unfenced | every structured field and every do-not rule (the only hard constraints) |
| Free text | everything else | `meaning.json notes`, verbatim, user-authored; never a field, never a rule |

**Anything that must be obeyed goes in the template.** interview.md (preamble, the Never-show question, the template's
first comment), request.md, SKILL.md and brief.md all say so.

## Decisions
- **UD1-1 One parser.** `mvh.stages.meaning.intent.parse_intent` is the only reader of intent.md. The voices stage
  (`mvh.stages.voices.intent`) is now an adapter over it: `n_characters` = template characters, `n_voices` = template
  `voices: <n>`, `voice_to_character` = template `characters.*.voices` then the template `voices:` map, then the viewer
  block (floor rule of D51/D69 unchanged), `line_characters` = template `line_singers`. Its free-text regexes
  (`C1 ... voice V1`, `V2 = C3`, `voices: 4`, `## Characters` bullet counts, `L007: V3`) are removed: a mapping or count
  written in prose is a note in both stages, so voices and meaning can never disagree (R-WORDS R5-2). Per-line voice fixes
  stay `overrides.json voices.lines`; `line_voice` is always empty. voices 1.2.0.
- **UD1-2 Template regions** (unchanged tolerances from M6b grammar v3): fenced with ```` ```yaml ```` / ```` ```yml ```` /
  ```` ```mvh-intent ```` (a missing closing fence ends at the first non-template line), or unfenced from a
  `# mvh-intent` marker or a column-0 lower-case template key; hex colours start values, `#` comments need 2+ spaces (or
  follow a closed value; the template's own hints always), plain values YAML would misread are quoted; per-key and
  per-entry fallback when a region does not parse. Changes: an entry that still fails is **kept verbatim as a note**
  (warned), never read as free-text fields; an unknown key is kept as a note (warned); a map key may hold `#`
  (`chorus#2:`); a bare list item `- x:` keeps its colon.
- **UD1-3 New template key `voices`.** `V1: C1 Name` (map) or bullets `- V1 = C1 Name` / `- V1 -> C1` / `- V1 is C1, Name`
  (the viewer block's own syntax). A voice has one character: `voices` wins over `characters.*.voices` (warning on a
  conflict); a new character id is created; the name fills an unnamed character. An integer (`voices: 3`) is the number of
  singers (the voices stage's explicit k). The generated template carries an empty `voices:` line with a hint comment
  (`# which character sings each voice ...`, in `TEMPLATE_HINTS`) and writes the count back when the user gave one.
- **UD1-4 Free text -> notes.** A note is a markdown heading with everything under it up to the next heading, template
  region or end; text before the first heading is a note. Lines are verbatim (trailing spaces cut, blank runs collapsed).
  A heading with no text joins the note below; directly above a template region it is that region's label (not a note).
  HTML comments are ignored. Notes are a union: the template's `notes` first, then the free text (`intent.free_notes`
  lists the free-text ones). `field_sources.notes = user`; status is `user` when any note exists.
- **UD1-5 Interview copies.** The harness's own interview lines are never notes: title, preamble, status, "Already
  answered", voice-fact bullets, the "Which character ..." line, the template heading and intro, the viewer's default
  title `# What this song means to me (meaning/intent.md)`, the column-0 bullets under `## Open questions`. A question
  line becomes the heading (`## <title>`) of the user's answer when one follows (below or after it on the same line);
  text the user appended after a harness line is kept. The fixed sentences live in `meaning/interview_text.py`, shared by
  the writer and the reader (a sync test checks every interview line). An untouched copy answers nothing.
- **UD1-6 Rule-like notes.** A free-text note containing never / avoid / don't / do not / must not / no-go / forbidden /
  off-limits / banned / taboo adds one open question ("N free-text note(s) ... read like a rule ... anything that must be
  obeyed goes in the template, under do_not"), citing note numbers, never the text. It never creates a rule.
- **UD1-7 Agent-facing surfaces.** brief.md: "User notes (N, user-authored ...; direction, never rules)" with the notes
  verbatim up to 120 words (`NOTES_WORDS`), the do-not line says "from the intent template: the only hard rules", and
  one line "Anything that must be obeyed goes in the template of meaning/intent.md (do_not); free-text notes are never
  rules." meaning.md shows every note as a block quote. Provenance stays per field (`field_sources` in meaning.json,
  sections' `field_sources` through `meaningAt()` / `meaning_at()`, `(draft)` tags in brief.md). meaning 1.1.0, brief 1.1.0.
- **UD1-8 Contract additions (additive).** `files/meaning` documents the optional `notes`, `references`, `field_sources`,
  `intent_form` (values none | yaml | text | yaml+text, `+viewer`); the `meaning/intent.md` file description says how it is
  read. The contract version bump (1.0.0-rc.2 -> 1.0.0-rc.3) is done once by ud2-kick for both W4 decisions.
- **UD1-9 Fixture.** `tests/synth/song/folder.py` `INTENT_MD` is now a template (logline, characters, palette, do_not,
  sections) with prose around it (two notes); no other fixture file depends on it (synth rebuilt with
  `python -m tests.synth.build --only synth`).

## Superseded review findings (tests rewritten to the new rule)
R-WORDS R3-3, R4-2, R4-3, R5-1, R5-2, R5-3, R5-4, N2, N4, F3 and R-CONTRACT R2-3, R3-3, R3-4 asked the heuristic reader to
recognise more markdown. Under UD1 their tests assert the new rule instead: free text is kept verbatim as notes and
never silently dropped, never becomes a field, a rule or a garbled value (`*`), the same answers in the template give the
fields and rules, and a rule-like note raises an open question.
