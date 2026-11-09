# ruff: noqa: E501  (long docstrings)
"""R-ML M4 round 3: M1 (r2) is fixed for white noise, but lv-chordia's no-chord share is still not used as tonal evidence.

The r2 fix counts ks/temperley/albrecht as one "profiles" source and caps conf at 0.25 when fewer than two sources have a
winner. On band-limited noise (300-700 Hz) the real S-KEY model clears the 0.2 vote gate (recovered p_max 0.41, i.e. it
hallucinates a key with some confidence), so the sources are {skey, profiles} = 2 and the cap never fires, even though
lv-chordia, the dedicated chord model, reports 100 % no-chord. Probe out/_wip/r-ml-m4-r3/probe_extra.log, case band60
(real S-KEY, real lv-chordia): "F minor", conf 0.708, flags only ['key:methods_disagree'] (no key:low_confidence, no
key:no_tonal_evidence). The r2 M1 suggested fix ("a no-chord share near 1.0 from lv-chordia should by itself mark the key
as having no tonal evidence") was not implemented. Drones, risers, noise interludes and ambient pieces reach this path.

The fast test drives it with a stub S-KEY at the probability the real model gave (0.41 on F minor) and lv-chordia's real
output on noise (one N segment). The real test uses the real S-KEY model.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from m4rml_signals import SR22, beat_grid


def _band_noise(seconds: int = 60) -> np.ndarray:
    rng = np.random.default_rng(1)
    y = rng.standard_normal(seconds * SR22)
    spec = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), 1 / SR22)
    spec[(f < 300) | (f > 700)] = 0
    band = np.fft.irfft(spec, len(y))
    return (band / np.abs(band).max() * 0.3).astype(np.float32)


class _HallucinatingSKey:
    """Stands in for keys.SKey: the recovered probability the real model gives on this band noise (0.41 on F minor)."""

    def __init__(self):
        from mvh.stages.harmony import theory as T

        self.keymap = [T.key_name(pc, mode) for mode in ("major", "minor") for pc in range(12)]

    def log_scores(self, y22):
        from mvh.stages.harmony import keys as K

        p = np.full(24, 0.59 / 23)
        p[self.keymap.index("F minor")] = 0.41
        return K.skey_log(p, self.keymap), p


def _analyse(y, skey):
    from mvh.stages.harmony import core

    dur = len(y) / SR22
    beats, bars = beat_grid(dur)

    def lv():                       # lv-chordia's real output on this noise (probe: no-chord share 1.0)
        return [{"start_time": 0.0, "end_time": dur, "chord": "N"}]

    return core.analyse(y, dur, math.ceil(dur * 100), beats, bars, lv, skey, {})


def _assert_not_confident(res):
    g, flags = res.key_meta["global"], res.key_meta["flags"]
    assert res.summary["no_chord_share"] >= 0.99
    assert g["conf"] <= 0.3 or "key:no_tonal_evidence" in flags or "key:low_confidence" in flags, (g, flags, res.key_meta["agreement"])


def test_all_no_chord_noise_gets_no_confident_key_stub_skey():
    _assert_not_confident(_analyse(_band_noise(), _HallucinatingSKey()))


@pytest.mark.real
def test_all_no_chord_noise_gets_no_confident_key_real_skey(skey):
    from mvh.testing import heavy

    with heavy("r-ml-m4-r3-test", threads=3):
        res = _analyse(_band_noise(), skey)
    _assert_not_confident(res)
