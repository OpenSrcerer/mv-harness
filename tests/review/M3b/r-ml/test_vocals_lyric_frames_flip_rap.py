"""R-ML round 4 (reviewer r-ml-m3b-r4): lyric-gated frames are counted as SINGING and added to the style tally.

I-M3b-14: "when the tagger gave them no style they count as sung" and ``style_secs["singing"] += lyr_sung``. An aligned
lyric line is evidence that a VOICE is there, not that it sings: on a rap song the lines are rap lines. When the tagger
labels part of a rap verse (rap) and misses the rest (inst.voice below the gate under a dense beat), the untagged
lyric frames become "singing", outvote the rap seconds, flip the dominant style to singing, and the sung-range
statistics are then computed over the rap (docs/SPIKE.md: f0 range statistics are not run on rap; PLAN §5 vocals).

Synthetic: one harmonic voice on lead_vocals 2-28 s; the tagger hears it (and calls it rap) 2-12 s only; aligned lines
(ctc, conf 0.9) cover 2-28 s. Expected: the style stays rap and no sung range is reported from these frames.
RMVPE, SwiftF0 and CED run inside a heavy slot (about 20 s).
"""
from __future__ import annotations

import numpy as np
import pytest
from m3b_fakectx import FakeCtx, activity

SR = 44100
DUR = 30.0


@pytest.mark.real
def test_untagged_lyric_frames_do_not_flip_a_rap_lead_to_singing():
    from tests.synth.primitives import sung_sine

    from mvh.stages import vocals
    from mvh.testing import heavy

    seq = [55, 57, 55, 53, 55, 57, 58, 57]  # a narrow, speech-like contour
    notes = [(2.0 + 0.5 * i, 0.45, seq[i % len(seq)]) for i in range(52)]
    x, sr, _ = sung_sine(notes, vib_cents=0.0, sr=SR)
    y = np.zeros(int(DUR * SR), np.float32)
    y[: min(y.size, x.size)] = x[: y.size]
    st = np.stack([y, y])
    n100 = int(DUR * 100)
    voice_1hz = np.zeros(int(DUR), np.float32)
    voice_1hz[2:12] = 0.9   # the tagger hears the voice here ...
    voice_1hz[12:28] = 0.2  # ... and misses it here (below the 0.35 gate; no style label)
    lines = [{"id": f"L{i + 1}", "t": t0, "d": 2.8, "conf": 0.9, "grade": "A", "timing_source": "ctc", "backing": False,
              "n_words": 6} for i, t0 in enumerate(np.arange(2.0, 27.0, 3.0).tolist())]
    ctx = FakeCtx(
        vocals,
        {"mix": (st, SR), "vocals": (st, SR), "lead_vocals": (st, SR)},
        curves={"stem.lead_vocals.active": activity(n100, [(1.5, 28.5)]),
                "stem.vocals.active": activity(n100, [(1.5, 28.5)]),
                "inst.voice": voice_1hz},
        upstream={"lyrics": {"lyrics/lyrics.json": {"instrumental": False, "grade": "A", "lines": lines}},
                  "stem_activity": {"meta/stems.json": {"stems": {"vocals": {"present": True}}}}},
        events={"vocal_style": [{"t": 2.0, "d": 10.0, "style": "rap", "conf": 0.8}], "beats": [], "bars": []},
    )
    with heavy("review-r-ml-m3b-r4", threads=3):
        vocals.run(ctx)
    vr = ctx.writer.json_docs["meta/vocal_range.json"]
    print(f"style={vr.get('style')} basis={vr.get('basis')} present={vr['present']} voiced_s={vr['voiced_s']} "
          f"p2={vr['p2']} p98={vr['p98']}")
    assert vr.get("style") == "rap", f"untagged lyric frames flipped the rap lead to {vr.get('style')!r}"
    assert vr["basis"] != "voiced frames", "the sung-range statistics were computed over the rap frames"
