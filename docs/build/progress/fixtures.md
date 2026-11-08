# fixtures — checkpoint log

Agent: fixtures (W1b). Owned: tests/synth/**, tests/contract/synth/**, tests/contract/real-*/**, tests/contract/README.md,
tests/unit/fixtures/**, this file, docs/build/reports/fixtures.md.

## Status: DONE (2026-11-08) — report at docs/build/reports/fixtures.md
- [x] Read PLAN, SPIKE, CONTRACT (+D1-D28), spike/main.md §1-2, contract code.
- [x] tests/synth primitives (primitives.py) + tests
- [x] synthetic song generator (song/score.py -> render.py -> truth.py -> folder.py)
- [x] tests/contract/synth: 195 files, 0 schema errors, `--check` byte-identical
- [x] real-* adapters (real.py): 4 songs, 0 errors, coverage.json per folder
- [x] tests/unit/fixtures: 57 tests (+90 contract) = 147 passed, 1 skipped (10-min file), 1 xfail (CR glob)
- [x] mvh analyze end to end on _truth/synth-song.flac (runtime CLI) exit 0; real ingest reproduces pcm_sha256
- [x] tests/contract/README.md, report

## Design decisions (so a resumed session does not re-decide)
- Song: 120 BPM, A minor, 56.5 s, 44.1 kHz stereo. Pickup beat at 0.5 s (bar 0), bar 1 at 1.0 s, bar 16 is 3/4 (31.0-32.5),
  bar 17 digital silence (32.5-34.5), drop = chorus#2 bars 18-25, outro 26-28 (bar 28 decay, no pulse).
- Sections S01 intro(1-4) S02 verse(5-8) S03 chorus(9-12) S04 bridge/build(13-17) S05 chorus/drop(18-25) S06 outro(26-28).
- Vocals: SAPI David (V1/C1) and Zira (V2/C2) words rendered one by one, then LPC-resynthesised at programmed notes
  ("sung" with exact f0 truth); verse = call-and-response, choruses = duet (V2 harmony on backing_vocals).
- All tracks quantised to the 24-bit grid BEFORE summing -> stems sum to the mix exactly.
- Drums/bass velocities x0.78 outside the drop (score.section_vel) so the drop measures as the loudest ("peak").
- TTS word clips are committed as int16 .npy under tests/synth/assets/tts/ (46 files, 2.4 MB).
- ffmpeg encodes with -fflags +bitexact -flags:a +bitexact for byte-identical reruns.
- Every source file starts with `# ruff: noqa: E501` (long data/docstring lines); `ruff check` + `ruff format --check` pass.

## Commands that worked
- `Set-Location <repo>; . .\scripts\mvh-env.ps1 -Offline; uv run --frozen --no-sync python -m tests.synth.build --only synth` (~20 s)
- `... python -m tests.synth.build --check` rebuilds into a temp dir and diffs against .done.json (0 differing files)
- `... python -m tests.synth.build --only real` (~5 min first time; stems encoded once, then skipped)
- `... python -m pytest -q tests/unit/fixtures tests/unit/contract` (~25 s)
- `... mvh analyze tests\contract\synth\_truth\synth-song.flac --out out\_wip\fixtures\synth --slug synth --no-network --no-heavy-locks`

## Gotchas
- SAPI: SpeechAudioFormatInfo(22050, 16 bit, mono) output is byte-identical across runs.
- PowerShell: backtick escapes only work in double-quoted strings ("{0}`t{1}") - the SAPI marks file needed that.
- Two conftest.py files collide as module `conftest` when tests/unit/contract and tests/unit/fixtures run together:
  never `from conftest import ...` (helpers live in tests/synth/stubrun.py).
- The runtime builder already replaced ingest's stub: stubrun calls mvh.contract.fixture.run_stub directly for every spec.
- W0 voices: k=3 clusters = 2 voices + the ASR-only item 1000 (skipped).
- newton's lyrics_src/chosen_lrclib.json is the plain-only record; the synced record 3921433 is in http/get_*.json.
