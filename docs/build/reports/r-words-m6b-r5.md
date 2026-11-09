# r-words-m6b-r5: R-WORDS round 5 review of M6b (meaning, brief, frames), W3 verify

## Verdict: fail (4 new majors, all in the intent grammar)

## Round-4 findings
- R4-1 (key + bullet answers): FIXED, with a real grammar change (`_list_answer`). Shapes beyond the tests were checked
  against the pre-rewrite parser: col-0 and indented bullets, one-key maps, nested section maps, bold ids, colons in
  names, perspective/motifs/palette/themes/do_not bullets (q3.py). All pass, and several work that never did before.
- R4-3 (interview copy): FIXED. Rule 0 recognises the question lines. Checked on the interviews of synth and all 4 real
  fixtures: an untouched paste stays pending with no user fields; answers under the questions, on the same line and
  unnumbered all land in the right fields; no harness text reaches notes (q4.py).
- R4-2 (do-not recall): FIXED ONLY for the named cases. The vocabulary is closed (fixed fillers, at most 8 tokens) and
  the suggested warning was not added. Reported again as R5-4.
- Minors m16, m17, m18: fixed.

## New majors (failing tests in tests/review/M6b/r-words/)
- R5-1: a label written in bold with the colon inside the bold (`**Story:**`, `**Never show:**`, `**Palette:**`, `**Tone:**`)
  gives the value `*`. The result is logline/summary `*` at user precedence, the do-not rule `*` in brief.md, and palette_unparsed `['*']`. The answer below the
  label is lost to notes or folded into the summary. This is a regression: the old parser read `**Never show:**` + bullets as rules. Confirmed on real newton-vs-nye
  via DevRun: brief `Do not (the user's words): "*"`. test_rw5_bold_colon_labels.py (9 fail).
- R5-2: voice-first answers to "Which character is each voice?" (`V1 = C1 The Keeper`, the viewer block's own syntax,
  or `V1 is C1`) are not read by meaning. They become notes, or the logline when there is no heading. The voices stage
  maps the same text. test_rw5_voice_answers.py (4 fail).
- R5-3: a regression from the R4-3 fix. User text appended to interview lines that rule 0 drops (the voice fact bullets,
  the "Which character is each voice?" line) and sub-bullet answers under copied `## Open questions` are lost silently.
  test_rw5_voice_answers.py (4 fail).
- R5-4: R4-2 is only partly fixed. `Avoid at all costs`, `Things I don't want to see in the video`, `What I'd never want to see`,
  `No-nos` and `Hard limits` still go to notes, with no warning. test_rw5_do_not_headings.py (6 fail).

## Minor
- m19 (in docs/review/M6b-r-words.md, Round 5): `L005: both` / `everyone` is dropped silently.

## Real songs (W3 verify)
DevRun of meaning, brief and frames on the integrator's outputs for jeremy, newton-vs-nye and megafauna. All stages
are ok with 0 warnings and 0 lyric 9-gram hits in brief.md, meaning.md, interview.md and request.md. Briefs are about
1.6k-1.9k tokens. The lines.tsv singer column uses the `C3+C1` form (order is known minor m1). The only meaning.json
diffs from the integrator are notes and references (additive). Lifecycle on newton-vs-nye: intent.md is byte-identical after 2 runs, and the
line_singers bullet gives `C1+C2` in lines.tsv. tests/integration/M6b does not exist.

Suites: tests/review/M6b plus unit meaning/brief/frames give 420 passed, 12 skipped and 23 failed. The 23 failures are exactly the new R5 tests. Ruff is clean.
Probes are in out/_wip/r-words-m6b-r5/ (q1-q9, life.py, real.py, real.log).
