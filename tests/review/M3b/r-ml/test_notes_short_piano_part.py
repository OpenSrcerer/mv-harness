"""R-ML M3b (major): a piano part that plays for less than 10 % of the song gets no notes at all.

``notes.run`` treats ``params.piano_min_active`` (0.10) as a fraction of the WHOLE song. Below it, ``_piano_gate``
returns "skip" without running CED, and the basic-pitch fallback is blocked too
(``results["piano"] = []`` "none (piano stem active < 10 %)"), with no warning. The SPIKE rule is "piano_transcription
only when the piano stem is active AND CED reports piano" (to stop the CRNN inventing notes on a SILENT stem); it does
not ask to discard an active, clean piano stem because the part is short. A piano intro, bridge or chorus figure of
15-25 s in a 4-minute song is 6-10 % of it.

Evidence (reviewer run, out/_wip/r-ml-m3b/synth, the synthetic song through the real upstream stages): the piano stem
is active 4.5 s (0.079 of 56.5 s) -> 0 piano notes. With ``--param notes.piano_min_active=0.02`` the same stage writes 25
piano notes, 18 of them correct (onset F1 vs truth: precision 0.72).

This test: a 60 s song whose only pitched content is 8 clean piano notes (20-24.3 s, 7 % of the song, stem active and
present). Expected: the piano notes are transcribed (by the CRNN when CED hears piano, else by basic-pitch).

Fix: express the activity floor in seconds of activity (or gate per active segment), keep the CED condition only for
the CRNN, and warn when an active stem is skipped.
"""
from __future__ import annotations

import numpy as np
import pytest
from m3b_fakectx import FakeCtx, activity

pytestmark = pytest.mark.real

SR = 44100
DUR = 60.0
PIANO = [(20.0 + 0.5 * i, 0.45, m, 0.8) for i, m in enumerate([60, 64, 67, 72, 71, 67, 64, 62])]


def _song():
    from tests.synth.primitives import midi_render

    x, sr, _truth = midi_render(PIANO, program="piano", sr=SR, tail_s=0.5)
    y = np.zeros(int(DUR * SR))
    y[: x.size] = x[: y.size]
    return y.astype(np.float32)


def test_short_active_piano_part_is_transcribed():
    import mvh.stages.notes as notes
    from mvh.testing import heavy

    piano = _song()
    silent = np.zeros_like(piano)
    n100 = int(DUR * 100)
    act = activity(n100, [(19.95, 24.3)])
    ratio = float(act.mean())
    assert 0.05 < ratio < 0.10
    stems_meta = {"stems": {"piano": {"present": True, "active_ratio": round(ratio, 4)},
                            **{s: {"present": False, "active_ratio": 0.0} for s in ("bass", "guitar", "other")}}}
    ctx = FakeCtx(notes, {"mix": (np.stack([piano, piano]), SR), "piano": (np.stack([piano, piano]), SR),
                          "bass": (silent, SR), "guitar": (silent, SR), "other": (silent, SR)},
                  curves={"stem.piano.active": act, **{f"stem.{s}.active": np.zeros(n100) for s in ("bass", "guitar", "other")}},
                  upstream={"stem_activity": {"meta/stems.json": stems_meta}})
    with heavy("r-ml-m3b-test", threads=3):
        res = notes.run(ctx)
    items = ctx.writer.ev.get("notes.piano", [])
    prov = "; ".join(res.provenance.get("notes", []))
    hits = sum(any(abs(it["t"] - t) <= 0.05 and it["midi"] == m for it in items) for t, _d, m, _v in PIANO)
    assert hits >= 6, (f"only {hits}/8 piano notes transcribed from an active, clean piano stem "
                       f"(active {ratio:.3f} of the song; {len(items)} notes written; provenance: {prov})")
