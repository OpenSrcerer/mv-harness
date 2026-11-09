# w4fix-words progress (W4 fixer, words group M5/M6b, round 1)

## Findings
- W4A-UD1 (meaning/intent.py do_not demotion): tests/review/W4/adversary/test_w4a_ud1_do_not.py
- W4A-S16 / S16 (voices backing span not backed by backing stem, Newton L021): test_w4a_real_seams.py::test_w4a_backing_spans..., W3 critic test_w3c_handoffs.py

## Done
- (start) read tests + code. Plan: intent.py tabs/do_not per-item/blank-line; voices backing span gated by stem_activity backing_vocals.

## Next
- implement, unit tests, rerun voices.. on copies of out/_wip/ud2-kick/<slug> (newest), gates M5, M6b.

## Milestone 1 (code done, fast tests pass: 1025 passed)
- intent.py: _expand_indent (tabs), _chunks(entries=True), do_not+list keys in _NESTED, blank lines keep list_ok, tab-in-value quoted, unparsed_keys.
- stage.py: intent_unparsed -> meaning.json intent_unparsed + open question first; brief build.py: bold line when entries did not parse.
- voices core.py: backing_window + _backing_activity (stem_activity backing_vocals), param backing_min_support 0.5, version 1.3.0, meta backing_unbacked_lines.
- tests: tests/unit/voices/test_backing_window.py, tests/unit/meaning/test_intent_w4_do_not.py
- Next: real reruns on copies of out/_wip/ud2-kick/<slug> into out/_wip/w4fix-words/<slug>; gates M5, M6b; decisions doc; report.

## Milestone 2: real reruns
- mvh analyze --only on copies fails: contract rc.2 -> rc.3 makes every stage stale (and other fixers change upstream).
  So: in-process driver out/_wip/w4fix-words/scripts/drive.py (from fixer-m5-r4 m5drive.py) on out/_wip/ud2-kick/<slug> cached upstream;
  outputs out/_wip/w4fix-words/<slug>/<stage>. Resume: sh out/_wip/w4fix-words/scripts/drive.sh newton-vs-nye synth jeremy megafauna versatile (<slug>.DONE markers).
- decisions doc docs/contract/decisions/W4-words.md written; SKILL.md line added.
- Newton driven: lead spans identical (hash), backing span L021 dropped, two-mouths-open 2.29 s -> 0.20 s (100 Hz curves),
  meaning unchanged, brief: C1 (both)->(lead), S04 C1+C3 -> C3. Adversary backing test passes on review/newton-vs-nye
  (minimal folder: manifest + stem_activity + new voice_spans; MVH_REVIEW_RUNS=out/_wip/w4fix-words/review), fails on old.
- compare: powershell run.ps1 python out/_wip/w4fix-words/scripts/compare.py [slugs]
- gates running bg: docs/build/progress/w4fix-words.gate-M5.log then gate-M6b.log
- ALL 5 driven. Only Newton changes (backing span dropped). synth/jeremy/megafauna/versatile: spans, mouths, meaning, brief identical.
- Next: wait gates (M5 then M6b), then report docs/build/reports/w4fix-words.md.
- Extra (owned skill/**): W4D-2/3/4 dogfood doc tests fixed in skill/mv-harness/references/RECIPES.md (kicks(), cover-art palette fallback, serving: file://, Range, what to ship). tests/review/W4/dogfood 8 pass.
- Tried a free-text "near template key" warning: REVERTED (contradicts test_intent_property: free text never warns).
- Report drafted docs/build/reports/w4fix-words.md; waiting on gates M5 (e2e/determinism) and M6b.
- Gates done: M5 all PASS except determinism (foreign: structure/rhythm edits mid-gate); M6b all PASS except ruff (structure TEMP debug, foreign) + determinism (foreign). Words stages determinism verified via driver twice (identical sha256). DONE; report final.
