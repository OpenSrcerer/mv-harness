# r-words-m6b-r2: round-2 review of M6b (meaning, brief, frames), lens R-WORDS

Verdict: **fail**. Three round-1 findings are not fully fixed (r-words F3 and F4, r-contract F3). The F3 fix introduced a
regression (N4). Draft text still reaches agents as the user's (N5, N6). There are no new blockers; all findings below
are major.

## Method
- All 16 round-1 review tests pass (tests/review/M6b/r-words and r-contract). M6b unit tests: 84 passed, 12 skipped.
- Read the fixed code: meaning/intent.py, stage.py, singing.py, cites.py, docs.py `yaml_template`, brief/build.py, and RECIPES/SKILL.
- Probes are in `out/_wip/r-words-m6b-r2/probe_*.py`. They use the synthetic fixture and the real-megafauna/versatile fixtures,
  which have no lyrics. Real lyric text was never printed; only apostrophe counts were taken from real-jeremy and newton-vs-nye.
- New evidence: 12 failing tests, each verified to fail for its stated reason, in `tests/review/M6b/r-words/test_rw2_intent_reopened.py`
  and `test_rw2_draft_labels.py`. Ruff is clean.

## Round-1 findings: status
| finding | status | note |
|---|---|---|
| r-contract F1 (Remotion include) | fixed | uses `helper:*` includes |
| r-contract F2 (mixed section labelled user) | partly | brief and zoom now tag each field `(draft)`, but SKILL/RECIPES still teach `provenance.status === 'draft'` and never mention `field_sources` (N6) |
| r-contract F3 (unfenced template) | partly | works only when the whole file parses as YAML. One appended markdown note brings back `{name` names, comment feels and the lost do_not rule (N3). The check also caused regression N4 |
| r-words F1 (brief draft labels) | partly | logline, palette and feel are labelled. A user character's name/description filled from the draft is not labelled anywhere (N5) |
| r-words F2 (voice proposal merge) | fixed | the `settled` set is a real fix; probed the 2- and 3-character cases |
| r-words F3 (do-not bullet -> feel) | partly | only `#` headings are handled. The interview's own `**Never show**` label, `Never show: ...` and `## Don'ts` still lose the rule and turn it into a feel or the logline (N2) |
| r-words F4 (untouched template) | partly | still fails when the song has no characters: the placeholder `lead_backing: lead` counts as an answer (instrumental songs; real-megafauna and real-versatile) (N1) |
| r-words F5 (warnings quote draft text) | fixed | `_fix_cites` and the motif check no longer echo values. `kind_of` anchoring was probed with id-plus-text strings |
| r-words F6 (draft quotes > 10 lyric words) | fixed (minor gap m11) | `cut_lyric_runs` covers all draft free text and the brief logline is capped. Apostrophe normalisation is missing (m11) |

## Findings (major)
- **N1** `docs.py` `yaml_template` (no-character branch) and `intent.py` `_parse_yaml`: an untouched template for a song with no characters flips the status to user. Test: `test_rw2_intent_reopened.py::test_untouched_template_of_a_song_without_characters_is_not_an_answer` (+ real megafauna/versatile).
- **N2** `intent.py` `_DO_NOT_HEAD` / `_parse_text`: do-not answers in the interview's own `**Never show**` form, as a single `Never show:` line, or under `## Don'ts` are lost. They become the chorus feel or the logline.
- **N3** `intent.py` `parse_intent`: an unfenced template followed by markdown falls back to free text. The template's do_not is lost, YAML syntax becomes character names, and template comments become the feel of every section.
- **N4** (regression) `intent.py` `_looks_like_template`: a free-text file whose first line is a lowercase key such as `logline:` or `palette:` is parsed as YAML. The `#hex` colours are read as comments and lost, and the section notes are dropped. There is no warning.
- **N5** `singing.py` `build_characters` (`filled_by_draft`), `stage.py` `characters_out`, `brief/build.py` `_meaning_block`, `docs.py` `yaml_template`: a draft name or description is shown as the user's, and the template prefills it as the user's answer.
- **N6** `skill/mv-harness/SKILL.md` and `references/RECIPES.md`: there is no `field_sources` guidance. On synth, sections S01, S02, S04 and S05 (status user) carry draft hints that agents will treat as the user's.

## Minor findings
m11 to m13 are in `docs/review/M6b-r-words.md` (Round 2): apostrophe normalisation in `cut_lyric_runs`; the zoom tags audio facts `(draft)`; `perspective` has no field source.
