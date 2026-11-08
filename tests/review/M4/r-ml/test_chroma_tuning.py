# ruff: noqa: E501  (long docstrings)
"""R-ML M4: the chroma tuning correction is applied at one third of its size.

``chroma._compute_chroma`` estimates the tuning with ``librosa.estimate_tuning(..., bins_per_octave=12)``, which
returns the offset in fractions of a *semitone*, then passes it unchanged to
``librosa.cqt(..., bins_per_octave=36, tuning=tuning)``. librosa applies ``fmin * 2 ** (tuning / bins_per_octave)``,
i.e. it reads the value as fractions of a *third of a semitone*: a recording 45 cents sharp is corrected by 15
cents and its energy leaks into the neighbouring pitch classes. The real test song jeremy is estimated at +0.28
semitones (provenance note of its events/chords.json), so about 19 cents stay uncorrected. Everything built on this
chroma (curves/chroma12.f32, the KS/Temperley/Albrecht profiles, the template + Viterbi chord check, chord `conf`
and `bass_pc`) is affected; lv-chordia is not (it has its own CQT).

Pure DSP, no model: an A minor triad of additive tones, in tune and 45 cents sharp. With the correction in the
right unit (``tuning * 36 / 12``) the chord-tone share of the aggregated chroma is 0.869 / 0.870; today it drops
from 0.868 to 0.734.
"""
from __future__ import annotations

import numpy as np
from m4rml_signals import SR22, _note


def _chord_tone_share(cents: float) -> tuple[float, float]:
    from mvh.stages.harmony.chroma import aggregate, compute_chroma

    y = sum(_note(57 + cents / 100 + i, 6.0, SR22) for i in (0, 3, 7)).astype(np.float32)   # A3 minor triad
    cf = compute_chroma(y, SR22)
    c = aggregate(cf)
    c = c / c.sum()
    return float(c[[9, 0, 4]].sum()), float(cf.tuning)


def test_detuned_recording_gives_the_same_chroma_as_an_in_tune_one():
    ref, _t0 = _chord_tone_share(0.0)
    det, t45 = _chord_tone_share(45.0)
    assert abs(t45 - 0.45) < 0.05, t45                     # the estimate itself is right (in semitones)
    assert det >= ref - 0.03, f"chord-tone share {det:.3f} at +45 cents vs {ref:.3f} in tune"
