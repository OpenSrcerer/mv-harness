import numpy as np

from mvh.stages.mood import frontend as F


def test_mel_filterbank_shape_and_normalisation():
    fb = F.mel_filterbank()
    assert fb.shape == (96, 257) and fb.dtype == np.float32 and fb.min() >= 0.0
    assert (fb.sum(axis=1) > 0).all()
    # Slaney area normalisation: every band integrates to about the same (2 / bandwidth-weighted) value
    assert fb.max() < 0.1


def test_log_mel_frame_count_and_silence():
    n = 16000 * 3
    x = F.log_mel(np.zeros(n, np.float32))
    assert x.shape == (1 + (n - 512) // 256, 96) and x.dtype == np.float32
    assert float(np.abs(x).max()) == 0.0                         # log10(1 + 0) = 0


def test_log_mel_puts_a_sine_in_the_right_band():
    sr = 16000
    for f in (200.0, 1000.0, 4000.0):
        y = 0.5 * np.sin(2 * np.pi * f * np.arange(sr) / sr).astype(np.float32)
        x = F.log_mel(y).mean(axis=0)
        centre_hz = F._mel_to_hz(np.linspace(F._hz_to_mel(0.0), F._hz_to_mel(8000.0), 98))[1:-1]
        assert abs(centre_hz[int(np.argmax(x))] - f) / f < 0.12, f


def test_log_mel_is_frame_local_and_deterministic():
    y = np.random.default_rng(0).standard_normal(16000 * 2).astype(np.float32) * 0.1
    a, b = F.log_mel(y), F.log_mel(y.copy())
    assert np.array_equal(a, b)
    # frame j depends only on samples [256 j, 256 j + 512): appending audio leaves earlier frames untouched
    c = F.log_mel(np.concatenate([y, y]))
    assert np.allclose(c[: a.shape[0]], a, atol=1e-6)


def test_patch_grid_and_centres():
    assert F.patch_starts(100, 187, 93) == [0]                     # shorter than one patch: one padded patch
    s = F.patch_starts(1000, 187, 93)
    assert s[0] == 0 and s[1] - s[0] == 93 and s[-1] + 187 == 1000   # last patch aligned to the end
    assert all(b - a == 93 for a, b in zip(s[:-2], s[1:-1]))
    P, st = F.make_patches(np.ones((50, 96), np.float32), 187, 93)
    assert P.shape == (1, 187, 96) and st == [0] and P[0, 60:].max() == 0.0
    c = F.patch_centres_s([0, 93], 187)
    assert abs(c[0] - 1.504) < 1e-3 and abs(c[1] - c[0] - 93 * 256 / 16000) < 1e-9
    c2 = F.patch_centres_s([0, 62], 128)
    assert abs(c2[0] - 1.032) < 1e-3
