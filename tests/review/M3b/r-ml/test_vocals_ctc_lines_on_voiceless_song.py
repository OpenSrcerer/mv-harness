"""R-ML round 5 (reviewer r-ml-m3b-r5): R-ML-M3b-r4-1 is only partly fixed.

I-M3b-15 drops lines whose timing_source is "interpolated" / "lrclib_line" or whose conf is <= 0.02. On real data the
conf test never fires: the word confidence in lyrics has a floor of 0.1 (``lyrics/core._word_conf``: an unaligned word
or a CTC score of 0 gives 0.1), so every emitted line has conf >= ~0.06. And forced alignment never leaves a supplied
line "interpolated": CTC (or the stable-ts fallback) always places the words somewhere, so the line is "ctc" or
"stable_ts".

Measured (out/_wip/r-ml-m3b-r5/karaoke): a 40 s synthetic song with NO voice (clicks, bass, saw lead) analysed end to end
with 8 user lyric lines (.txt). lyrics emitted 7 "ctc" lines (conf 0.12-0.30, grade D) and 1 "stable_ts" line
(conf 0.72), song grade D, 34.5 s of line coverage; vocals then logged "lyric coverage 34.5 s in 8 line(s) counted
as voice evidence". There the separator happened to put the saw lead in "other". When the synth lead lands in the
vocals stem (MEGAFAUNA's vocals stem is mostly synth leads; a karaoke or instrumental version with supplied lyrics),
those lines open the voice gate and the stage invents a singer. This test feeds exactly the measured lines.

Synthetic input only; RMVPE, SwiftF0 and CED run inside a heavy slot (about 30 s).
"""
from __future__ import annotations

import numpy as np
import pytest
from m3b_fakectx import FakeCtx, activity

SR = 44100
DUR = 40.0
# the lines lyrics emitted on the voiceless synthetic song (timing_source, t, d, conf, line grade); text omitted
MEASURED = [("ctc", 0.78, 10.24, 0.1234, "D"), ("ctc", 9.56, 5.5, 0.2584, "D"), ("ctc", 13.58, 5.4, 0.2473, "D"),
            ("ctc", 17.48, 3.18, 0.2604, "D"), ("ctc", 19.22, 5.9, 0.1851, "D"), ("ctc", 23.72, 3.28, 0.1994, "D"),
            ("ctc", 31.04, 4.99, 0.2975, "D"), ("stable_ts", 34.3, 4.42, 0.7238, "B")]


def _synth_lead() -> np.ndarray:
    """A band-limited sawtooth lead (15 harmonics) playing 0.5 s notes between A3 and A4, 4-36 s."""
    t = np.arange(int(DUR * SR)) / SR
    y = np.zeros_like(t)
    melody = [57, 59, 60, 62, 64, 65, 67, 69, 67, 65, 64, 62]
    for k, t0 in enumerate(np.arange(4.0, 36.0, 0.5)):
        f = 440.0 * 2 ** ((melody[k % len(melody)] - 69) / 12)
        i0, i1 = int(t0 * SR), int((t0 + 0.45) * SR)
        tt = t[i0:i1] - t0
        env = np.minimum(1.0, np.minimum(tt / 0.01, (0.45 - tt) / 0.02))
        y[i0:i1] += env * sum(np.sin(2 * np.pi * h * f * tt) / h for h in range(1, 16))
    return (0.15 * y / np.max(np.abs(y))).astype(np.float32)


@pytest.mark.real
def test_forced_aligned_lines_on_a_voiceless_song_do_not_make_a_singer():
    from mvh import stages  # noqa: F401
    from mvh.stages import vocals
    from mvh.testing import heavy

    lead = _synth_lead()
    voc = np.stack([lead, lead])
    n100 = int(DUR * 100)
    lines = [{"id": f"L{i + 1:03d}", "t": t, "d": d, "conf": c, "grade": g, "timing_source": ts, "backing": False,
              "n_words": 6} for i, (ts, t, d, c, g) in enumerate(MEASURED)]
    ctx = FakeCtx(
        vocals,
        {"mix": (voc, SR), "vocals": (voc, SR), "lead_vocals": (1e-5 * voc, SR)},
        curves={"stem.vocals.active": activity(n100, [(3.5, 36.5)]),
                "stem.lead_vocals.active": np.zeros(n100, np.float32),
                "inst.voice": np.zeros(int(DUR), np.float32)},  # the tagger hears no voice anywhere
        upstream={"lyrics": {"lyrics/lyrics.json": {"instrumental": False, "grade": "D", "lines": lines}},
                  "stem_activity": {"meta/stems.json": {"stems": {"vocals": {"present": False}}}}},
        events={"vocal_style": [], "beats": [], "bars": []},
    )
    with heavy("review-r-ml-m3b-r5", threads=3):
        vocals.run(ctx)
    vr = ctx.writer.json_docs["meta/vocal_range.json"]
    n_notes = len(ctx.writer.ev.get("notes.vocals", []))
    n_ph = len(ctx.writer.ev.get("vocal_phrases", []))
    print(f"present={vr['present']} voiced_s={vr['voiced_s']} p2={vr['p2']} p98={vr['p98']} notes={n_notes} phrases={n_ph}")
    assert vr["present"] is False, (
        f"forced-aligned (grade D) lines on a voiceless song turned a synth lead into a singer: voiced {vr['voiced_s']} s, "
        f"range p2 {vr['p2']} - p98 {vr['p98']}, {n_notes} vocal notes, {n_ph} phrases")
    assert vr["voiced_s"] < 2.0 and n_notes == 0 and n_ph == 0
