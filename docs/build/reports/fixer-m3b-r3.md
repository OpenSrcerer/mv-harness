# fixer-m3b-r3 report (M3b, W3 round 1)

Seam S04 (MEGAFAUNA: lyrics, voices and singing have a singer; vocals says none) fixed at the root.

Root causes
1. The karaoke split sent MEGAFAUNA's voice to backing (lead_vocals p95 -74 dBFS vs -19 for vocals), so RMVPE and the
   activity gate looked at an empty stem (RMVPE voiced 1.2 s).
2. On the full vocals stem RMVPE finds 46 s of pitch, but 37 s of it is the intro synth leads and only ~7 s lies in the 14
   aligned lyric lines; the tagger voice gate (inst.voice, 7 s in the whole song) rejected those 7 s too.

Changes (src/mvh/stages/vocals, src/mvh/stages/instruments/lead.py)
- vocals tracks the full vocals stem when lead_vocals is nearly silent (same 20 dB rule as lyrics), only when lyric lines
  exist or stem_activity votes vocals present (keeps Versatile on lead_vocals unless the stem vote says otherwise).
- lyrics is a new dependency of vocals. Pitched frames inside lyric lines (+-0.15 s) pass the voice gate and count as sung when the
  tagger gave them no style. Presence also holds with >= 4 pitched s inside >= 20 s of lines (stats need 4 s; conf low).
  Frames outside the lines still need the tagger, so the synth leads stay rejected.
- Params: lead_gap_db, lyric_pad_s, lyric_min_voiced_s, lyric_min_s. Decisions I-M3b-13/14 in docs/contract/decisions/M3b.md.
- New unit test tests/unit/vocals/test_lyric_presence.py (3 tests).

Results on my copies of the integrator runs (out/_wip/fixer-m3b-r3/<slug>, full re-run of stale upstream)
- megafauna: present false -> true (6.96 voiced s, E3-E4, alto), 10 phrases, 33 vocal notes (were 0); lyrics 14 lines, singing 14.
- synth: identical. newton-vs-nye: identical. jeremy: +2 voiced s inside lines (194.0 -> 196.3), 42 -> 41 phrases, 588 -> 589 notes,
  same range E3-C#5 tenor. versatile (harness run): voiced 2.9 -> 5.6 s, 6 -> 10 phrases, 16 -> 27 notes, present stays false
  (the vocals stem vote is true there, so the stem fallback applies).
- notes and instruments outputs unchanged (bass/guitar/other/piano note counts identical on all songs).

Gate (out/_wip/fixer-m3b-r3/gate.log): tests/review/M3b pass, unit notes/vocals/instruments pass (13/17+4 skipped/11), e2e and
validate pass, ruff clean after fix. Remaining FAILs are not in M3b files: tests/unit/contract::test_deps_match_plan (needs the
vocals PLAN_DEPS line to gain "lyrics") and test_generated_artifacts_up_to_date / contract --check (docs/CONTRACT.md is out of date).
The tests/integration/M3b test reads out/_wip/integrator, so it passes once the integrator re-runs vocals (my copy: 14 lines, 14 singing,
present true, 10 phrases).
