# r-dsp-m2-r2: independent review of M2 Rhythm, round 2 (lens R-DSP)

**Verdict: fail.** One major finding is still open: F4, the structure stage on realistic upstream. It has a new
failing test. F1, F2, F3 and F5 are fixed. There are seven new minor findings, listed in `docs/review/M2-r-dsp.md`
under "Round 2". No real-song lyric text was read or printed.

## What was run
- **Review tests:** `tests/review/M2/r-dsp`, including `-m real`. Before my new test, all 14 passed. M2 unit tests:
  39 passed, 7 skipped.
- **Real-song replays** with the W0 tracker outputs, for megafauna, versatile, jeremy and newton-vs-nye, through
  rhythm, structure, choreo and cues. I compared them with the round-1 replays
  (`out/_wip/r-dsp-m2-r2/replay`, probes `cmp_sections.py` and `cmp_meter.py`).
- **Full `mvh analyze` of the synthetic song:** the round-1 folder re-run `--from rhythm`, in
  `out/_wip/r-dsp-m2-r2/synth`. `mvh validate` reports 0 errors.
  - rhythm: beat F1 1.00, downbeat F 1.00, tempo error 0.033 BPM, the pickup and the 3/4 bar 16 are still correct.
  - structure: boundary F 0.615.
- **Edge cases** (`p_edge2.py`): silence, noise, a sine, and click tracks from 0.3 to 7 s at 70, 120 and 180 BPM, on
  the DSP and the model paths.
- **Structure attribution** (`p_struct_mix.py`, `p_struct_nomel.py`): which real upstream breaks the stage, and the
  effect of the melodic fingerprint.
- **Gate M2** (`out/_wip/r-dsp-m2-r2/gate.log`):
  - PASS: fixture, contract, validate, e2e, lib-node.
  - review fails only on my new test.
  - unit fails only on `tests/unit/contract` (the stub check, CR M2-5).
  - ruff fails outside M2; the M2 paths are clean.

## Round-1 findings
- **F1 (fixed).** The pin leads the merged cue (`kind: pinned`, tier 1, strength 1.0) and appears in moments.json. The
  fix is generic, not specific to the test.
- **F2 (fixed for inputs of 1 s and longer).**
  - `smooth_same` gives the same output as `np.convolve(..., 'same')` for all kernel sizes tested.
  - The metrical window is clipped to the song.
  - A crash remains below 0.68 s, in `tempogram_peaks`'s autocorrelation length (minor r2-m1).
- **F3 (fixed).** The short-first-section path is gone, and no real song has a non-silence section shorter than
  2 bars. Side effect: the odd intro bar now goes to the end of the first section's phrase grid (minor r2-m2).
- **F4 (NOT fixed): major.** See below.
- **F5 (fixed).**
  - versatile: no spurious 3-beat bar, and allin1 downbeat F against the fused bars rises from 0.844 to 0.907.
  - The other songs and the synthetic song are unchanged.
  - The correction uses the first-pass decode as its reference (minor r2-m4).

## Major
**F4-r2. structure still misses the synthetic song's sections with realistic upstream. The round-1 test passes
because of a second circular input: the fixture's dynamics segments are the truth sections.**
- **Test:** `tests/review/M2/r-dsp/test_structure_real_upstream.py`, with data
  `tests/review/M2/r-dsp/data/synth_real_harmony_dynamics.npz`. 4 tests fail and 1 passes (the one showing the
  circularity).
- **Evidence:**
  - Real allin1 and real harmony chroma: F 0.909. Chorus#1 at 17.0 s is merged into the verse, and the choruses are in
    groups B and D.
  - Adding the real dynamics as well: sections at 1.0, 5.0, 9.0, 25.0, 34.5, 42.5 and 52.5 s, F 0.615.
  - The full `mvh analyze` gives the same 0.615 (round 1: 0.667).

## Paths
- New test: tests/review/M2/r-dsp/test_structure_real_upstream.py; data: tests/review/M2/r-dsp/data/synth_real_harmony_dynamics.npz
- Minors: docs/review/M2-r-dsp.md (section "Round 2")
- Probes and outputs: out/_wip/r-dsp-m2-r2/
