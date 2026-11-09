"""R-ML review M3a round 2, finding F3 (re-opened): the mono fix is a cliff at side/mid = -30 dB; a near-mono master
still inverts the lead / backing split silently.

``separate_hq`` now skips the karaoke model when ``fit.is_mono`` (side energy >= 30 dB under mid) and flags it. The same
17-29 s synthetic excerpt with its side scaled to 24 dB under mid (L/R correlation 0.992: a mono-ish master, a mono
recording with a stereo reverb) passes as stereo: lead_vocals -11.1 dB vs the mix, backing_vocals -6.3 dB (the truth
has the lead 6.4 dB over the backing; full stereo gives -6.9 / -10.3), lead SDR 2.08 dB (stereo 8.31),
``lead_backing_split: true``, no flag. At -18 dB lead and backing come out level (-8.2 / -8.0). Real stereo songs
measure backing 9-22 dB under lead (jeremy -7.6 / -16.8, newton-vs-nye -6.6 / -29.0), so "backing louder than lead"
is the cheap sanity flag the round-1 finding asked for; the fix did not add it.
"""
from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.real, pytest.mark.slow]


def test_near_mono_input_keeps_the_lead_louder_than_backing_or_flags_the_split(synth_narrow_e2e):
    with open(synth_narrow_e2e / "meta" / "separation.json", encoding="utf-8") as fh:
        sep = json.load(fh)
    rel = sep["checks"]["stem_rel_db"]
    flagged = (not sep["lead_backing_split"]) or any(
        ("lead" in f or "backing" in f or "karaoke" in f) for f in sep.get("flags", []))
    assert flagged or rel["lead_vocals"] > rel["backing_vocals"], (
        f"near-mono input (side 24 dB under mid): lead {rel['lead_vocals']} dB / backing {rel['backing_vocals']} dB vs "
        f"the mix, lead_backing_split={sep['lead_backing_split']}, flags={sep.get('flags')}")
