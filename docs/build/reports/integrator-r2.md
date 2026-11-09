# integrator-r2 (W3 steps 4-6) report

This round applied the W3 fixers' change requests and closed most of the critic's and verifiers' open findings (D67-D77).
It added the R19 override round-trip acceptance test on real stages, re-ran `--profile max` from scratch on the four real
songs and the synthetic song (plus a draft run), and ran the full gate. It also wrote docs/RUNS.md and updated
docs/SEAMS.md and docs/CONTRACT.md. No lyric text appears in this report.

## 1. Gate blockers and cross-module change requests
| Item | Result |
|---|---|
| tests/unit/contract `test_deps_match_plan` (vocals now depends on lyrics, CR-M3b-1) | PLAN_DEPS updated (D67) |
| CONTRACT.md out of date (`gen --check`) | Regenerated after D67-D77; `--check` OK; the skill copy is synced |
| ruff (structure, vocals, notes, sep/determinism) | Already clean when I started; still clean after my edits |
| Determinism (GPU drum sub-stems, separation stems) | D47 (DrumSep on the CPU) + fixer-m3a-r4 (math SDPA, rocBLAS). The sep worker now exports `ROCBLAS_USE_HIPBLASLT=0` for rocm (D74). Gate determinism result in section 5 |
| Re-run the integrator folders (every fixer's CR) | Done from scratch (section 4); phase-1 folders kept in out/_wip/integrator/_phase1/ |
| Merge module decisions (M1, M2 "W3 fix rounds", M5-D47..D55, M6b W3 rounds) | Merged by reference in D76; the stage-specific ones I changed are D67-D73 |
| M5: Jeremy outro test is wrong (fixer and verifier agree) | tests/integration/M5/test_real_lyrics_grade.py now asserts the M5-D52 flag (vocals after the last line + review warning) |
| M6a: voices must treat mapped voices as a floor | D69 (`n_voices_min`) |
| CR-M1-4/5/6 (kick fusion / precedence), S06 test change | Superseded by user decision UD2 (W4 phase 0). Not started, per instructions |
| M6b intent-parser findings (R5-1..R5-4) | Superseded by user decision UD1 (W4 phase 0). Not started |
| CR-M3b-2..4 (notes deps instruments; overrides.json keys for vocals/notes/instruments; catalogue fold-ins) | Still open: stage params remain the correction hooks (D59) |
| PyYAML as a direct dependency (M6b CR-4), madmom numpy patch (M2-3) | pyproject/lock changes for the orchestrator (change_requests) |
| fixer-m1-r4: empty folder `C:\OPENSR~1` | Outside the repo; deleting it needs the user (not touched) |

## 2. Fixes (each with a review or critic test that now passes)
- **M2 structure 1.2.0 (D68).**
  - W3C-6: boundary edits are applied locally to the automatic result instead of re-running the DP.
  - F8-r5: a phrase remainder leads its section only on that section's own evidence (snapped start, or boundary score).
  - F-R5-APPLIED-BOUNDARY (with M6a): one `overrides_applied` entry per key, holding the list; the viewer also collects
    repeated keys.
  - m6: `edm_role` is set on every section in a role span.
  - The unit test tests/unit/structure/test_phrase_grid.py was rewritten to the local rule. Its old global-vote cases
    were the behaviour that finding F8-r5 shows to be wrong.
- **M2 choreo 1.1.0 (D71).**
  - W3C-2: Longuet-Higgins/Lee syncopation; the synthetic truth formula was re-baselined and the fixtures rebuilt.
  - W3C-1: groove clustering by per-row onset F1 (exact step 1, +-1 step 0.5) against the cluster's majority pattern.
    The synthetic pairwise agreement with truth is 0.988.
- **M3a drums 1.1.0 (D73), R5-1.** The coincidence-decay rule now fires at snare/tom strokes only.
- **M3b vocals 1.1.0 + instruments 1.1.0 (D67).**
  - R5-1: lyric lines count as voice evidence only with grade A-C or G1 >= 0.3.
  - R5-2: untagged lyric frames inherit only `rap`; otherwise they count as sung.
  - r4-m4: the style tagger reads `pick_lead_stem`.
- **M4 harmony 1.1.0 (D72), R5-M1 and R5-M2.**
  - A chord-less key needs a peaked long-term chroma (peak/mean >= 2.2) and S-KEY p >= 0.35 for the full carve-out
    (cap 0.8).
  - A neighbour or abstaining S-KEY keeps the key at <= 0.5 instead of `no_tonal_evidence`.
- **M5 lyrics 1.1.0 / voices 1.1.0 (D69, D70).**
  - W3C-5: each lead line's tail is capped at the next lead line's first word.
  - R5-1: lone `Name:` markers must pass the name check.
  - R5-2: speaker hints come from all lines, so the voices stage no longer crashes.
  - F-R4-VOICE-FLOOR: the viewer's mapped voices are a floor on the voice count.
  - m2: a single voice is not flagged for review because of grade D.
- **lib** `singer_at` / `singerAt`: one entry per (character, voice). Node lib tests 30/30, Python lib tests pass.
- **brief** 1.0.1: key flags are no longer double-prefixed (m1). **SKILL.md**: frames file name for `--frame0 1` (m7).
- **Review test M6a r5.** Its precondition now accepts both provenance stamp shapes. I added a test that the viewer
  still loads with one entry per edit (repeated keys), so the robustness it checked is kept.

Not fixed (W4, reasons in docs/SEAMS.md): S06 / M1 R5-M1..M4 (UD2), M6b R5-1..R5-4 (UD1), W3C-3 half-time feel
(needs a DAG or contract decision), W3C-4 Jeremy hats (M3a algorithm), and grooves on MEGAFAUNA and Versatile (noisy
DrumSep rows; UD2).

## 3. R19 override round trip (tests/integration/test_override_roundtrip.py)
The test is marked real and slow. It copies the integrator's max folders, edits them through the edit server
(`make_server`: GET then POST /api/overrides with etag and token, POST /api/intent), then runs `python -m mvh.cli analyze
<folder>`. **2 passed in 481 s.**
- **Synthetic, step 1** (boundary move, pinned cue, V1 -> C1 named, meaning + feel of one section):
  - Re-ran exactly the stages downstream of structure, cues, voices and meaning.
  - The moved boundary is the only boundary change.
  - The pinned cue appears in events/cues.json.
  - meaning.json C1 has the user's name and V1; singing rows of V1 carry C1.
  - The meaning edit is re-anchored to the overlapping section(s) with `field_sources.meaning = user`.
- **Synthetic, step 2** (`rhythm.downbeat_phase = 1`):
  - Re-ran rhythm, dynamics, harmony, notes, structure, lyrics, mood, vocals, choreo, cues, voices, lipsync, meaning,
    brief and viewer. None of ingest/identity/loudness/spectral/separate_*/allin1/stem_activity/drums/instruments re-ran.
  - Every downbeat moved by one beat, and the earlier edits survived.
- **Newton, step 1:** re-ran structure, lyrics, mood, vocals, choreo, cues, voices, lipsync, meaning, brief and viewer
  (203 s of stage time), and every edit appeared.

## 4. Real runs (fresh, `--profile max`, offline, LRCLIB replayed, 5 songs concurrently)
| Song | Wall s | analyze / validate | Lyrics | Notes |
|---|---|---|---|---|
| jeremy | 2949 | 0 / 0 | B (G1 0.76; was D) | outro flagged (vocals_after_last_line_s 75) |
| megafauna | 2815 | 0 / 0 | D | vocals present, range E3-E4 conf 0.44 (S04 fixed); vocals/voices degraded (vocals_stem) |
| versatile | 2826 | 0 / 0 | none (instrumental) | mouth closed (S07 fixed) |
| newton-vs-nye | 2715 | 0 / 0 | C (G2 0.748 vs 0.75; was B) | 4 voices; hand-off overlaps gone |
| synth | 2737 | 0 / 0 | B (transcribed) | truth checks in unit tests |
| jeremy-draft | 1070 (almost alone) | 0 / 0 | transcribed (not seeded) | draft profile |

A no-op re-run of all five folders gave 25/25 cache hits each (4-5 s) and validate 0. Per-stage seconds, waits and
disk use are in docs/RUNS.md §3.

Integration tests (tests/integration, 19 incl. the round trip): 18 pass, S06 fails. Critic tests: 28 pass, 5 fail
(W3C-3, W3C-4, grooves on MEGAFAUNA and Versatile, and the 2.1 s backing-double mouth overlap).

## 5. Gate (`scripts\gate.ps1 all`)
Run on a quiet machine after all runs (2067 s, rc 1, log out/_wip/integrator/gate-all.log):

| Step | Result |
|---|---|
| fixture | PASS |
| unit | **PASS**: 992 passed, 97 skipped, 1 xfailed, 0 failed |
| review | FAIL: 39 failed / 262 passed / 32 skipped. Every failure is a finding left for W4: M1 r-dsp `test_rdsp_r5_kicks.py` (11; UD2), M6b r-words `test_rw5_bold_colon_labels.py` (9), `test_rw5_voice_answers.py` (8), `test_rw5_do_not_headings.py` (6) (23; UD1), W3 critic (5: feel W3C-3, grooves MEGAFAUNA + Versatile, mouth overlap from a backing double, Jeremy hats W3C-4). Every other review test passes, including the M2, M3a, M3b, M4, M5, M6a and M6b r-contract rounds and all w1b tests. |
| ruff | PASS |
| contract (gen --check) | PASS |
| validate (fixture) | PASS |
| e2e (synthetic song, real stages) | PASS, 247 s |
| lib-node | PASS |
| determinism | **PASS**: analyze --force twice, every file except run.json/.cache identical |

## 6. Gotchas
- The stage cache key does not include code. Bump the stage version after a behaviour change (done for structure,
  choreo, drums, vocals, instruments, harmony, lyrics, voices, brief), or use `--force`.
- A Bash heredoc that runs python turns `"\n"` inside the python source into a real newline. Use the Edit/Write tools for
  backslashes.
- Never run the five max songs and a unit run at the same time. The unit tests' `heavy()` waits hit pytest-timeout
  (tests/unit/harmony timed out once like that; it passes alone).
- The first gate launch of this round wrote to out/_wip/integrator/gate-all.* (the phase-1 path), replacing phase 1's
  gate log. Phase 1's results are kept in docs/build/reports/integrator.md §4.
