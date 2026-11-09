# w4fix-words report (W4 fixer, words group M5 + M6b, round 1)

## Findings fixed
| id | fix | test |
|---|---|---|
| W4A-UD1 (major, M6b) | `meaning/intent.py`: tabs in indentation (and between `-` and the item) expand to spaces (tab stop 4) and a plain value holding a tab is quoted; blank lines between a valueless key and its column-0 `- ` items keep the region open; `do_not` (and `symbolism`, `notes`, `themes`, `references`, `palette`) are parsed entry by entry when the key fails, and an entry starts at EVERY line at the entries' indent, so a stray sentence becomes its own warned note and the rules survive. Demotions are recorded (`unparsed_keys`) and surfaced: meaning.json `intent_unparsed` (additive), the first open question, and a bold brief.md line ("rules typed under do_not may be missing"). SKILL.md tells agents what to do. | tests/review/W4/adversary/test_w4a_ud1_do_not.py 5/5 pass; new tests/unit/meaning/test_intent_w4_do_not.py (10) |
| W4A-S16 / S16 (major, M5) | `voices` 1.3.0: backing (duet) spans are gated by `stem_activity` backing_vocals: a line backed >= `backing_min_support` (0.5, new param) keeps the whole line; else the span is trimmed to the active hull (>= min_item_s and itself >= 0.5 backed) and embedded there; else dropped. Newton L021 (0.44 s of backing activity under a 1.97 s line) is no longer a backing span. Additive meta field `backing_unbacked_lines`. | backing test passes on the new outputs (fails on ud2-kick); new tests/unit/voices/test_backing_window.py (6) |
| W4D-2/3/4 (major, dogfood, skill docs; skill/** is owned here) | `skill/mv-harness/references/RECIPES.md`: kicks via `song.pulse('kick', t)` / `song.kicks().inFrame()` (no `drums.kick` curve), palette fallback to the cover-art palette (`manifest.summary.palette`) while meaning is pending, a "Serving a song folder" section (no file://, Range support, what to ship / not ship). | tests/review/W4/dogfood 8/8 pass; M6b recipes-runnable pass |

## Real reruns (no regression)
`mvh analyze --only` on copies is impossible now (contract rc.2 -> rc.3 makes every cached stage stale; other fixers
change upstream too), so the words stages ran in-process on the cached upstream of `out/_wip/ud2-kick/<slug>`
(driver `out/_wip/w4fix-words/scripts/drive.py`, from fixer-m5-r4; outputs `out/_wip/w4fix-words/<slug>/<stage>`;
compare `out/_wip/w4fix-words/scripts/compare.py`). Numbers only:

| song | lead spans | backing spans | two mouths open (100 Hz) | meaning / brief |
|---|---|---|---|---|
| newton-vs-nye | 54 identical | 1 (L021, 22 % backed) -> 0 | 2.29 s -> 0.20 s (critic limit 1.5 s) | meaning same; brief 2 rows: C1 lead (was both), S04 singer C3 (was C1+C3) |
| synth | 9 identical | 3 (100 % backed) -> same 3 | 8.44 s -> 8.44 s (the fixture's real duet) | identical |
| jeremy / megafauna / versatile | identical | 0 -> 0 | 0 -> 0 | identical |

The adversary backing test passes on a minimal review folder (`out/_wip/w4fix-words/review/newton-vs-nye`: manifest,
stem_activity, new voice_spans; `MVH_REVIEW_RUNS` pointing at it). The W3 critic mouth-overlap test needs a published
folder (lib + packed curves): computed equivalently from the lipsync curves: 0.20 s <= 1.5 s. Both real-song tests
will pass once the integrator re-runs voices -> lipsync on Newton.

## Gates
- `gate.ps1 M5`: fixture, unit (contract, identity, lyrics, voices incl. ECAPA synth models, lipsync), review M5, ruff,
  contract, validate, e2e, lib-node PASS; determinism FAIL (22 files: meta/structure.json, sections, counts, cues ...,
  and everything downstream of structure). Log: docs/build/progress/w4fix-words.gate-M5.log.
- `gate.ps1 M6b`: unit (contract, meaning, brief, frames), review M6b, contract, validate, e2e, lib-node PASS;
  ruff FAIL (2 errors, both in src/mvh/stages/structure/__init__.py:645, a `# TEMP debug` import of another fixer);
  determinism FAIL (33 files incl. meta/tempo.json, hits.kick, drums, structure). Log: .gate-M6b.log.
- Both determinism failures come from other fixers editing rhythm / structure / drums code between the two
  `analyze --force` runs (the same gate run). Words stages checked on their own: voices, lipsync, meaning and brief
  run twice on synth and Newton by the driver give byte-identical files (all outputs incl. curves).
- ruff on every words-group path: clean.

## Not done / notes
- Not changed: free text that looks like a template key (`DO_NOT:`, indented `  do_not:`) stays a silent note: a
  warning there contradicts the UD1 property test (free text never warns). Left as is.
- Text inside an unlabelled ``` code fence that looks like template keys is parsed as template (pre-existing; the
  grammar says only the fence lines are dropped). Not reported by a reviewer; left.
