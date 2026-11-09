# critic-w3 report (W3 completeness critic, R-CONTRACT lens)

**Verdict: pass-with-fixes.** Every Must from R1 to R20 has a producing stage, a test and output in all four real songs and
the synthetic song. Licences are recorded in run.json and in each model's provenance. The JS and Python loaders agree on
real folders. The R19 override round trip works end to end.

Six new majors make parts of the output unusable for a choreography or character agent:
- groove ids;
- syncopation;
- the half-time feel label;
- Jeremy's hats;
- rap hand-offs;
- boundary edits that are not local.

The open SEAMS S03, S04, S05, S06, S07 and S09 still apply and were not filed again. No blocker was found.

Full matrix: `docs/review/W3-completeness.md`. It has one row per R1-R20 and per §4 file: producing stage, tests,
per-song plausibility numbers, usability and licence.

## What I did
1. I read PLAN (§2, §4, §5, §7, §11, §12), SPIKE, the CONTRACT layout/IDs/values/§6-7/§9, SKILL.md, RECIPES.md, SEAMS.md,
   W2-open-findings and the integrator's progress file.
2. I probed the 5 max-run folders (`out/_wip/integrator/<slug>`) through each folder's own `lib/mvh_load.py`. All probe
   scripts and outputs are in `out/_wip/critic-w3/`; they print numbers only, never lyric text.
   - Beat grid against the drums: phase histograms of kicks, snares and hats against `beats.json`, and the share of hits
     within 1/32 beat of a 16th position. The kicks confirm the grid on JR, NN, VS and SY. MF is weaker but still on the 16th grid.
   - Sections against the song form: voice changes against section starts on NN (3 of 4 within 0.7 s); the EDM roles on VS and MF.
   - Singers against voice changes: line and row overlaps, per-voice mouth curves, `singer_at` and `lyric_at`.
   - JS against Python: `jsprobe.mjs` and `pyprobe.py`, with Node 26 on NN and JR, 6 instants each. All fields matched.
   - MIDI tempo maps (mido), licences (run.json against every provenance block), `mvh brief --section`, `mvh frames`.
3. R19 round trip on a copy of the synthetic folder (`out/_wip/critic-w3/rt-synth`, driven by `rt_step.ps1`):
   - step 1 adds the synthetic intent and authored files;
   - step 2 adds `overrides.json` with a structure move and a label.

   It works mechanically, but it showed W3C-6.
4. I wrote failing tests in `tests/review/W3/critic/` (ruff clean). 15 fail as intended and 3 controls pass.

## Findings (all major; owner first)
| ID | Location | Claim | Test |
|---|---|---|---|
| W3C-1 | M2 choreo groove clustering | groove ids nearly one per bar (JR 91/124; 31 identical kick/snare bars over 14 ids; MF 57/63; VS 60/80; NN 38/88) | test_w3c_grooves.py |
| W3C-2 | M2 choreo `syncopation()` | 8th-note syncopation always scores 0 (85 % of JR's and 100 % of NN's syncopated bars) | test_w3c_grooves.py |
| W3C-3 | M2 rhythm `feel_labels` | NN 76 % of strong snares on beat 3 (half time), feel 'normal' | test_w3c_feel.py |
| W3C-4 | M3a drums drumsep_hits (hihat) | JR hats 37 % on the 16th grid (chance 25 %, kick/snare about 90 %) | test_w3c_hats.py |
| W3C-5 | M5 lyrics `_finalise_line` sustain (+ singing, lipsync, lib singer_at) | NN: lines overlap 1.4 s, so two singers show and two mouths open at every rapper hand-off; singer_at duplicates | test_w3c_handoffs.py |
| W3C-6 | M2 structure overrides + global DP | moving one boundary moves others (17->21 turns the build start 25.0 into 29.0) | test_w3c_override_locality.py |

Minor findings m1-m7 are in the matrix (§4). They cover the stale `key:key:` in brief.md, review flags on one-voice
grade-D songs, NN S06 one bar late, the manifest near its token cap, 5 unclear licences, sections.edm_role set only on a
drop's first section, and the SKILL frames file name.

## Change requests
None. Every fix lies inside a module's own paths.

## Notes for the integrator-r2
- The real-folder tests read `out/_wip/integrator/<slug>`. Re-run the max analyses after the fixes; the tests skip when a folder is absent.
- The integrator's folders are already stale against the current code. Module fixers changed structure params
  (bar_jitter_frames, short_section_margin, impact_snap_strength), so `mvh status` reports structure and its dependants as stale.
- `out/_wip/critic-w3/rt-synth` (about 250 MB) can be deleted after review.
