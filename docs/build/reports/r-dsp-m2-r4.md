# r-dsp-m2-r4: R-DSP re-review of M2 Rhythm, round 4 (W3 verify)

**Verdict: pass-with-fixes.** All 4 routed items are fixed in the code. One new major: a regression from the S05 fix.

## Method
- **Code under review.** Current code (structure changed at 06:21 by fixer-m2-r3). allin1, rhythm, choreo and cues have
  not changed since the integrator's runs (05:10).
- **Real upstream.** `out/_wip/r-dsp-m2-r4/probes/runreal.py` re-runs structure, choreo and cues on the integrator's real
  runner caches (`out/_wip/integrator/<slug>/.cache`) for synth, jeremy, megafauna, versatile and newton-vs-nye.
  Output: `out/_wip/r-dsp-m2-r4/real/`.
- **Jitter sweep.** `p_jit2.py` uses the r3 harness (recorded real allin1, harmony and dynamics). It sweeps constant bar
  shifts from -40 to +40 ms and random per-bar jitter of ±20 ms (8 seeds) and ±30 ms (4 seeds).
- **Snap ablation.** Each song was also re-run with `structure.impact_snap_strength=0` to isolate the S05 rule.
- **Tests.** Review `tests/review/M2/r-dsp`: 22 pass by default, 3 pass with `-m real`. M2 unit tests: 49 pass. Ruff is clean.

## Routed items
| id | status | evidence |
|---|---|---|
| F4-r3 (major) | **fixed** | F 1.0 on the synthetic song for: the real rhythm, the truth rhythm, every constant shift from -40 to +40 ms, and 12 random per-bar jitter seeds. The full run through real upstream gives F 1.0, labels == truth. Centred bar_pattern slots, jitter-averaged novelty and a short-section margin. All three are general mechanisms, not test hacks. |
| F6-r3 (major) | **fixed** | MEGAFAUNA drop 141.8-212.7 s on real integrator upstream. Repeat groups I/J are all drop now. |
| S05 (major) | **fixed in the stage** | Jeremy verse#1 now starts at 19.47 s. The snap fires on Jeremy only (ablation: no change on the other 4 songs). `tests/integration/M2/test_real_section_at_impact.py` still fails because the integrator output is stale. It passes on a re-run. **But see F7-r4.** |
| S09 (minor) | **fixed (synthetic)** | The intro is one 'intro' section and the bridge is labelled 'bridge'. The integration test fails only on stale output. Jeremy's chorus overcount remains (11/19; minor r4-m3). |

## New finding
**F7-r4 (major): the S05 impact snap shifts Jeremy's verse#1 eight-counts by one bar, leaving a 4-beat partial before the first chorus.**

Location: `src/mvh/stages/structure/__init__.py`, the impact snap plus the phrases built from each section start. Downstream:
`choreo` eight-counts.

- **What the snap does.** It extends verse#1 to 9 bars (19.47-40.13 s). The phrases start at the section start, so the
  1-bar remainder goes at the END: P 19.47 s (8 bars) + P 37.86 s (1 bar).
- **Effect on the eight-counts.**

  | | eight-count starts | vocal entry 21.9 s |
  |---|---|---|
  | snap on | 19.47 / 24.10 / 28.68 / 33.26 s, then partial E009 (4 beats) at 37.86 s | count 5 |
  | snap off (`impact_snap_strength` 0) | 21.80 / 26.37 / 30.96 / 35.56 s | count 1 |

  Every later section sits on the 8-bar grid from 21.80 s.
- **Cue side effect.** cues gains a tier-2 'phrase' cue at 37.9 s.
- **Why the fixer missed it.** fixer-m2-r3 reports "counts unchanged". The number of counts is unchanged, but their grid moved.
- **The rule in general.** By construction, the rule always makes the moved section one bar longer at its start, so it
  causes this whenever it fires.
- **Test.** `tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py` (`-m real`; integrator caches):
  - 2 fail: grid moved, and the dangling partial.
  - 1 passes: the snap precondition.
- **Suggested fix.** When the snap moves a start back by one bar, keep the phrase grid of the original boundary. Make the
  impact bar a 1-bar leading phrase (pickup), so the eight-counts are partial at the section START. More generally,
  place a section's phrase remainder where the following sections' phrase grid puts it.

## Minors (docs/review/M2-r-dsp.md, Round 4)
- **r4-m1:** the integrator outputs are stale, so the S05/S09 integration tests fail.
- **r4-m2:** the structure StageSpec version is still 1.0.0. Only new params invalidated the cache.
- **r4-m3:** Jeremy has 11 of 19 sections labelled chorus.
- **r4-m4:** the DSP-only fallback still locks onto the off-beat (r3-m4).
- **Round-3 minors:** m1 and m3 are fixed, m2 is unchanged but harmless, m5 is covered.

## Files
- **Test:** `tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py`
- **Probes:** `out/_wip/r-dsp-m2-r4/probes/{runreal.py, cmp.py, p_jit2.py, p_loop.py, all.sh}`
- **Logs:** `out/_wip/r-dsp-m2-r4/p_jit2_const.log`, `p_jit2_rand.log`
- **Re-run outputs:** `out/_wip/r-dsp-m2-r4/real/<slug>[_nosnap]/`
