"""W4A-ACAP (M1 spectral, D80 precision): hits.kick must not turn sung plosives / syllable onsets into kicks.

The contract fixture's own vocals stem (synthetic voices, no drums; truth 0 kicks) had 13 'kicks' (kick_conf 0.68-1.00),
each within 0.25 s of a sung word. A kick's 30-150 Hz peak sits above the 300-3000 Hz voice-formant peak in the 40 ms
after its onset; a vocal onset is formant-dominated (``kick_low_over_mid_db``)."""
from __future__ import annotations

import math

import numpy as np
from tests.synth.m1.harness import run_m1
from tests.synth.m1.markers import REPO

from mvh.stages.spectral import dsp


def test_vocals_stem_has_no_kicks(tmp_path):
    from mvh.io import audio as aio

    d = aio.decode(REPO / "tests" / "contract" / "synth" / "stems" / "vocals.flac")
    r = run_m1(np.asarray(d.samples, np.float32), int(d.sr), tmp_path, stages=("spectral",))
    kicks = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    assert len(kicks) <= 2, [(round(k["t"], 2), k["kick_conf"]) for k in kicks]


def test_formant_dominated_onset_takes_no_route():
    ev = dsp.KickEvidence(attack=12.0, glide=1.6, f_early=90.0, click=8.0, low_ex=8.0, body_ex=12.0, body_add=8.0,
                          body_db=-20.0, decay=12.0, gate=1.0, low_over_mid=6.0)
    p = dict(dsp.KICK_DEFAULTS)
    assert dsp.kick_route(ev, p) == "sweep"
    ev.low_over_mid = -3.0
    assert dsp.kick_route(ev, p) == ""
    p["low_over_mid_db"] = -math.inf          # the gate off: the old behaviour
    assert dsp.kick_route(ev, p) == "sweep"
