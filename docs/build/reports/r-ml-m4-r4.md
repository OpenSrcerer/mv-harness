# r-ml-m4-r4: R-ML review of M4 (harmony, mood), round 4 (W3 verify)

Verdict: **fail** (1 new major, a regression introduced by the R3-M1 fix). R3-M1 itself is fixed.

## R3-M1: FIXED
- `keys.global_confidence(..., no_chord_share)`: a lv-chordia no-chord share of 0.9 or more in the span caps confidence at
  0.3 and adds `key:no_tonal_evidence` + `key:low_confidence`. Chords and phrase count as sources only when chords cover at least 25 %.
  `core.analyse_key` passes the share for the global key and for every region. The logic is general, not specific to the test.
- `tests/review/M4/r-ml/test_key_gating_band_noise.py` passes (stub and real). With real S-KEY and real lv-chordia, band
  noise (3 bands), brown noise and a riser are all capped at 0.3 or below and flagged (`out/_wip/r-ml-m4-r4/probe.log`). m13 is fixed too.
- Fast M4 unit + review suite: 61 passed. Real review tests: 5 passed.

## New major R4-M1 (regression): a tonal a-cappella line is labelled "no tonal evidence"
- `tests/review/M4/r-ml/test_key_gating_a_cappella.py` fails in both variants (stub models: conf 0.3; real S-KEY + real lv-chordia: conf 0.3).
- Signal: `tests/contract/synth/stems/lead_vocals.flac` (A minor, synthetic). lv-chordia gives 100 % N; S-KEY (p_max 0.566,
  voted), KS, Temperley and Albrecht all say A minor. Disabling the gate (NO_TONAL_SHARE=1.01) gives 0.97
  (`out/_wip/r-ml-m4-r4/prefix_check.py`).
- Suggested fix: decide tonality from the chroma, not from "no chord". The median normalised chroma entropy is 0.91-0.97 on
  every noise probe and 0.71 on the vocal (`out/_wip/r-ml-m4-r4/peaky.py`). Apply the cap when N is 0.9 or more AND the
  chroma is flat (for example entropy > 0.85), or when S-KEY does not vote and the profiles split.
- Impact on real material is limited: on real separated lead-vocal stems S-KEY mostly does not vote (p_max 0.17-0.34) and the profiles
  split. Gating jeremy's A-minor region drops it from 0.83 to 0.30. Clean a-cappella, choral and solo-voice pieces get the false label.

## Real songs (W3 verify)
- With the integrator's beats and bars: newton-vs-nye A minor 0.888, megafauna D minor 0.5 (3 regions), versatile A minor 0.5.
  These are the same values as the integrator's pre-fix outputs, so there is no regression on mixes (no-chord share 4-22 %).
- `mvh analyze out/_wip/r-ml-m4-r4/jeremy --only harmony,mood --force harmony,mood`: the harmony outputs are byte-identical to
  the integrator's run, so harmony is deterministic across processes. The W2 CR about key/chord nondeterminism traces to the
  upstream rhythm. Mood did not run there (structure stale in the copied folder without stems), so the mood heads were
  re-run directly on jeremy and newton-vs-nye (`mood_check.py`): section values reproduce to within 5e-5 and the tags are identical.
- There is no `tests/integration/M4/`.

## Minors (docs/review/M4-r-ml.md, Round 4)
m14 harmony stage_version not bumped after the behaviour change (stale caches); m15 chord evidence keeps full weight at
low chord coverage; m16 a region shorter than one window gets 0.97 with no window support (megafauna 18.1 s, below
key_min_region_s); m17 an overridden key keeps the contradicting low-confidence and no-tonal flags; m18 decisions/M4.md
does not describe the gate; m9 is partly open (no unit tests of recover_probs, skey_weight or voted; no integration tests).

## Gate
`scripts/gate.ps1 M4` (log `out/_wip/r-ml-m4-r4/gate.log`) fails at the unit step on two shared contract tests that are not M4:
`test_deps_match_plan` (vocals now depends on lyrics) and `test_generated_artifacts_up_to_date` (CONTRACT.md has not been regenerated).
The harmony and mood unit tests pass.

## Files
- tests/review/M4/r-ml/test_key_gating_a_cappella.py (new, fails as stated)
- docs/review/M4-r-ml.md (Round 4 section)
- probes: out/_wip/r-ml-m4-r4/{probe.py,probe.log,probe_real.py,probe_real.log,prefix_check.py,prefix_real.py,peaky.py,mood_check.py,override_check.py}
