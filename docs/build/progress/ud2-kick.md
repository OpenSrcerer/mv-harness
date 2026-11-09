# ud2-kick progress (W4 phase 0, user decision UD2)

## Status
- [x] read BUILD-STATUS UD2, SEAMS, fixer-m1-r4 (CR-M1-4/6), drums stage, lib, finalize
- [x] data exploration of the DrumSep kick stem (scratch: scratchpad/kickx.py)
- [x] drums: kick quality gate (CR-M1-4) + recovery of mislabelled low hits (drums/kick.py; drums 1.2.0)
- [x] drums: per-song reliability score + kick_source choice -> meta/drums.json (catalog files/drums, D79)
- [x] manifest summary.kick_source + kick_agreement + flag qa:kick_sources_disagree (finalize.kick_info)
- [x] lib kick helpers (kickSource, kicks(), events('kick'), kickItems) + golden 6b + kick.test.mjs/test_lib_kick.py
- [x] brief kick row + per-section kicks column + zoom line; viewer kick row (data.js meta drums, lanes.js, panels.js); frames 'kick' column
- [x] SKILL.md wording ('Cut on the kick' row)
- [x] hits.kick precision retune; M1 review tests (r4/r5), unit spectral, integration S06 rewritten; docs/contract/decisions/UD2.md
- [x] CONTRACT.md D79 + D80 (after ud1's D78); frames 1.1.0
- [x] VERSION BUMPED rc.2 -> rc.3 by ud2-kick (ud1: do NOT bump again): mvh/__init__, catalog, mvh.js, mvh_load.py, mvh.d.ts,
  mvh.glsl, viewer edit.js, viewer/data.py, CONTRACT.md header + example. Then: golden, addendum, gen, fixtures, skill sync.
- [x] runs: synth + 4 real songs done (analyze 0 / validate 0, rc.2 + UD2 code)
- [x] golden/addendum/gen/fixtures/skill sync done; unit suite 1534 pass (test_skill alias fixed); node lib 35 pass
- [x] gate M1 PASS all steps; gate M3a: everything PASS except review (the r-ml --only list lacked spectral; fixed, 3/3 rerun pass)
- DONE. Report written.
- [x] report docs/build/reports/ud2-kick.md (fill gate results)

## Design (decided)
- drums 1.2.0 depends on spectral (cheap; acyclic). It gates the kick stem, scores both sources, picks the
  agent-facing source and writes the optional `meta/drums.json` (kick_source, reason, scores, agreement).
- finalize copies kick_source + agreement into manifest summary, flag `qa:kick_sources_disagree` when low.

## Coordination (from ud1-meaning progress)
- ud1 takes D78; ud2 takes D79+. ud2 does the ONE contract bump 1.0.0-rc.2 -> 1.0.0-rc.3 (mvh/__init__, catalog,
  mvh.js/mvh_load.py/mvh.d.ts/mvh.glsl, viewer edit.js + viewer/data.py, golden vectors, gen, fixtures rebuild
  `python -m tests.synth.build`, skill CONTRACT copy). ud1 edits brief/build.py `_meaning_block` and SKILL.md meaning
  section only: re-read before editing those files.

## Exploration results (scratchpad kickx.py / gate.py / recov.py / shape.py / kfree.py / realk.py / unm.py)
- block-index bug in scratch: use k = t*sr/bs, not t*1000 (bs = sr//1000 = 44 at 44.1k).
- MEGAFAUNA kick stem: kick rows' 30-120 Hz level weak rows -35 dB vs strong -17.5; inst sections (18-36 s, 124-135 s):
  the real kick sits in the SNARE stem (30-120 over 150-400 Hz +12..+20 dB, rise 24-48 dB), kick stem only bleed.
- Gate (rise>=3 dB, on-hat & L<ref-10, L<ref-20; ref = p75/p90 of kick-row 30-120 Hz level): Jeremy stem->mix 0.79->0.91,
  Versatile 0.88->0.99, Newton/synth unchanged; no strong (vel>=.5) row dropped on clean songs.
- Recovery: only from the snare stem (lo-body >= 10 dB); Jeremy/Versatile toms are bass-heavy floor toms (lo-body 6-16)
  -> toms need a fast decay (>= 10 dB at 80-110 ms) + mix confirmation.
- hits.kick precision: click route = all false kicks on kick-free textures (pluck 39, piano 21, snare+bass 7); on real
  songs <= 3 events. sweep click-alternative at attack 10-10.6 = pluck's 12. Weak+ambiguous filter (strength < 0.5 and
  kick_conf < 0.8): Jeremy P 0.90 -> 0.97 at the same recall, others unchanged. Plan: click route off, click_attack 12,
  weak filter on. Costs: tr808-120 F1 0.968 -> 0.945, acoustic over held bass recall 1.0 -> 0.63 (tests to rewrite).

## Milestones
- spectral 1.3.0 precision retune DONE in dsp.py/__init__.py (click route off, click_attack 12, weak filter with roll/duck/
  on-tail exemption). Jeremy hits.kick vs stem: P 0.89 -> 0.95 at R 0.95; kick-free textures 0 / 0 / 0 kicks.
- src/mvh/stages/drums/kick.py written (gate_kicks, choose_source). Scratch result (dgate.py, integrator stems, old hits.kick):
  synth/newton/versatile/jeremy drums (agree >= 0.90 both ways); MEGAFAUNA drums 647 -> 342 rows (gate drops 324, recovers
  10 snare-stem kicks + 9 layered), vel med 0.46, fast gaps 0.16, agreement 0.44/0.25 -> QA flag. floor 16/18 hurt Versatile.

- RUNS launched (background, resumable): out/_wip/ud2-kick/run_song.ps1 -Slug <slug> (copies integrator/<slug>, analyze, validate,
  writes <slug>.done.json). meta/drums.json: synth drums .977/.988, newton drums 1.00/.995, versatile drums .956/.991,
  jeremy drums .958/.916, megafauna drums .463/.249 (QA flag). Version NOT bumped yet (bump at the end; runs are rc.2 + UD2).
- skill CONTRACT copy: run `python skill/mv-harness/scripts/sync_contract.py` after CONTRACT.md edits.

## Commands that worked
- scratch python: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python <script>`

## Gotchas
