"""R-ML round 5 (reviewer r-ml-m3b-r5): regression from the R-ML-M3b-r4-2 fix (I-M3b-15).

Voiced frames inside aligned lyric lines that the tagger left unlabelled now inherit the song's dominant TAGGED style,
including "speech". On MEGAFAUNA the tagger's only label is 7 s of "speech" (from CED on the near-silent lead_vocals
stem) and it covers 0.07 s of the 6.96 voiced seconds. Every sung frame of the singer then inherits "speech", the
sung-range statistics see 0 sung frames, and meta/vocal_range.json loses lowest/highest/p2/p98/register:
r4 rerun E3-E4, p2 52.1 / p98 67.0, alto, conf 0.44; r5 rerun of the same upstream (out/_wip/r-ml-m3b-r5/megafauna):
all null, spoken_pitch 6.96 s. The round-4 fix suggestion kept "speech" leads sung for exactly this song; only a rap
style should be inherited (docs/SPIKE.md rules out range statistics on rap, not on a stray speech label).

Synthetic mirror: a sung vibrato voice (E3-E4) in the vocals stem 4-28 s (lead_vocals near silent, tagger voice low
there), aligned ctc lines cover it, and the tagger's only style label is 7 s of "speech" at 31-38 s where nothing is
pitched. Expected: a sung range is reported. RMVPE, SwiftF0 and CED run inside a heavy slot (about 30 s).
"""
from __future__ import annotations

import numpy as np
import pytest
from m3b_fakectx import FakeCtx, activity

SR = 44100
DUR = 40.0


@pytest.mark.real
def test_a_stray_speech_label_does_not_erase_the_sung_range():
    from tests.synth.primitives import sung_sine

    from mvh.stages import vocals
    from mvh.testing import heavy

    seq = [52, 55, 57, 59, 60, 62, 64, 60]
    notes = [(4.0 + 0.6 * i, 0.55, seq[i % len(seq)]) for i in range(40)]
    x, _, _ = sung_sine(notes, vib_cents=40.0, sr=SR)
    y = np.zeros(int(DUR * SR), np.float32)
    y[: min(y.size, x.size)] = x[: y.size]
    st = np.stack([y, y])
    n100 = int(DUR * 100)
    voice_1hz = np.full(int(DUR), 0.1, np.float32)
    voice_1hz[31:38] = 0.9  # the tagger only hears a voice (and calls it speech) where nothing is pitched
    lines = [{"id": f"L{i + 1:03d}", "t": t0, "d": 2.9, "conf": 0.5, "grade": "C", "timing_source": "ctc", "backing": False,
              "n_words": 6} for i, t0 in enumerate(np.arange(4.0, 28.0, 3.0).tolist())]
    ctx = FakeCtx(
        vocals,
        {"mix": (st, SR), "vocals": (st, SR), "lead_vocals": (1e-5 * st, SR)},
        curves={"stem.vocals.active": activity(n100, [(3.5, 28.5)]),
                "stem.lead_vocals.active": np.zeros(n100, np.float32),
                "inst.voice": voice_1hz},
        upstream={"lyrics": {"lyrics/lyrics.json": {"instrumental": False, "grade": "C", "lines": lines}},
                  "stem_activity": {"meta/stems.json": {"stems": {"vocals": {"present": False}}}}},
        events={"vocal_style": [{"t": 31.0, "d": 7.0, "style": "speech", "conf": 0.6}], "beats": [], "bars": []},
    )
    with heavy("review-r-ml-m3b-r5", threads=3):
        vocals.run(ctx)
    vr = ctx.writer.json_docs["meta/vocal_range.json"]
    print(f"present={vr['present']} voiced_s={vr['voiced_s']} style={vr.get('style')} basis={vr.get('basis')} "
          f"p2={vr['p2']} p98={vr['p98']} spoken={vr.get('spoken_pitch')}")
    assert vr["present"] is True
    assert vr["p2"] is not None and vr["lowest"] is not None, (
        f"{vr['voiced_s']} s of sung vibrato voice inside aligned lines inherited the tagger's stray 'speech' label "
        f"(which covers none of them): sung range null, spoken_pitch {vr.get('spoken_pitch')}")
    assert abs(vr["p2"] - 52) <= 1.0 and abs(vr["p98"] - 64) <= 1.0
