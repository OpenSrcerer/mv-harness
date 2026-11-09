# M6b review, lens R-WORDS (reviewer r-words-m6b): minor findings

Scope: the meaning stage (intent parsing, draft merge, citations, re-anchoring, singing.json / lines.tsv), the meaning
parts of brief.md, and the lyric-privacy surface of meaning / brief / frames. Blockers and majors are failing tests
under `tests/review/M6b/r-words/` (see `docs/build/reports/r-words-m6b.md`). Each item below was checked by running code
(probe scripts in `out/_wip/r-words-m6b/probe*.py`, synthetic fixture only).

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | `src/mvh/stages/meaning/singing.py` join_singing (the `order` loop) | D38 says the `singer` cell is "lead first (then by voice number)", and `conventions.singer_at` orders lead, then voice number. join_singing orders leads by **time** first, so a line where V2 then V1 trade words (both lead) gets `C2+C1` in lines.tsv while `singerAt` returns C1 first. | probe4: spans V2 0.0-1.5 s, V1 2.0-3.5 s, both lead -> `singers['L001'] == ['C2', 'C1']`. | Sort leads by (voice number, t), like `singer_at`; or amend D38 / decision #4 and conventions together. |
| m2 | `src/mvh/stages/meaning/intent.py` `_section_notes`; `anchor.py` | Free-text notes keyed by a section id (`S03: ...`, explicitly supported) carry no time range, so after a structure change they silently attach to whatever section is now `S03` (no re-anchor, no orphan, no warning). PLAN §8.5 wants every per-section claim to keep section_id + t_range. | `anchor_claim({'key': 'S03', 't0': None, 't1': None}, new_sections)` -> `how: 'id'`, anchored to the new S03 whatever its time. | Add an open question / note listing free-text S-id notes ("cannot follow section changes; use the template or a label"), or have interview.md advise labels (`chorus#2:`) in free text. |
| m3 | `stage.py` draft section loop + `_orphan` | A draft section entry with `t0`/`t1` but no `section_id` is orphaned with reason "no section is a " and a fabricated `old_section_id: "S00"` instead of being anchored by time. | probe7: draft section {t0 17, t1 25} -> orphans `[('S00', 'no section is a ')]`, S03 gets nothing. | In `anchor_claim`, use the time path whenever t0/t1 are present and the key is not a label/occurrence; give the orphan a clear reason. |
| m4 | `src/mvh/stages/meaning/cites.py` `_fix_cites` | The <= 10-word quote check counts whitespace-separated tokens, so a CJK/Japanese quote of any length counts as one word. | `'夜空に灯るランタンが川を流れていく'.split()` has length 1. | Count words with a Unicode-aware tokenizer (or a character cap for scripts without spaces). |
| m5 | `stage.py` (`draft asks:` / `draft suggests a do-not rule`) | A draft's `open_questions` and `do_not` strings are copied verbatim into meaning.json `open_questions`, interview.md and meaning.md with no quote-length or lyric check. | read of stage.py lines 374-379; no `check_claims` pass over these strings. | Run the same quote / lyric-overlap check as for claims (see major F6) or cap their length. |
| m6 | `src/mvh/stages/meaning/llm_draft.py` `_problems` | The `--draft anthropic` path validates citations against a smaller id set than the stage (no word ids, EDM roles, text/line groups, tier 2-4 cues), so it **drops valid citations** and writes the damaged draft to `meaning/authored.json` (an input the stage never repairs). | probe8: cites `L001.02`, `R01` -> "does not exist (dropped)" in `_problems`; the stage merge keeps both. | Build the known-id set with the same `collect_ids` inputs as `stage.build` (lyrics words, edm_roles, cues, text/repeat groups), or skip id repair in `_problems` and let the merge do it. |
| m7 | `src/mvh/stages/meaning/docs.py` interview hooks | With `lyrics_to_agents=false` the interview says the hook text is "in lines.tsv", but the same setting blanks the `text` column of lines.tsv. | `docs.py` line with `'text in lines.tsv'`; `stage.py` writes `text: ""` when the flag is off. | Point to `lyrics/lyrics.json` (user-only) or just give the line ids. |
| m8 | `src/mvh/stages/brief/build.py` `_status_line` | `singers:review=N` counts singing.json **items**, not lines: a line with two flagged spans counts twice, so the number does not match `meaning.json` / interview "N lyric line(s) have a low-confidence singer". | `sum(1 for x in ev_singing if x.get('review'))`. | Count distinct `line_id`s. |
| m9 | `tests/unit/brief/test_brief.py::test_real_brief` (line ~168) | On failure, `assert ln["text"] not in text` makes pytest print a **real** lyric line (and a slice of brief.md) into the test output, which the privacy rule forbids. | pytest assertion rewriting shows both operands of `not in`. | Assert on a count: `assert not [i for i, ln in enumerate(lines) if ln['text'] in text]`, or compare hashes. |
| m10 | runtime CLI (`mvh analyze`), not M6b code | PLAN §10 flags `--intent`, `--meaning-draft` and `--no-lyrics-to-agents` do not exist on `mvh analyze` (`mvh analyze --help`); request.md / brief CLI messages name `--no-lyrics-to-agents`, which only `mvh meaning` accepts. Users must know `--param meaning.lyrics_to_agents=false`. | `mvh analyze --help` output. | W3 integrator: add the three analyze flags mapped to `meaning.*` params (change request), or reword the M6b messages. |

