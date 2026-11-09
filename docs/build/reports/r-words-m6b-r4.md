# r-words-m6b-r4: round-4 R-WORDS review of M6b (meaning, brief, frames), W3 verify

Verdict: **fail**. The 8 round-3 findings are fixed, but the parser rewrite introduced 3 new majors (2 are regressions).

## Round-3 findings: all fixed
The fixer replaced the intent heuristics with one documented grammar (intent.py "grammar v2"). docs.yaml_template now
writes every user claim back. The changes are general, not test-specific hacks. Re-checked with inputs outside the
tests (probe out/_wip/r-words-m6b-r4/p4.py):
- hex palettes (R3-1 contract, R3-2 words): flow lists with and without spaces, block lists at column 0 and indented,
  3-digit hex, hex in section palettes, the hint comment kept after the answer. These all parse, fenced and unfenced,
  and the do_not rules and logline are kept. A broken key keeps the other keys and gives a warning that names it.
- template example comments never become claims (R3-2 contract), with one minor case left (m17).
- do-not over-capture (R3-3/R3-4 contract, R3-3 words): an inline label is one rule, and a title heading is not a
  do-not block.
- template round trip (R3-1 words): motifs, symbolism, references, notes and section do_not are prefilled.
- perspective field_sources (R3-5): `perspective.narrator` and `perspective.addressee` are set; meaning.md labels a
  draft perspective; brief does not print perspective.
- Tests: all of tests/review/M6b and the unit tests for meaning, brief and frames pass. Round-3 minors m14 and m15 are
  fixed; m16 is still open.

## New majors (each has a failing test)
- **R4-1 (regression)** `test_rw4_key_lists.py`: a lower-case template key followed by markdown bullets is silently
  dropped (`characters:` + `- C1 The Keeper = V1`, `sections:` + `- Chorus: ...`, `line_singers:` + `- L005: C1+C2`).
  - Cause: the key and its bullets become a layer-2 region, YAML returns a list, and `_apply_yaml` ignores lists for
    these three keys. There is no warning and nothing is kept in notes.
  - The pre-rewrite parser read all three.
  - The voices stage still counts 2 characters from the same text, so meaning and voices disagree.
- **R4-2 (headings part is a regression)** `test_rw4_do_not_recall.py`: common do-not headings now become notes:
  `## What I don't want`, `## Avoid these`, `## Things I never want to see`, `## Never show these`.
  - The old parser treated all four as do-not blocks.
  - Bulleted labels (`- Never show: blood`, and `9. **Never show**: blood` numbered like the interview question) are
    not rules either.
  - Notes are not in brief.md, so the user's prohibitions never reach the agent.
- **R4-3** `test_rw4_interview_copy.py`: the user copies interview.md and answers under each question, which is how
  the interview invites answers. Then:
  - the harness's preamble becomes the user's logline and summary;
  - question 8's text, including its 'night blue' example, becomes a user palette;
  - the "Never show" answer is folded into the question bullet and kept only as a note.
  - Pasting the interview untouched turns status 'draft' into 'user'.

Minors m17 and m18 are in docs/review/M6b-r-words.md (Round 4).

## W3 checks
- Real songs jeremy and newton-vs-nye: meaning, brief and frames were run through DevRun on out/_wip/integrator/<slug>
  (out/_wip/r-words-m6b-r4/real.py).
  - All stages ok with 0 warnings. brief.md is about 1.9k and 1.6k tokens.
  - 0 lyric 9-grams in brief.md, meaning.md, interview.md and request.md.
  - The lines.tsv singer column uses 'C3+C1' for multi-singer lines (D38).
  - The only meaning.json differences from the integrator are the additive `notes` and `references`.
- tests/integration/M6b does not exist. I did not run the full gate, because none of these findings depends on it.
