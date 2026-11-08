# fixer-m6b-r2 report (M6b round 2)

All 39 tests in tests/review/M6b pass with real fixes; tests/unit/{meaning,brief,frames} pass; ruff clean.

## Fixes
- R2-1 / N1: the interview template prefills nothing non-empty (`lead_backing: ""`, voice proposals only in comments);
  the fallback V1 link is stamped `proposed` (default of `voice_mapping` is now `proposed`, never `user`).
- R2-2 / R2-3 / N3 / N4: `intent.py` finds the unfenced template as a region (`# mvh-intent` marker, or >= 2 template keys,
  no other `key:` line and no value a `#` would truncate); the text around it is parsed as free text. Template-shaped lines
  (`{name:` flow maps, `# label` comments) are never read as free text. Unknown top-level YAML keys give a warning.
- N2: do-not labels (`**Never show**`, `Never show: ...`, `Don'ts`, `Avoid:`) start a do-not block; free-text do_not is merged
  with the YAML one.
- R2-4 / N5: `characters[].field_sources` (name/description user|draft); brief.md shows `(draft name + description)`;
  meaning.md notes it; the template prefills only the user's own fields.
- R2-5 / N6: SKILL.md and RECIPES.md document `field_sources` (sections, characters, top level) with a recipe.
- R2-6: `mvh frames` always checks the runner status of `frames` and exits 1 with `not_run` when not done. The unit fixture
  in tests/unit/frames now reports `done` after a successful write.

## Notes
- Decisions in docs/contract/decisions/M6b.md (Round 2).
- Change request: `song.meaningAt(t)` should return `field_sources`.
