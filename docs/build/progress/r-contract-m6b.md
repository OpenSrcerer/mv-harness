# r-contract-m6b progress (R-CONTRACT review of M6b: meaning, brief, frames, skill/)

## Done
- Read PLAN §4/§8/§10/§11, SPIKE, CONTRACT §1-4, §6 (singing/counts/cues), §7 meaning files, §9, §11-14, catalog entries, SKILL.md, RECIPES.md.
- DevRun of meaning/brief/frames on synth + 4 real fixtures: out/_wip/r-contract-m6b/devrun_all.py (dev/<slug>/song).
- synth with intent/draft/both: devrun_user.py; draft do_not handling: devrun_dodraft.py (draft do_not -> open question; OK).
- frames parity vs conventions (curves, t, cue_id, hit, section, count, singer) on synth/newton/jeremy, 4 frame rules: all match (parity_frames.py).
- strict per-block brief trace (trace_strict.py): 0 untraced decimals on synth-both, newton, jeremy, megafauna.
- singing.json/lines.tsv on synth == fixture truth (cmp_singing.py).
- FAILING tests written: tests/review/M6b/r-contract/test_recipes_runnable.py (+ remotion_recipe.mjs) [F1 Remotion include list],
  test_draft_fields_labelled.py [F2 draft fields shown as user in zoom]. Both fail now for the stated reason.
- Full `mvh analyze` of synth started in background (log out/_wip/r-contract-m6b-synth.err); heavy slots busy.

## Next
- When analyze finishes: mvh validate, mvh frames CLI (--fps 24000/1001, --frame0 1), mvh meaning, mvh brief --section on full folder.
- Edge cases: 10 s file, intent YAML template.
- Write docs/review/M6b-r-contract.md (minors) and docs/build/reports/r-contract-m6b.md.

## Commands that worked
- MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-contract-m6b/<script>.py
- uv run --frozen --no-sync python -m pytest -q -p no:cacheprovider tests/review/M6b/r-contract

## Final (review complete)
- F3 blocker: tests/review/M6b/r-contract/test_intent_template_copy.py (unfenced YAML template -> free text, do_not dropped).
- Minors written to docs/review/M6b-r-contract.md; report at docs/build/reports/r-contract-m6b.md.
- Review tests: 5 failed, 1 passed (precondition); ruff clean.
- Full synth analyze stopped (stuck waiting for shared heavy slots); end-to-end CLI (mvh frames/meaning/validate on a full folder) not run.

## Resume check (after interruption)
- Re-ran tests/review/M6b/r-contract: still 5 failed, 1 passed (same reasons). meaning/cli.py, frames/cli.py changed later (21:59) but m11 still holds (only = meaning, brief[, viewer]). Structured summary returned.
