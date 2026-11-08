# ruff: noqa: E501  (long numeric tables / docstrings)
"""Pure pitch logic of the vocals stage (no models)."""

from __future__ import annotations

import numpy as np

from mvh.stages.vocals import pitch as P


def test_arbitration_rmvpe_decides_voicing_and_pitch():
    n = 6
    rm = np.array([60, 60, 60, 60, 60, 60.0])
    rc = np.array([.9, .9, .9, .9, .1, .9])
    sw = np.array([60.2, 72.0, 64.0, np.nan, 60.0, 60.0])
    sc = np.array([.95, .95, .95, .95, .99, .5])
    a = P.arbitrate(rm, rc, sw, sc, gate=0.3, sw_gate=0.9)
    assert np.isnan(a.midi[4])                          # SwiftF0 never voices a frame RMVPE rejects
    assert np.allclose(a.midi[[0, 1, 2, 3, 5]], 60)     # RMVPE pitch wins (octave and other disagreements)
    assert a.conf[0] == 0.9 and abs(a.conf[1] - 0.9 * 0.85) < 1e-9 and abs(a.conf[2] - 0.9 * 0.7) < 1e-9
    assert a.both == 3 and abs(a.octave - 1 / 3) < 1e-9
    assert n == a.midi.size


def test_octave_islands_and_short_runs():
    m = np.full(40, 60.0)
    m[10:14] = 72.0
    m[30] = np.nan
    m[36:40] = np.nan
    m[33:36] = 60.0
    out = P.fix_octave_islands(m)
    assert np.allclose(out[10:14], 60)
    d = P.drop_short(np.array([np.nan, 60, 60, np.nan, 61, 61, 61, 61, 61, 61]), 5)
    assert np.isnan(d[1:3]).all() and np.isfinite(d[4:]).all()


def test_pitch01_eases_through_gaps_and_never_nan():
    m = np.full(100, np.nan)
    m[10:30] = 60.0
    m[60:80] = 72.0
    p = P.pitch01(m, 60.0, 72.0, 0.15)
    assert np.isfinite(p).all()
    assert np.allclose(p[:30], 0.0) and np.allclose(p[60:80], 1.0)   # exact where voiced, first value held before
    assert np.allclose(p[30:45], 0.0)                                  # held through the gap ...
    ramp = p[45:60]
    assert np.all(np.diff(ramp) > 0) and ramp[-1] < 1.0               # ... then eased over the last 150 ms
    assert np.allclose(p[80:], 1.0)
    assert np.allclose(P.pitch01(np.full(10, np.nan), 0, 1), 0.0)     # nothing voiced -> 0


def test_segment_notes_with_vibrato_and_steps():
    t = np.arange(150) / 100
    m = np.where(t < 0.7, 57 + 0.35 * np.sin(2 * np.pi * 5.5 * t), 60 + 0.35 * np.sin(2 * np.pi * 5.5 * t))
    m[148:] = np.nan
    ns = P.segment_notes(m)
    assert [x["midi"] for x in ns] == [57, 60]
    assert abs(ns[1]["t"] - 0.7) <= 0.05


def test_sustained_extremes_and_register():
    f0 = P.midi_to_hz(np.full(500, 60.0))
    notes = [{"t": 0.0, "d": 0.2, "midi": 55, "i0": 0, "i1": 20}, {"t": 0.22, "d": 0.15, "midi": 55, "i0": 22, "i1": 37},
             {"t": 1.0, "d": 0.05, "midi": 40, "i0": 100, "i1": 105},   # too short to count as sustained
             {"t": 2.0, "d": 0.5, "midi": 67, "i0": 200, "i1": 250}, {"t": 3.0, "d": 0.4, "midi": 60, "i0": 300, "i1": 340}]
    lo, hi = P.sustained_extremes(notes, f0)
    assert lo["midi"] == 55 and lo["name"] == "G3" and lo["t"] == 0.0
    assert hi["midi"] == 67 and hi["t"] == 2.0
    assert P.register_of(56.0, 0.1) == "baritone" and P.register_of(62.0, 0.1) == "tenor"
    assert P.register_of(70.0, 0.9) == "soprano" and P.register_of(60.0, 0.9) == "alto"


def test_phrases_join_short_rests():
    m = np.full(400, np.nan)
    m[0:100] = 60
    m[130:200] = 62   # 0.3 s rest -> same phrase
    m[300:350] = 64   # 1.0 s rest -> new phrase
    m[398:400] = 65   # 0.48 s rest: separate, and too short to be a phrase
    assert P.phrases(m, 0.45, 0.3) == [(0, 200), (300, 350)]


def test_to_grid_nearest():
    t = np.array([0.0, 0.016, 0.032, 0.048])
    v = np.array([1.0, 2.0, 3.0, 4.0])
    g = P.to_grid(t, v, 5)
    assert list(g) == [1.0, 2.0, 2.0, 3.0, 4.0]
