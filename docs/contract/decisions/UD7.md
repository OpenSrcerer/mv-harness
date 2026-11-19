# UD7: the meaning of the whole song, plus optional notes on lyric lines

User decision UD7 (2026-11-19), merged into docs/CONTRACT.md as **D87**. meaning 1.4.0, viewer 1.6.0, brief 1.3.0.

## Why
The viewer asked for a meaning per section and per group of sections. Sections are the music's parts (verse, drop,
chorus), not units of meaning, and a song has 20 to 30 of them: the boxes went unused. What a user does want to add
is a word of explanation on a single lyric line (a reference, a name, slang, who it is aimed at).

## Decisions
- **UD7-1 Viewer.** The Edit tab keeps the whole-song meaning. The boxes "Meaning by group of sections" and "Meaning of a
  section" are removed. Answers by section saved by an older viewer stay in intent.md and in effect; the panel says so
  and offers to remove them. The template keeps accepting `sections:` answers.
- **UD7-2 Line notes.** Selecting a lyric line shows "what this line means (optional)". A line that repeats (same
  `repeat_group`) shows "same for every repeat of this line", ticked by default: one note for every repeat. Unticked,
  the note is for that line alone, and a repeat with its own note keeps it. Written to the viewer block of intent.md
  under `### Lines` as `- r12: note` or `- r12 only: note`, keyed by the line's stable reference (D83).
- **UD7-3 Output.** meaning.json `line_notes[]` (one entry per line that has a note, shared ones marked), meaning.md
  "Line notes (user)", brief.md "Line notes", and the note next to each line in `mvh brief --section`. A note makes
  the meaning status `user`. A note whose line no longer exists becomes an open question.
- **UD7-4 Interview.** No question per section; a question about single lines and one about the music's big moments.
  Drafts may still suggest a look per section (marked draft).

## Tests
`tests/unit/meaning/test_line_notes.py`, `tests/unit/viewer/logic.test.mjs` (line notes).
