# r-words-m6b: independent review of M6b (meaning, brief, frames), lens R-WORDS

Verdict: **pass-with-fixes**. No blockers; 6 majors (each a failing test under `tests/review/M6b/r-words/`), 10 minors
(`docs/review/M6b-r-words.md`). Findings were formed from the spec and the code before reading the builder's report.

## What I ran
- `build()` of the meaning stage on the synthetic fixture (DictSource over `tests/contract/synth`), with the fixture's
  intent.md / authored.json and with targeted variants (partial voice mappings, the interview template, do-not phrasings,
  draft citations, split / removed sections). Scored singing against `_truth` (the builder's own truth test passes: 100 %).
- `build()` on all four real fixtures (`tests/contract/real-*`) with `lyrics_to_agents` true and false: schema-valid
  meaning.json / input.json, every line has a singer, no 4-word lyric n-gram in warnings, notes, summary, input.json or
  request.md, nothing over 10 consecutive lyric words in meaning.json / interview.md; with the flag off, lines.tsv text is
  blank and the interview carries no hook quotes. (Counts only were printed; no lyric text.)
- `DevRun` (the real `runner.child` path, synthetic) for meaning + brief + frames: end-to-end confirmation of F3 (the
  brief's S03 row) and F5 (the draft text lands in `.cache/meaning/_mvh/done.json`; finalize copies stage warnings to
  manifest.json, run.json and the analyze stdout). frames: 24 fps CSV, 1356 rows, no NaN, singer column `C1`, `C2`, `C1+C2`,
  no lyric words.
- A full `mvh analyze` of the synthetic song was started (out/_wip/r-words-m6b/synth) but sat behind the machine-wide
  heavy slots held by other agents (lyrics/mood stages waiting) for over an hour; I stopped it. The DevRun path covers the
  M6b stages through the same child runner.

Probe scripts: `out/_wip/r-words-m6b/probe1.py` ... `probe10.py`.

## Majors (failing tests)

| id | location | claim | test |
|---|---|---|---|
| F1 | `src/mvh/stages/brief/build.py` `_meaning_block`, `_feel`, `render_section` | Once the user answers anything, brief.md shows the draft's logline, palette and per-section feel unlabelled (status `user`; section provenance is `user` if one field is). The per-field origin exists in `meaning.json field_sources` but the brief ignores it. | `tests/review/M6b/r-words/test_rw_brief_draft_provenance.py` (3 tests) |
| F2 | `src/mvh/stages/meaning/singing.py` `build_characters` | The voices stage's `proposed_character_id` is applied before the user's exclusive mapping is respected: with the YAML template mapping C1 = V2 (and M5 proposing V_k -> C_k because its parser does not read `voices: [...]`), C1 sings both voices and C2 sings nothing; the duet collapses. | `tests/review/M6b/r-words/test_rw_voice_mapping.py` (2 tests) |
| F3 | `src/mvh/stages/meaning/intent.py` `_parse_text` (line loop -> `_section_notes`) | A Never-show bullet addressed to a section ("- Chorus: never show the singers' faces.") also becomes the user's `feel` for every chorus (brief cue sheet, `meaningAt().feel`, the ComfyUI prompt recipe). | `tests/review/M6b/r-words/test_rw_intent_parsing.py::test_section_addressed_do_not_rule_is_not_a_feel` |
| F4 | `src/mvh/stages/meaning/docs.py` `yaml_template` + `intent.py` / `stage.py` `has_user` | Pasting the interview's template untouched ("Empty = no answer") flips status pending -> user and stamps the harness's voice proposals as user-confirmed (`voice_mapping: user`), so the SKILL pending rule no longer fires. | `test_rw_intent_parsing.py::test_untouched_template_is_not_a_user_answer`, `::test_untouched_template_does_not_confirm_voice_proposals` |
| F5 | `src/mvh/stages/meaning/cites.py` `_fix_cites` (`{cid!r}`), `check_claims` (motif `line_id`) | Text from authored.json (e.g. a quote put in `cites[].id`) is echoed into stage warnings -> done.json, manifest.json, run.json, stdout (NF5; the builder's decision #9 says problems never quote text). | `tests/review/M6b/r-words/test_rw_draft_privacy.py::test_draft_citation_text_is_not_echoed_into_warnings` |
| F6 | `cites.py` (only `quote` is checked) + `brief/build.py` (logline printed in full) | A draft logline quoting a verse puts > 10 consecutive lyric words into brief.md and meaning.json (CONTRACT §1/§12: quotes <= 10 words). | `test_rw_draft_privacy.py::test_draft_logline_quoting_a_verse_is_cut_before_brief` |

All 10 tests fail now for the stated reasons (`uv run --frozen --no-sync python -m pytest -q tests/review/M6b/r-words`),
use only the synthetic fixture, run in under a second, and are ruff-clean.

## Suggested fixes (short)
- F1: label per field from `field_sources`: `Draft: <logline>`, `Palette (draft): ...`, `(draft)` on a feel whose
  `field_sources.feel` is `draft`; the zoom prints the source per line.
- F2: in `build_characters`, ignore a voices-stage proposal that names a user character whose voices the user listed
  (or that already has a user-mapped voice); then give the voice to a voiceless user character (with the question) or
  a new character. Separately (M5/W3): the voices stage's intent parser should read the YAML template's `voices:` lists.
- F3: skip lines inside do-not blocks in the free-text line loop (or attach them as that section's `do_not`).
- F4: write harness proposals into the template as comments (or `voices: []  # proposed: V1`), and do not count a key
  whose value equals the template's prefill as an answer.
- F5: say "a cited id is not a contract id" / "an occurrence names an unknown line" without the value (D42 style).
- F6: compare draft free-text fields with the lyrics (11-word n-gram overlap) and cut / flag, and cap the brief's
  logline at a word budget.

## Contract additions / change requests
None from me. Minor m10 notes for the W3 integrator: `mvh analyze` lacks the PLAN §10 flags `--intent`,
`--meaning-draft`, `--no-lyrics-to-agents`.

## What looked right
Inputs are never written (the writer only declares catalogue outputs; `--overwrite-draft` is an explicit opt-in);
draft claims cannot be typed `user`; draft do-not rules become questions, not rules; time-anchored claims re-anchor
correctly on a split (both halves) and orphan cleanly with a schema-valid orphans.json and a brief warning;
lines.tsv singer cells match D38's pattern; `lyrics_to_agents=false` keeps text out of lines.tsv, input.json and the
interview; the brief and zoom never print lyric text without `--lyrics`; frames never writes NaN.

## Overlap with other M6b reviews (read after my findings were fixed)
- r-contract-m6b F2 (zoom prints draft fields under `## Meaning (user)`) is the `render_section` half of my F1; my tests
  cover the main brief (logline, palette, cue-sheet feel). One fix (`field_sources` per field) closes both.
- r-contract-m6b F3 (unfenced template parsed as free text) is a different failure from my F4 (fenced, untouched template
  counted as user answers); both point at the template's prefill / parsing.
- Baseline: the builder's unit tests pass (`tests/unit/{meaning,brief,frames}`: 82 passed, 12 real-song skips).
