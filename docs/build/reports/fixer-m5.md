# fixer-m5 report (M5 Words, review-fix round)

All 15 tests under tests/review/M5/** pass (including the model-backed alignment and LRCLIB tests, ~75 s), module unit
tests pass (identity, lyrics, voices, lipsync), ruff, contract check and validate pass.

| finding | fix |
|---|---|
| A  | align.py: group windows capped at the next group's first expected start (+0.15 s) and floored at the previous group's end; order repair re-aligns interleaving adjacent non-backing lines jointly; new notes crossings / crossings_fixed / crossings_left / lines_off_gt2s with a text-free warning; core._asr_repair judged on its own score |
| A2 | MmsAligner.emissions: context floor MIN_CTX_S = 6 s per side |
| B  | text.py: inline "Name:" prefixes are labels only in a labelled file (label recurs or a header names a speaker); unit test test_srt_vtt now uses a recurring label |
| C  | asr.NONLYRIC extended (thank you for watching, transcribed by, otter.ai, URLs, copyright, bare thank you / bye); asr_only lines need no_speech_prob < 0.6 |
| D  | per-line re-alignment clipped to neighbouring lines' placements |
| E  | lrclib.rank/choose: lyrics ahead of instrumental-only; core ignores the instrumental flag when the ASR has >= 8 words with p >= 0.5 |

Decisions: docs/contract/decisions/M5.md (M5-D30..D34).
Not done: minor findings m1-m5, m7-m10 (not cheap/safe in this round); m6 (CR-M5-1) left as a change request.
