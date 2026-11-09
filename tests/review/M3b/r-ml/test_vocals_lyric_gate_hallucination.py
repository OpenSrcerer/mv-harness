"""R-ML round 4 (reviewer r-ml-m3b-r4): the S04 fix (I-M3b-14) treats EVERY lyric line as voice evidence.

lyrics/lyrics.json marks lines whose timing has no acoustic support: ``timing_source`` "interpolated" (nothing aligned,
times spread from the text) or "lrclib_line" (LRCLIB line times copied without an audio match), with ``conf`` ~0 and
grade D. vocals._lyric_mask ignores timing_source, conf and grade, so such lines (user lyrics or an LRCLIB match on an
instrumental / karaoke version) open the voice gate for whatever RMVPE pitches inside them. Here the vocals stem holds
only a synth sawtooth lead (the tagger says no voice, inst.voice = 0, stem vote = absent), lead_vocals is near silent,
and the "lines" are interpolated with conf 0: the stage still declares a present singer and derives a vocal range,
phrases and vocal notes from the synth lead. That is hallucinated output from a gate that should only trust aligned lines.

Synthetic input only; RMVPE, SwiftF0 and CED run inside a heavy slot (about 20 s).
"""
from __future__ import annotations

import numpy as np
import pytest
from m3b_fakectx import FakeCtx, activity

SR = 44100
DUR = 30.0


def _synth_lead() -> np.ndarray:
    """A band-limited sawtooth lead (15 harmonics) playing 0.5 s notes between A3 and A4, 2-28 s."""
    t = np.arange(int(DUR * SR)) / SR
    y = np.zeros_like(t)
    melody = [57, 59, 60, 62, 64, 65, 67, 69, 67, 65, 64, 62]
    k = 0
    for t0 in np.arange(2.0, 28.0, 0.5):
        f = 440.0 * 2 ** ((melody[k % len(melody)] - 69) / 12)
        k += 1
        i0, i1 = int(t0 * SR), int((t0 + 0.45) * SR)
        tt = t[i0:i1] - t0
        env = np.minimum(1.0, np.minimum(tt / 0.01, (0.45 - tt) / 0.02))
        y[i0:i1] += env * sum(np.sin(2 * np.pi * h * f * tt) / h for h in range(1, 16))
    return (0.15 * y / np.max(np.abs(y))).astype(np.float32)


@pytest.mark.real
def test_interpolated_lyric_lines_do_not_turn_a_synth_lead_into_a_singer():
    from mvh import stages  # noqa: F401
    from mvh.stages import vocals
    from mvh.testing import heavy

    lead_synth = _synth_lead()
    voc = np.stack([lead_synth, lead_synth])
    lead_vocals = 1e-5 * voc  # karaoke split suspect: the lead stem is ~100 dB down
    n100 = int(DUR * 100)
    lines = [{"id": f"L{i + 1}", "t": t0, "d": 2.8, "conf": 0.0, "grade": "D", "timing_source": "interpolated",
              "backing": False, "n_words": 4}
             for i, t0 in enumerate(np.arange(2.0, 27.0, 3.0).tolist())]
    ctx = FakeCtx(
        vocals,
        {"mix": (voc, SR), "vocals": (voc, SR), "lead_vocals": (lead_vocals, SR)},
        curves={"stem.vocals.active": activity(n100, [(1.5, 28.5)]),
                "stem.lead_vocals.active": np.zeros(n100, np.float32),
                "inst.voice": np.zeros(int(DUR), np.float32)},  # the tagger hears no voice anywhere
        upstream={"lyrics": {"lyrics/lyrics.json": {"instrumental": False, "grade": "D", "lines": lines}},
                  "stem_activity": {"meta/stems.json": {"stems": {"vocals": {"present": False}}}}},
        events={"vocal_style": [], "beats": [], "bars": []},
    )
    with heavy("review-r-ml-m3b-r4", threads=3):
        vocals.run(ctx)
    vr = ctx.writer.json_docs["meta/vocal_range.json"]
    n_notes = len(ctx.writer.ev.get("notes.vocals", []))
    n_ph = len(ctx.writer.ev.get("vocal_phrases", []))
    print(f"present={vr['present']} voiced_s={vr['voiced_s']} p2={vr['p2']} p98={vr['p98']} notes={n_notes} phrases={n_ph}")
    assert vr["present"] is False, (
        f"a synth lead inside interpolated (conf 0) lyric lines became a singer: voiced {vr['voiced_s']} s, "
        f"range p2 {vr['p2']} - p98 {vr['p98']}, {n_notes} vocal notes, {n_ph} phrases")
    assert n_notes == 0 and n_ph == 0
