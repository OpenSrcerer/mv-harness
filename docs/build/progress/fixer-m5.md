# fixer-m5 progress
- DONE: B (text.py label policy via contextvar _file_labelled; unit test srt updated), C (asr NONLYRIC + no_speech_prob in asr_only), E (lrclib rank/choose + core instrumental flag vs ASR), D+A (align.py group caps, neighbour-clipped line realign, crossing repair), A2 (MIN_CTX_S=6), repair acceptance in core._asr_repair.
- NEXT: run tests/review/M5 (models), unit tests, gate M5, decisions doc M5-D, report.
- cmd: MVH_SKIP_MODELS=1 .venv/Scripts/python.exe -m pytest -q tests/review/M5
