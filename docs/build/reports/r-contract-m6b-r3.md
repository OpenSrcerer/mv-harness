# r-contract-m6b-r3: round-3 R-CONTRACT review of M6b (meaning, brief, frames, skill)

Lens: the video agent (Remotion / three.js / Blender / ComfyUI) working from one song folder plus
`skill/mv-harness/SKILL.md`. Inputs: synth fixture (invented lyrics) and the four real W0 fixtures via DevRun, plus
a full `mvh analyze` of the synth song for the frames verb. No real lyric text appears here or in any test.

Verdict: **fail**. 5 majors (each with a failing test), 5 minors (docs/review/M6b-r-contract.md "Round 3").

## Round-2 findings: re-check

| id | status | how it was checked |
|---|---|---|
| R2-1 / N1 untouched template flips to user | **fixed** | template placeholders are `""`; fallback V1 link is `proposed`; review tests pass, and the code no longer prefills a value the user did not give |
| R2-2 / N3 template mixed with free text | **partly fixed -> R3-2** | the marker/key-line region parser handles story-before, open-fence and prose-after. When the unfenced template does NOT parse, its example comments are still read as user claims |
| R2-3 / N4 lowercase `palette:` free text read as YAML | fixed | needs 2 template keys, no other `key:` line and no comment-cut value; p2.py |
| R2-4 / N5 draft-filled character fields shown as user | fixed | `characters[].field_sources`; the brief row says `(draft name + description)`; the template prefills only intent values |
| R2-5 / N6 skill does not mention field_sources | fixed | SKILL §3 and RECIPES document it and include an `isDraft` recipe (minor r3-m3: `audio` counted as draft) |
| R2-6 frames verb exits 0 when the stage did not run | **fixed, verified end to end** | real `mvh analyze` of the synth song, then `mvh frames`. Another module changed `separate_hq` params, so upstream went stale; the verb exited 1 with `not_run: upstream not done: ...` and listed no stale CSV. Run settings are written before the run, so `status()` sees the new rates |
| N2 do-not labels | **fixed, but over-captures -> R3-3, R3-4** | `**Never show**`, `Never show: X` and `## Don'ts` are recognised. The new label block and the wider heading regex now swallow other content |

## New / reopened majors

- **R3-1** (new): the template's own palette hint (`palette: []   # hex (#1b2a49) ...`) leads users to type
  `[#c93523, night blue]`. That is a YAML ParserError, so the whole template is dropped: characters and do_not are lost. Fenced: the status
  goes back to pending. Unfenced: the status is user, with the R3-2 junk. Test: `test_r3_intent_parsing.py::test_hex_palette_as_the_template_hint_shows_keeps_the_answers`.
- **R3-2** (reopen R2-2/N3): when the unfenced template fails to parse (R3-1, or no marker line plus any `Key:` note),
  free text reads the template's example comments as user claims: `line_singers L005 = C1+C2` (singing.json L005
  `source: user`) and palette `#1b2a49` (field_sources user). Test: `::test_template_example_comments_never_become_user_claims`.
- **R3-3** (regression of the N2 fix): `Never show: blood` followed by a blank line and bullets turns the character bullets
  or section-note bullets into do-not rules, and the characters are lost. Tests: `::test_do_not_label_does_not_swallow_*`.
- **R3-4**: a title heading containing never/don't (`# Never Let Me Go`, `# Don't Stop Me Now: my notes`; `don't`
  was added by N2) makes the story, the character lines and the section notes into do-not rules. Test: `::test_title_heading_with_a_do_not_word_is_not_a_do_not_block`.
- **R3-5**: `perspective` (narrator/addressee) filled from authored.json has no top-level `field_sources` entry. Under
  `status: user` an agent that follows SKILL §3 takes the draft's who-sings-to-whom as the user's. Test: `test_r3_perspective_source.py`.

The parallel r-words round-3 reviewer found overlapping issues independently (tests/review/M6b/r-words/test_rw3_*.py:
hex palette, do-not over-capture, and the template dropping section do_not, motifs and symbolism on round-trip).

## Gate and runs

- `scripts\gate.ps1 M6b` (log out/_wip/r-contract-m6b-r3/gate.log): fixture, review, contract, validate, e2e (361 s) and lib-node PASS.
  unit FAIL only in tests/unit/contract (not M6b). ruff FAIL was transient: a re-run of `ruff check src tests` is clean.
  determinism FAIL comes from upstream modules, as in round 2.
- brief.md: synth with intent and authored.json is 1770 tokens; real fixtures are 882-1260 tokens (cap 4k).
- Probes: out/_wip/r-contract-m6b-r3/p1-p5.py, run_scen.py, e2e/.

## Addendum (resumed after power outage)

- `mvh frames` on the stale folder again exited 1 with `not_run: upstream not done: lyrics (stale), ...` and listed no CSV (R2-6 fix re-confirmed).
- After a fresh `mvh analyze` (rc 0), `mvh frames --fps 24 --fps 24000/1001 --frame0 1` exited 0 and wrote `frames/24_f1fps.csv`
  (1356 rows) and `frames/24000-1001_f1fps.csv` (1355 rows). Names follow CONTRACT §14; `t` equals `time_of(n)` on every row (0 mismatches);
  row counts agree with `frame_count`. No NaN/inf. Empty cells appear only in the event columns (section_id, bar, line_id, singer, cue_*), never in a
  curve channel. The singer column uses `C1+C2` for multi-singer lines (D38).
- Re-run of tests/review/M6b plus unit meaning/brief/frames: 18 failed (the 9 r-contract R3 tests and 9 r-words R3 tests, all for the stated reasons), 123 passed, 12 skipped.