## Round 2 (reviewer r-words-m6b-r2)

All 16 round-1 review tests now pass. The round-1 fixes for F5 (no draft text in warnings), F6 (lyric runs cut from
draft free text, logline capped at 40 words in the brief) and F2 (settled user characters ignore voices-stage
proposals) are real fixes, not test-specific hacks. F1, F3 and F4 (and r-contract F2 and F3) are only partly fixed. The
blockers and majors are failing tests in `tests/review/M6b/r-words/test_rw2_*.py` (see
`docs/build/reports/r-words-m6b-r2.md`). The probes are in `out/_wip/r-words-m6b-r2/` and use the synthetic fixture
and lyric-free real fixtures only.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m11 | `src/mvh/stages/meaning/cites.py` `cut_lyric_runs` / `_WORD` | The 11-word overlap check does not normalise typographic apostrophes. If the lyrics use `'` and the draft quotes them with `’` (or the reverse), every contraction splits into two tokens and breaks the run. A 20-word quote with contractions every 6-7 words passes uncut. | Probe: a 20-word lyric with 4 contractions. Straight apostrophes give 1 cut; curly apostrophes give 0 cuts. | Before building n-grams, NFKC-normalise both texts and map `’ ‘ ʼ` to `'` (or drop apostrophes). |
| m12 | `src/mvh/stages/brief/build.py` `_is_draft` (zoom `tag()`) | Every field whose `field_sources` value is not `user` is tagged `(draft)`, including harness facts (`characters_present: audio`, `emotion.audio`). When the stage falls back to `provenance.status`, an audio-only emotion is also tagged `(draft)`. The zoom therefore tells agents that an agent wrote facts, even when no authored.json exists. | `probe_zoom.py` uses synth intent.md with no draft. S02 shows `- characters: C1, C2 (draft)` (field_sources `audio`), and S06 shows `- emotion: ... audio melancholic ... (draft)`. | Return true only for `fs[field] == "draft"`. Optionally tag audio facts `(audio)`. |
| m13 | `src/mvh/stages/meaning/stage.py` `perspective` | `perspective.narrator` / `addressee` is merged from the user and the draft with no `field_sources` entry. When the user gave one and the draft gave the other, nothing in the meaning output shows that the second one is a draft. | Read of stage.py lines 354-355: `gsrc` has no `perspective` key. | Add `field_sources["perspective.narrator"]` / `["perspective.addressee"]`. |

## Round 3 (reviewer r-words-m6b-r3)

