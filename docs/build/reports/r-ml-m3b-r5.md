# r-ml-m3b-r5: R-ML review of M3b (notes, vocals, instruments), round 5 (W3)

Verdict: **fail**. Two majors are open, each with a failing test. Notes and instruments are unchanged since round 4: their
source files predate it, and `notes/notes.mid` is byte-identical on both real reruns.

## Fix verification
| finding | status | evidence |
|---|---|---|
| R-ML-M3b-r4-1: lyric lines without acoustic support open the voice gate | **partly fixed** → R-ML-M3b-r5-1 | `test_vocals_lyric_gate_hallucination.py` passes (MVH_REAL=1), but only because it uses timing_source "interpolated" with conf 0. Real lyrics output never looks like that for supplied text: see r5-1. |
| R-ML-M3b-r4-2: lyric-only frames flip a rap lead to singing | **fixed** (the fix is real) but **regresses MEGAFAUNA** → R-ML-M3b-r5-2 | `test_vocals_lyric_frames_flip_rap.py` passes: style rap, basis null. |

## New majors
### R-ML-M3b-r5-1: forced-aligned lyric lines on a voiceless song still open the voice gate
- **Where:** `src/mvh/stages/vocals/__init__.py` `_lyric_mask` (L75-L90), used by `gate = active & loud & (voice | lyr)` (L171)
  and by `lyric_present` (L224-L230).
- **The conf filter is dead.** `conf <= 0.02` can never fire, because `lyrics/core._word_conf` floors every word at 0.1
  (unaligned, or CTC score 0), so the minimum line conf is ~0.06. On the three real songs with lyrics, every line is "ctc"
  with conf 0.09-1.0.
- **The timing_source filter misses the real case.** CTC and the stable-ts fallback always place supplied words, so text
  supplied for a song with no voice yields "ctc" or "stable_ts" lines, never "interpolated".
- **End-to-end evidence** (`out/_wip/r-ml-m3b-r5/karaoke`): a full `mvh analyze` of a 40 s synthetic song with no voice
  (clicks, bass, saw lead), with 8 user lines.
  - lyrics output: 7 ctc lines (conf 0.12-0.30, grade D) plus 1 stable_ts line (conf 0.72), song grade D, 34.5 s of coverage.
  - vocals: "lyric coverage 34.5 s in 8 line(s) counted as voice evidence". It escaped a fake singer only because the
    separator put the saw lead in "other".
- **Failing test:** `tests/review/M3b/r-ml/test_vocals_ctc_lines_on_voiceless_song.py` feeds those measured lines, with
  the synth lead in the vocals stem (as on MEGAFAUNA). Result: present True, 27.12 voiced s, p2 57.0 / p98 69.0, 58 vocal
  notes, 2 phrases.
- **Suggested fix:** do not rely on line conf (docs/SPIKE.md: per-line score AUC ~0.5). Require acoustic voice evidence
  from outside the aligner, for example:
  - ASR-matched words in the line (lyrics' asr_ok, or G1 pass at song level);
  - or `inst.voice` above a lower bar somewhere in the line;
  - or song grade better than D unless the ASR heard words.

### R-ML-M3b-r5-2: inherited "speech" style erases MEGAFAUNA's sung range (regression from the r4-2 fix)
- **Where:** `vocals/__init__.py` L190-L198 (`inherit = max(tagged, ...)` applied to every untagged lyric frame).
- **Real rerun** (`out/_wip/r-ml-m3b-r5/megafauna`: r4's folder with spectral..lyrics and then vocals re-run): present true,
  6.96 s, but lowest, highest, p2, p98 and register are all null. r4 reported E3-E4, p2 52.1 / p98 67.0, alto, conf 0.44.
- **Why:** spoken_pitch went from 0.07 s to 6.96 s. The tagger's only label (7 s "speech", r4-m4: CED and SwiftF0 run on the
  near-silent lead_vocals) covered almost none of the voiced frames, yet every sung frame inherited it.
- **Impact:** vocal range is an explicit user requirement, and S04 (lyrics, voices, singing and meaning all have a singer)
  is only half fixed.
- **Failing test:** `tests/review/M3b/r-ml/test_vocals_inherited_speech_drops_range.py` (synthetic mirror). Result: range
  null, spoken 23.18 s, style speech.
- **Suggested fix:**
  - Inherit only "rap", as the r4 suggestion said. Or inherit only from tagger labels that overlap or neighbour the line.
  - Fix r4-m4: run the style tagger on `pick_lead_stem`.

## Real-song regression runs (W3 verify)
- **megafauna:** see r5-2. Vocal notes and phrases match r4; `notes.mid` is identical.
- **newton-vs-nye:** identical to r4 and to the integrator (72.12 s, rap, spoken_pitch only, `notes.mid` identical).
- **Integration test:** `tests/integration/M3b/test_real_vocal_presence.py` still reads the stale integrator vocals (05:10).
  The r5 rerun gives present true, so the integrator needs to re-run lyrics and vocals.
- **Tests:** unit vocals 18 pass; ruff is clean on tests/review/M3b/r-ml.

The minor findings are in docs/review/M3b-r-ml.md, Round 5: r5-m1, r5-m2, plus r4-m2 and r4-m4, which are still open.
