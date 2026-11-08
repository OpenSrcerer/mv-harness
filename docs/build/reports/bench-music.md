# bench-music report

Status: done. All 14 tools ran on all 4 full songs (piano transcription gated off everywhere: no piano present). Full findings: `docs/spike/bench-music.md`.

## Deliverables
- `docs/spike/bench-music.md`: timings per tool and song with concurrent load, cross-tool agreement (beat F, tempo candidates, downbeat phase, key), per-song sanity (Jeremy vocal range G3-G#4, drop times), go/no-go per tool, re-baselined thresholds, change requests.
- `tests/.cache/real/<slug>/{decode,demucs,beat_this,allin1,librosa,spectral_proto,chords,key,notes,pitch,instruments,mood,madmom_dbn,piano}/` raw outputs; `tests/.cache/real/index.music.json` registry.
- `docs/research/spike-scripts/bench-music/`: `bench_music.py`, `run_all.sh`, `analyze.py`, `extra.py`, `analysis.json`, `extra.json`.
- `docs/build/progress/bench-music.md` checkpoint log.

## Headline results
- MEGAFAUNA tempo is a three-way split (allin1/librosa ~105, tempogram 143.6, beat_this/madmom ~193-200): keep candidates, no hard pick. Other songs: trackers agree (beat F .85-.97, tempo within 2 percent).
- Downbeat phase differs by one beat between madmom and allin1/beat_this on versatile and newton-vs-nye: use a vote.
- Key: S-KEY = Krumhansl on 3 of 4 (A minor); MEGAFAUNA ambiguous; S-KEY probability is flat (<=.094), not a confidence.
- Rap vocals fail SwiftF0 gating (8.6 s voiced) while RMVPE finds 41 percent.

## Change requests
1. docs/spike/main.md: CED-base ONNX output is already a probability, do not apply sigmoid.
2. docs/spike/main.md: `heavy_lock.py run` needs an absolute forward-slash interpreter path.
3. rhythm/dynamics stage design notes (section 7-8 of the spike doc).
No env, lock or models.lock changes.

## Deviations
- Driver is one process per song (steps independent, resumable); stems are written as float32 WAV, not FLAC.
- First CED/RMVPE gating bugs fixed and the affected steps re-run (megafauna: beat_this, pitch, instruments, piano); other songs ran on the fixed code.
