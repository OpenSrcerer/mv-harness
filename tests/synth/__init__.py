# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Deterministic synthetic test signals and the synthetic multitrack song (PLAN §7.1, W1b fixtures).

Modules
  audio_io    WAV read/write (float32 / int16 / int24), 24-bit grid quantisation, ffmpeg encoders (bitexact)
  dsp         oscillators, envelopes, one-shot drums, simple synth voices (all seeded, numpy only)
  midi        a minimal Standard MIDI File writer (deterministic)
  tts         Windows SAPI word rendering (David, Zira) + cached assets + LPC "singing" resynthesis
  primitives  click tracks, EBU loudness signals, sweeps, rendered MIDI, vibrato sines, TTS sentences, edge-case files
  song        the synthetic song: score (ground truth) -> render -> contract folder (tests/contract/synth/)
  real        thin adapters from the W0 cache (tests/.cache/real/) to tests/contract/real-<slug>/
  build       ``python -m tests.synth.build``: regenerates everything deterministically

Nothing here prints lyric text of real songs. Synthetic lyrics are invented for the fixture.
"""
