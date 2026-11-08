# ruff: noqa: E501  (long docstrings)
"""R-ML review M3a, finding F3: on a mono input the karaoke split (lead / backing) inverts, silently.

The karaoke model (mel_band_roformer_karaoke_aufr33_viperx) was trained on stereo mixes, where the lead is centred and
backing vocals are spread; that pan cue carries much of its decision. separate_hq feeds a mono song to it as a
dual-mono pair (``fit.stereo44`` duplicates the channel) and still reports ``lead_backing_split: true`` without a flag.
On the synthetic song (V1 lead centred, V2 harmony panned -5 dB) the 17-29 s excerpt gives lead_vocals SDR 8.3 dB
against the truth lead in stereo but 0.5 dB in mono, where lead_vocals sits at -18.8 dB vs the mix and backing at
-5.1 dB (stereo: -6.9 / -10.3): the lead voice is routed to ``backing_vocals``. lyrics, voices and lipsync read
``lead_vocals``. The newton-vs-nye rap (a 40 s excerpt) keeps its lead in mono but the backing level rises from -30.2
to -17.0 dB, so the split is unreliable on mono in general.

Passes when the stage either declines or flags the split for mono / dual-mono input (``lead_backing_split`` false, or
a ``sep:*`` flag naming lead/backing), or actually delivers the lead (SDR >= 3 dB against the truth lead).
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from m3a_rml_util import MONO_SPAN, SYNTH

pytestmark = [pytest.mark.real, pytest.mark.slow]


def test_mono_input_keeps_the_lead_in_lead_vocals_or_flags_the_split(synth_mono_e2e):
    from mvh.io import audio as aio

    with open(synth_mono_e2e / "meta" / "separation.json", encoding="utf-8") as fh:
        sep = json.load(fh)
    flagged = (not sep["lead_backing_split"]) or any(
        ("lead" in f or "backing" in f or "karaoke" in f) for f in sep.get("flags", []))
    a, b = MONO_SPAN[0] * 44100, MONO_SPAN[1] * 44100
    ref = aio.decode(SYNTH / "stems" / "lead_vocals.flac").samples[:, a:b].astype(np.float64).mean(axis=0)
    est = aio.decode(synth_mono_e2e / "stems" / "lead_vocals.flac").samples.astype(np.float64).mean(axis=0)
    n = min(ref.size, est.size)
    sdr = 10.0 * np.log10(np.sum(ref[:n] ** 2) / np.sum((ref[:n] - est[:n]) ** 2))
    rel = sep["checks"]["stem_rel_db"]
    assert flagged or sdr >= 3.0, (
        f"mono input: lead_vocals SDR {sdr:.2f} dB vs the truth lead (stereo gives ~8.3), lead {rel['lead_vocals']} dB / "
        f"backing {rel['backing_vocals']} dB vs the mix, lead_backing_split={sep['lead_backing_split']}, "
        f"flags={sep.get('flags')}")