Round-2 majors re-checked by running code (probes in `out/_wip/r-words-m6b-r3/`): R2-1/N1 (untouched template on
synth, synth without voices, synth without lyrics and the four real fixtures, fenced and unfenced, with and without a
draft: the status never changes), R2-2/N3 and R2-3/N4 (template region + marker/two-key rule), R2-4/N5
(`characters[].field_sources`, brief `(draft name + description)`, template prefills the user's own fields only),
R2-5/N6 (SKILL.md and RECIPES.md document `field_sources`), R2-6 (frames verb always checks the stage status) and N2
(do-not labels) are fixed. New majors R3-1..R3-3 are in `docs/build/reports/r-words-m6b-r3.md` with failing tests
`tests/review/M6b/r-words/test_rw3_*.py`. Minors:

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m14 | `src/mvh/stages/meaning/intent.py` `_parse_text` (no-heading summary) | A file with no headings whose lines are section notes is also taken whole as the user's summary, and the first note becomes the logline. | `parse_intent("Intro: slow drift.\nDrop: wide shots.\n")` -> logline `Intro: slow drift.`, summary both notes, plus the two section claims. | Exclude section-note lines (`_SEC_KEY` at line start) from the no-heading summary, like the `C1`/`L001`/palette lines. |
| m15 | `intent.py` `_template_region` (no marker) | Without the `# mvh-intent` marker, one trailing user comment on a template key line (`tone: dark and slow   # my note`) makes the whole template free text: logline, tone and every other answer are lost (only the generic warning). | p6_minor.py: form `text`, logline None, tone None. | Check the `" #"` rule only on keys whose YAML value would actually lose text (compare the YAML value with the raw text before the comment), or keep the parse when the lost part follows two or more spaces. |
| m16 | `skill/mv-harness/references/RECIPES.md` `isDraft` | The recipe treats every non-`user` field source as a draft, so harness facts (`characters_present: audio`, `emotion.audio`) are shown to agents as agent drafts (same root as m12). | RECIPES line `... !== 'user'`. | `=== 'draft'`, and present `audio` as a measured fact. |

## Round 4 (reviewer r-words-m6b-r4, W3 verify)

All 8 round-3 findings (R-CONTRACT R3-1..R3-5, R-WORDS R3-1..R3-3) are fixed. The fix is a real rewrite of the parser, not a set of test-specific hacks: intent.py now has one documented grammar (grammar v2), and docs.yaml_template writes every user claim back. Re-checked with variants outside the tests: hex values in flow lists without spaces, block lists at column 0 and indented, 3-digit hex, hex in section palettes, a broken YAML key next to good ones (the good ones are kept), and the hint comment kept after the answer. Round-3 minors m14 and m15 are also fixed. m16 is still open: RECIPES `isDraft` still uses `!== 'user'`.

New majors R4-1..R4-3 have failing tests in tests/review/M6b/r-words/test_rw4_*.py. Minors:

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m17 | `intent.py` `_cut_comment` (one-space comment) | When the user deletes the `[]` and the spaces before the hint, the hint's example colour becomes a user colour. `palette: #c93523 # hex (#1b2a49) or colour words` gives palette `['#c93523', '#1b2a49']`. | p4.py `plain_hint_onespace`, fenced and unfenced. | Treat a comment whose text matches the template's own hint text as a comment whatever the spacing. Or move the hex example from the comment to the separate `# Hex colours ...` comment line. |
| m18 | `src/mvh/stages/brief/build.py` (meaning block) | The user-sourced `notes` and `references` in meaning.json (new in W3) are not in brief.md, the LLM entry point. SKILL.md does not mention them either. Grammar v2 sends every user line it cannot classify to `notes`, so those words reach only meaning.md. | grep: brief/build.py has no `notes`/`references`; docs.py prints `## Notes (user)` only in meaning.md. | Add one brief line, e.g. "User notes: N (meaning/meaning.json notes)", plus references. Mention both in SKILL §3. |

## Round 5 (reviewer r-words-m6b-r5, W3 verify)

R4-1 and R4-3 are fixed, and the fixes are real grammar changes (grammar v3), not test hacks. For R4-1, key + bullet answers were checked for every map key with col-0 and indented bullets, one-key maps, nested maps, bold ids and colons inside names; the probe is `out/_wip/r-words-m6b-r5/q3.py`. For R4-3, the interviews of synth and all 4 real fixtures were checked: an untouched paste stays `pending`, and answers written under the question or on the question line, numbered or not, land in the right fields (`q4.py`). R4-2 is fixed only for the cases it named. Common variants still fall to notes with no warning, so they are reported again as R5-4. Minors m16, m17 and m18 are fixed.

New majors R5-1..R5-4 have failing tests in `tests/review/M6b/r-words/test_rw5_*.py`. Minor:

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m19 | `intent.py` `_apply_yaml` line_singers / `_LINE_SINGER` | A per-line singer fix that names no character id (`L005: both`, `L005: everyone`, free text `L005: both of them`) is dropped silently, with no warning and nothing kept in notes. The interview's "Check the singer" question invites this kind of answer. | `q9.py`: `line_singers:\n- L005: both`, `line_singers:\n  L005: everyone` and `L005: both of them` all give line_singers `{}`, notes `[]`, warnings `[]`. | Warn ("L005: no character id (use C1+C2)") and keep the text in notes. Optionally map `both`/`all`/`everyone` to the characters of the voices on that line. |
