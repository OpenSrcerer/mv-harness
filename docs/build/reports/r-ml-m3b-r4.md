# r-ml-m3b-r4: R-ML review of M3b, round 4 (W3)

Verdict: **pass-with-fixes**. S04 is fixed in code, but the fix added 2 new majors in the lyric gate.

## S04 verification
- **The fix is real.** `vocals` picks the vocals stem when lead_vocals is more than 20 dB down, and lyric lines open the voice gate.
- **MEGAFAUNA re-run** (`out/_wip/r-ml-m3b-r4/megafauna`): present true, 6.96 s, E3-E4, 10 phrases, 33 notes.
  - 6.83 s of the voiced frames lie inside aligned words, and 0.07 s lies outside lines.
- **The integration test still fails.** `tests/integration/M3b/test_real_vocal_presence.py` reads
  `out/_wip/integrator/megafauna`. vocals has not been re-run there since the fix, so the integrator must re-run it.
- **No regression on the other real songs:**
  - jeremy: 196.3 s, E3-C#5 tenor, 589 notes.
  - newton-vs-nye: identical.
  - versatile: present false.
  - notes and instruments: unchanged (`notes.mid` byte-identical).

## New majors (failing tests)
1. **R-ML-M3b-r4-1:** `_lyric_mask` trusts every line. It ignores `timing_source` (interpolated / lrclib_line), `conf` and `grade`.
   - Evidence: a synth sawtooth on the vocals stem inside conf-0 interpolated lines becomes a singer (present, 24.96 s, p2 57 /
     p98 69, 52 notes, 1 phrase).
   - Test: `tests/review/M3b/r-ml/test_vocals_lyric_gate_hallucination.py`.
   - Fix: count only lines with acoustic timing (ctc / whisper / stable_ts / lrclib_word / user) and conf >= ~0.3. MEGAFAUNA
     still has 5.3 pitched s in such lines (>= 4), so S04 stays fixed.
2. **R-ML-M3b-r4-2:** untagged frames inside lyric lines are counted as singing and added to the style tally.
   - Evidence: on a rap lead that the tagger hears for only 10 s of 26, the dominant style flips to singing, and the range is
     computed over the rap (style=singing, basis "voiced frames").
   - Test: `tests/review/M3b/r-ml/test_vocals_lyric_frames_flip_rap.py`.
   - Not triggered on newton-vs-nye, where the tagger's voice is 1.0 in every line.
   - Fix: do not add lyric frames to the style tally, and treat them as sung only when the tagger's dominant style is not rap.

## Minors
r4-m1..m5 and one runner observation are in docs/review/M3b-r-ml.md (Round 4): catalogue CONSUMES, undeclared params, the DAG
test failure (PLAN_DEPS), the style sustain feature still on lead_vocals, and Versatile's vocal events while present is false.

## Commands
- `out/_wip/r-ml-m3b-r4/run_song.ps1` and `run_all.ps1`: `--only spectral,...,lyrics,vocals` on copies of the integrator folders.
- `out/_wip/r-ml-m3b-r4/probe.py`: numbers-only probe (no lyric text).
- Tests: `uv run --frozen --no-sync python -m pytest -q tests/review/M3b/r-ml` (the 2 new tests fail; the 3 old ones pass).
