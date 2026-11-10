# ffix-form report (final fix pass: honest section labels)

Status: done. Gate `scripts\gate.ps1 M2 -SkipE2E`: PASSED (unit, review M2, ruff, contract, validate, lib-node).

## Changes (structure 1.4.1 -> 1.5.0; decisions in docs/contract/decisions/F-form.md)
- `_chorus_evidence()` in src/mvh/stages/structure/__init__.py: a group keeps `chorus` only with recurrence (>= 2 separate
  occurrences), refrain share (<= 0.55 of the song) and a consistent allin1 vote (chorus - verse >= 0.15). Non-recurring choruses
  that near-repeat a recurring chorus keep it; otherwise allin1's best non-chorus label, with form slots (lone part between two
  occurrences of one chorus = bridge; non-recurring run after the last chorus into the outro = outro).
- Hook rule (W4V2-JEREMY-HOOK-VERSE): a non-repeated verse next to a recurring chorus occurrence that near-repeats it is chorus
  (not in the slot right before the chorus's first occurrence).
- W4V2-FORMRULE-NARROW: `verse_min_before_chorus` default 0.25 -> 0.0 (form condition alone).
- Additive `sections.label_evidence` (string[]) explains every label; `conf` is the label confidence.
- New params: chorus_min_margin, chorus_max_share, chorus_near_repeat, hook_verse_margin.
- Tests: tests/unit/structure/test_form_labels.py (7 fast tests on hand-made matrices); test_w4_stop_bar param assertion updated.

## Measured (structure re-run on cached upstreams; out/_wip/ffix-form/dev/{v2,v3}, logs v2.log/v3.log/chain.log)
| Song | Before | After |
|---|---|---|
| Newton vs Nye | 7/14 chorus | 0/14 chorus (11 verse, 2 outro, silence) |
| Jeremy (+gm6, gm12 identical) | 10/18 chorus, 176.12 s hook = verse | 7/18 chorus, hook = chorus, 220-288 s vamp (no lead lyrics) = outro; hook test violations 0 |
| Synth: base, sr22, sr32, sr48, tempo 0.9/0.95/1.05/1.1, gain +-12, mp3 | sr22: intro chorus chorus bridge chorus outro | all 12 = truth labels |
| MEGAFAUNA, Versatile (+ gain copies) | | sections and EDM roles identical (structural path untouched) |

## Notes / open
- The W4 review tests (tests/review/W4/verify-analysis) read the old run folders; they need fresh runs on structure 1.5.0 to
  reflect this fix (the dev results above show they would pass for the label tests).
- No CC test tracks downloaded (optional; skipped for the usage budget).
