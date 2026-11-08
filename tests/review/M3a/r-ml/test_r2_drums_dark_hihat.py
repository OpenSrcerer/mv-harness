# ruff: noqa: E501  (long docstrings)
"""R-ML review M3a round 2, finding N2: the F1 fix relabels open hats as cymbals (and drops other hats) whenever the
hi-hat stem is less bright than the synthetic one.

``drumsep_hits`` (fix round) turns a hi-hat-stem hit into ``cymbal`` when its brightness (7-16 kHz over 1.5-6 kHz,
first 30 ms) is under the ABSOLUTE ``cym_bright_db`` = 11 dB with a slow decay and a large rise, and drops it
(``weak_dull``) with a small rise. The generator's hats are unusually bright (stem typical brightness 18.5 dB); the
real hi-hat stems of the fixer's runs measure 10.45 dB (newton-vs-nye: 52 relabelled) and 4.93 dB (jeremy: 138
relabelled cymbal, 210 dropped as weak_dull). Here the generator's CLEAN hi-hat stem is darkened until its typical
brightness is jeremy's (~5 dB; 15 dB less energy above ~6.5 kHz): all 32 open hats become cymbals and 32 hats are
dropped; hat F1 0.997 -> 0.783, cymbal 0.974 -> 0.535. The threshold should be relative to the stem's own typical
brightness. Synthetic input only (fast).
"""
from __future__ import annotations

from m3a_rml_util import oracle_substems, truth


def test_open_hats_on_a_darker_hihat_stem_stay_hats():
    from scipy import signal

    from mvh.stages.drums import core

    subs, sr = oracle_substems()
    air = signal.sosfiltfilt(signal.butter(6, 6500 / (sr / 2), btype="highpass", output="sos"), subs["hihat"])
    subs = dict(subs, hihat=subs["hihat"] - (1 - 10 ** (-15 / 20)) * air)
    hits, st = core.drumsep_hits(subs, sr)
    assert 3.0 <= st["hihat_typical_brightness_db"] <= 8.0   # the brightness the jeremy hi-hat stem has (4.93 dB)
    T = truth()["drum_hits"]
    hat_t = [h.t for h in hits if h.drum == "hat"]
    opened = [h["t"] for h in T if h.get("inst") == "hat_open"]
    kept = sum(1 for t in opened if any(abs(t - x) <= 0.010 for x in hat_t))
    f_hat = core.match_f1(hat_t, [h["t"] for h in T if h["drum"] == "hat"], 0.010)[0]
    assert kept >= 0.9 * len(opened) and f_hat >= 0.9, (
        f"darker hi-hat stem (typical brightness {st['hihat_typical_brightness_db']} dB): open hats kept as hat "
        f"{kept}/{len(opened)}, hat F1 {f_hat:.3f}, relabelled_cymbal={st['relabelled_cymbal']}, "
        f"weak_dull_dropped={st.get('weak_dull_dropped', 0)}")
