"""R-WORDS M5 (major): the per-line window constraint re-aligns a line onto audio its neighbour already holds.

``align.align_groups`` re-aligns a line alone in [expected - slack, next expected + slack] when its first word lands
more than ``slack`` (2.5 s) from the expected start, and keeps the result when the line's mean token score improves.
It never checks the neighbouring lines, so with repeated text (choruses, Jeremy's line repeated 8 times) the line is
moved onto the audio of the previous line: both lines then claim the same words.

Real evidence (jeremy, LRCLIB 22859144, this stage's own run, times only): ``align_groups`` reports 2 re-aligned /
2 accepted lines; lines L037 and L039 come out with word starts identical to words of L036 / L038 (204.12 and
208.20 s; 210.26 s), L037 starts 2.1 s before its LRCLIB time, L036/L037 and L038/L039 interleave, and the song still
grades B (G5 0.875). Combined with the group-tail spill (test_rw5_alignment_synth.py) jeremy has 4 interleaving line
pairs and a 9.44 s word (L033.03).

Here: a deterministic two-line construction on hand-made log-probabilities (no model). Line A ("x y") is sung
strongly at 4.0 s, line B (the same text, a repeat) weakly at 8.7 s; expected starts 3.0 and 6.0 s. The group pass
places both correctly; B is 2.7 s from its expected start, so it is re-aligned alone in [3.5, 9.5] s and snaps onto
A's audio (higher score), duplicating A's word times.
"""
from __future__ import annotations

import numpy as np

from mvh.stages.lyrics import align as A


def _logp(n_frames: int = 600) -> np.ndarray:
    p = np.full((n_frames, 3), 0.01)
    p[:, 0] = 0.98                              # blank everywhere
    for f, tok, q in ((200, 1, 0.95), (202, 2, 0.95), (435, 1, 0.4), (437, 2, 0.4)):
        p[f] = (1 - q) / 2
        p[f, tok] = q
    p /= p.sum(1, keepdims=True)
    return np.log(p).astype(np.float32)


def test_group_pass_alone_places_both_lines():
    """Sanity: with the constraint out of reach (huge slack) both lines sit on their own audio."""
    res, _ = A.align_groups(_logp(), [3.0, 6.0], [5.0, 7.0], [[[1], [2]], [[1], [2]]], slack=99.0)
    assert abs(res[0][0]["start"] - 4.0) < 0.05 and abs(res[1][0]["start"] - 8.7) < 0.05


def test_line_constraint_does_not_duplicate_the_previous_line():
    res, notes = A.align_groups(_logp(), [3.0, 6.0], [5.0, 7.0], [[[1], [2]], [[1], [2]]])
    a_end = max(r["end"] for r in res[0])
    b_start = min(r["start"] for r in res[1])
    assert b_start >= a_end, (f"line B re-aligned onto line A's audio: A ends {a_end:.2f} s, B starts {b_start:.2f} s "
                              f"(re-aligned {notes.line_realigned}, accepted {notes.line_realign_accepted})")
