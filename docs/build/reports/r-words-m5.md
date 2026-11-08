# r-words-m5: R-WORDS review of M5 Words (identity, lyrics, voices, lipsync)

Independent reviewer (PLAN §11), lens R-WORDS. Findings were formed from the code, the spec (PLAN §5/§7, SPIKE,
bench-words §5-7, CONTRACT D1-D46, M5 decisions) and my own runs, before reading the builder's report. No real
lyric text appears here.

## Verdict: fail (6 majors, 0 blockers)

The module works end to end and meets the headline numbers (TTS median onset error 20 ms; offsets detected;
newton -1.32 s, 4 voices matching the W0 blocks, 4 mouth channels; Jeremy 22859144, B, nothing after 218 s), but the
alignment can misplace whole lines by several seconds while grading A/B, and three text/source rules lose or
invent lyrics silently.

| id | sev | location | claim | test |
|---|---|---|---|---|
| A | major | `lyrics/align.py::align_groups`, `lyrics/core.py` | With an EXACT line-synced LRC, L008 of the synth is placed -2.2/+5.6/+5.6 s off and interleaves with L009; the song grades A. The group window runs 2 s past the next group's first line, nothing keeps lines monotonic, and ASR repair rejects the correct re-alignment. Jeremy shows the same: L033's last word 9.44 s long, 4 interleaving line pairs. | `tests/review/M5/r-words/test_rw5_alignment_synth.py` (2 tests) |
| A2 | major | `lyrics/align.py::MmsAligner.emissions` | 2 s right context is too short: the last ~1.3 s before each 30 s seam come out blank. Swept over 606 word placements, words ending < 1 s before a seam score 0.51 vs 0.70 with 6 s context, and 5-10 % fall below 0.10. | same file, `test_emissions_before_a_window_seam_are_not_degraded` |
| B | major | `lyrics/text.py::_label_split` | One-off "Word: ..." lyric lines become speaker labels: the sung word is deleted, the hint carries over to every later line, and two of them make voices force k = 2 from the hints. | `tests/review/M5/r-words/test_rw5_speaker_labels.py` |
| C | major | `lyrics/asr.py::filter_segments` | The filter keeps "Thank you for watching.", "Transcribed by https://otter.ai" and "Copyright WDR 2021" at p 0.9 with active vocals; the asr_only path adds such segments to lyrics.json before or after the lyrics. | `tests/review/M5/r-words/test_rw5_hallucination_filter.py` |
| D | major | `lyrics/align.py::align_groups` (line-window constraint) | A re-aligned line can snap onto its neighbour's audio (repeated text); accepted on score alone. Jeremy: L037/L039 share word starts with L036/L038 (204.12, 208.20, 210.26 s), grade B. | `tests/review/M5/r-words/test_rw5_line_realign_duplicates.py` |
| E | major | `lyrics/lrclib.py::rank`, `lyrics/core.py` | An instrumental-flagged LRCLIB duplicate with a smaller Δdur beats an entry with lyrics, and `instrumental_hint` then blocks the transcription fallback: on the synth, 53 confident ASR words give `instrumental: true` and 0 words. | `tests/review/M5/r-words/test_rw5_lrclib_instrumental.py` (pure + models) |

Minor findings m1-m10 are in `docs/review/M5-r-words.md`. They cover: the double sustain hold (3.08 s), years read as
cardinals, override id drift, the stable-ts index mapping, the draft transcript written into the models folder,
CR-M5-1 not applied as briefed, the lead envelope used for backing voices, the voices[0] fallback, the missing
coverage tie rule, and hint text in meta/voices.json.

## What I ran (all offline, M5 harness = runner child code, upstream = fixture copies)

| run | result |
|---|---|
| synth, user LRC with A2 word tags | grade A, 0 ms onset error (verbatim user words), voices 10/10 lines, 4/4 backing spans, mouth recall 0.98 / 0.96, false opening 3 % / 2 % |
| synth, plain txt (anchored) | median 20 ms, p90 76 ms, max 0.48 s, grade A |
| synth, line-only LRC, shifts 0 / +1.3 / +2.5 / +-4 s | offset found within 0.04 s, flagged above 3 s, but L008 off by 5.6 s in every case (finding A) |
| real-newton-vs-nye (builder's recorded HTTP) | LRCLIB 3921433, B, offset -1.32, 52 lines (announcer asr_only), 4 voices: announcer + A(L002-016) B(L017-031) A(L032-043) C(L044-052) = the W0 blocks; 4 mouth channels, overlap 3 % |
| real-jeremy | LRCLIB 22859144, B, offset -0.14 (not applied), last word end 218.1 s, 1 voice, ungated outro 75.5 s; 4 interleaving line pairs, 2 duplicated placements (D) |
| probes | seam sweep, group-tail cap experiment, ASR-repair debug, label / hallucination / ranking logic, token romanisation, hold length |

Privacy: no lyric word appeared in any result, warning, provenance, done.json or run log of these runs. The only
"hits" were title and artist words in identity. The Rhubarb dialog files are deleted after each run.

## Commands

```
Git Bash, MVH_RUN_OFFLINE=1:
powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-words-m5/scripts/run_m5.py <fixture> <work> [--lyrics f] [--seed-http out/_wip/builder-m5/h-<slug>] [--stages ...]
.venv/Scripts/python.exe out/_wip/r-words-m5/scripts/score_synth.py <work>
powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/M5     # 12 failed, 3 passed (guards) in 55 s
```
The review tests use only synthetic text. The models tests run in a heavy slot (about 55 s in total); skip them with
MVH_SKIP_MODELS=1.
