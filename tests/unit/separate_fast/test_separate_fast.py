# ruff: noqa: E501  (long docstrings and tables)
"""separate_fast: the fitting helpers and invariants (fast), and the real demucs-onnx array route (``-m real``)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from tests.synth.m3a import SYNTH, fixture_upstreams, run_stage

from mvh.sep import fit, invariants


def test_stereo44_and_fit_channels():
    m = np.arange(10, dtype=np.float32)[None, :]
    s = fit.stereo44(m)
    assert s.shape == (2, 10) and np.array_equal(s[0], s[1])
    back = fit.fit_channels(s, 1)
    assert back.shape == (1, 10) and np.allclose(back[0], m[0])
    assert fit.fit_length(s, 12).shape == (2, 12) and fit.fit_length(s, 7).shape == (2, 7)


def test_to_mix_resamples_to_the_song_rate(tmp_path):
    sr = 44100
    t = np.arange(sr) / sr
    x = np.stack([np.sin(2 * np.pi * 440 * t)] * 2).astype(np.float32)
    y = fit.to_mix(x, sr, 48000, 48000, 2, tmp_path)
    assert y.shape == (2, 48000)
    # same tone at the new rate (away from the edges)
    t2 = np.arange(48000) / 48000
    ref = np.sin(2 * np.pi * 440 * t2)
    assert invariants.diff_db(y[0, 1000:-1000], ref[1000:-1000]) < -40


def test_invariants_exact_and_gain():
    rng = np.random.default_rng(1)
    a, b, c = (rng.standard_normal((2, 44100)).astype(np.float32) * g for g in (0.3, 0.2, 0.01))
    mix = a + b + c
    assert invariants.residual_db(mix, [a, b, c]) < -120
    assert invariants.residual_db(mix, [a, b]) == pytest.approx(10 * np.log10(np.sum(c.astype(float) ** 2) / np.sum(mix.astype(float) ** 2)), abs=1e-3)
    g = invariants.gain_gate(mix, {"a": a, "b": b, "c": c})
    assert abs(g["a"]["gain_db"]) < 1e-3 and g["a"]["tol_db"] == 0.1 and g["a"]["pass"] is True
    assert g["c"]["tol_db"] is None and g["c"]["pass"] is None      # 30 dB below the mix: not gated
    g2 = invariants.gain_gate(mix, {"a": a * 1.1, "b": b, "c": c})  # a re-levelled stem fails
    assert g2["a"]["pass"] is False


@pytest.mark.real
def test_demucs_array_route_on_the_synthetic_song(tmp_path):
    """Real model: the stage on the synthetic song; stems are finite, aligned, and sum near the mix."""
    from mvh.io.wav import read_wav

    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("separate_fast", tmp_path, ups, ing, heavy_locks=True)
    mix, sr = read_wav(SYNTH / "_intermediate" / "ingest" / "canonical.wav")
    with open(out / "fast" / "separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    stems = {}
    for s in ("vocals", "drums", "bass", "other"):
        x, sr2 = read_wav(out / "fast" / f"{s}.wav")
        assert sr2 == sr and x.shape == mix.shape and np.isfinite(x).all()
        stems[s] = x
    assert meta["invariants"]["sum_error_db"] < -15
    # the generator's drums are louder in the drums stem than anywhere else
    d = {k: invariants.rms_dbfs(v) for k, v in stems.items()}
    assert d["drums"] > -40 and d["bass"] > -40
    # determinism: a second run is byte-identical
    out2, _ = run_stage("separate_fast", tmp_path / "again", ups, ing, heavy_locks=True)
    for s in stems:
        assert (out / "fast" / f"{s}.wav").read_bytes() == (out2 / "fast" / f"{s}.wav").read_bytes()
