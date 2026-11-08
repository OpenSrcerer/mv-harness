# ruff: noqa: E501  (long literals and docstrings)
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.synth import m4  # noqa: E402

from mvh.stages.harmony import chroma as CH  # noqa: E402


def _tone_chord(pcs, seconds=3.0, sr=22050, base=48, cents=0.0):
    t = np.arange(int(seconds * sr)) / sr
    x = np.zeros_like(t)
    for pc in pcs:
        f = 440.0 * 2 ** ((base + (pc - base) % 12 + cents / 100 - 69) / 12)
        for k in range(1, 6):
            x += np.sin(2 * np.pi * f * k * t) / k
    return (0.3 * x / np.abs(x).max()).astype(np.float32)


def test_chroma_picks_chord_tones():
    cf = CH.compute_chroma(_tone_chord([0, 4, 7]))
    v = CH.aggregate(cf)
    assert set(np.argsort(-v)[:3]) == {0, 4, 7}
    assert cf.chroma.shape[0] == 12 and cf.chroma.shape[1] == len(cf.times) and cf.fps == 22050 / 256


def test_chroma_survives_detuning():
    for cents in (-30, 30):
        cf = CH.compute_chroma(_tone_chord([9, 0, 4], cents=cents))
        assert set(np.argsort(-CH.aggregate(cf))[:3]) == {9, 0, 4}, cents


def test_curve_100hz_shape_range_and_silence():
    x = np.concatenate([np.zeros(22050), _tone_chord([7, 11, 2], 2.0), np.zeros(22050)]).astype(np.float32)
    cf = CH.compute_chroma(x)
    n = math.ceil(len(x) * 100 / 22050)
    c = CH.to_curve_100hz(cf, n)
    assert c.shape == (12, n) and c.dtype == np.float32 and c.min() >= 0 and c.max() <= 1.0 + 1e-6
    assert c[:, :80].max() == 0.0                       # digital-silence lead-in reads 0
    mid = c[:, 150:250].mean(axis=1)
    assert set(np.argsort(-mid)[:3]) == {7, 11, 2}
    assert abs(c[:, 150:250].max(axis=0).mean() - 1.0) < 0.05   # max-normalised per frame


def test_bass_chroma_follows_bass_note():
    x, sr, _ = m4.progression([(7, "maj")], repeats=2, bass=True)
    cf = CH.compute_chroma(m4.resample(x, sr, 22050))
    b = CH.aggregate(cf, 0.5, 3.5, which="bass")
    assert int(np.argmax(b)) == 7
