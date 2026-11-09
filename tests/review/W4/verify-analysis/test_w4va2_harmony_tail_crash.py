"""W4V2-HARMONY-NAN (M4, w4verify-analysis-r2): harmony crashes on a valid song when a chord segment starts at or after
the last chroma frame.

Found end to end: the synthetic song at 1.05x tempo (ffmpeg ``atempo=1.05``, 53.82 s;
out/_wip/w4verify-analysis-r2/synth_tempo105) ends with a 2 ms trailing 'N' segment [53.820, 53.822) after the last
chroma frame (53.812 s). ``chords.verify_segments`` takes ``cf.energy[a:max(b, a + 1)].mean()`` with a = b = the frame
count: an empty slice, so the mean is NaN, the 'N' conf is NaN, and ``ctx.writer.events('chords', ...)`` raises
``ValueError: Out of range float values are not JSON compliant: nan``. harmony fails, and structure, lyrics, mood,
vocals, choreo, cues, voices, lipsync, meaning, brief and viewer are not run (analyze rc 1). It is not the W4-AN-9
level change: harmony with ``analysis_lufs = null`` fails the same way on that cache.

Fast, synthetic, no models.
"""

from __future__ import annotations

import math

import numpy as np


def _cf(n_frames: int = 200, fps: float = 100.0):
    from mvh.stages.harmony.chroma import ChromaFrames

    rng = np.random.default_rng(3)
    chroma = rng.random((12, n_frames)) + 0.1
    chroma[[9, 0, 4], :] += 3.0                      # an A minor-ish frame set
    energy = np.full(n_frames, 0.5) + 0.1 * rng.random(n_frames)
    times = np.arange(n_frames) / fps
    return ChromaFrames(chroma=chroma, bass=chroma.copy(), energy=energy, times=times, tuning=0.0)


def test_w4va2_a_trailing_segment_after_the_last_chroma_frame_gets_a_finite_conf():
    from mvh.stages.harmony.chords import Seg, verify_segments

    cf = _cf()
    last = float(cf.times[-1])
    segs = [Seg(t=0.0, d=last - 0.5, root=9, quality="min", label="A:min"),
            Seg(t=last - 0.5, d=0.5 + 0.008, root=None, quality="N", label="N"),
            Seg(t=last + 0.008, d=0.002, root=None, quality="N", label="N")]   # the 2 ms tail past the last frame
    verify_segments(segs, cf, None, None)
    confs = [s.conf for s in segs]
    assert all(math.isfinite(c) for c in confs), f"chord conf not finite for a segment past the last chroma frame: {confs}"
