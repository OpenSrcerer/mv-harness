"""R-WORDS M5 round 2 (major): the ASR repair moves a correctly placed word onto the next line's audio.

Finding D was fixed in ``align.align_groups`` (re-alignment clipped to the neighbouring lines), but
``core._asr_repair`` has the same flaw and its acceptance bar was lowered by the A fix (M5-D30: accept when the new
score is >= max(0.05, min(0.5 x old, 0.10)), i.e. at most 0.10 whatever the old placement scored). The repair
pairs supplied words with ASR words by LCS. When the ASR misses a word that the next line repeats (anadiplosis:
"... carry the light / light the lanterns ..."; a dropped word is common on processed vocals), LCS pairs the
earlier line's word with the ASR word of the LATER occurrence. The repair then re-aligns the word alone in a window
around that ASR time; the window is clipped only by the same line's words and by the line's synced bounds
(start - 2.5 s .. next line start + 2.5 s), never by the neighbouring line's placement. The word therefore lands
on the next line's first word: two lines claim the same audio and the lines interleave. The crossing check and its
warning (``alignment.notes.crossings_left``) run BEFORE the repair, so nothing reports it.

Deterministic construction on hand-made log-probabilities (no model): line A "carry the light" sung at 2.0/2.4/
2.8 s, line B "light the lanterns" at 5.0/5.4/5.8 s, LRC starts 2.0 / 5.0 s. align_groups places every word
correctly; the ASR heard every word except A's "light".
"""
from __future__ import annotations

import numpy as np

from mvh.stages.lyrics import align as A
from mvh.stages.lyrics import core as C

# token ids: 0 blank, 1 carry, 2 the, 3 light, 4 lanterns
SUNG = [(100, 1), (120, 2), (140, 3), (250, 3), (270, 2), (290, 4)]


def _logp(n_frames: int = 500) -> np.ndarray:
    p = np.full((n_frames, 5), 0.005)
    p[:, 0] = 0.98
    for f, tok in SUNG:
        p[f] = 0.01
        p[f, tok] = 0.96
    p /= p.sum(1, keepdims=True)
    return np.log(p).astype(np.float32)


def _lines():
    mk = lambda words, toks, t: {"words": words, "toks": toks, "wres": [None] * len(words), "src_t": t}  # noqa: E731
    return [mk(["carry", "the", "light"], [[1], [2], [3]], 2.0), mk(["light", "the", "lanterns"], [[3], [2], [4]], 5.0)]


def _asr():
    w = lambda n, t: {"n": n, "start": t, "end": t + 0.3, "p": 0.9}  # noqa: E731
    return [w("carry", 2.0), w("the", 2.4), w("light", 5.0), w("the", 5.4), w("lanterns", 5.8)]


def _run():
    logp = _logp()
    lines = _lines()
    starts, ends = [2.0, 5.0], [5.0, 8.0]
    res, notes = A.align_groups(logp, starts, ends, [x["toks"] for x in lines])
    for x, r in zip(lines, res):
        x["wres"] = r
    before = [[round(r["start"], 2) for r in x["wres"]] for x in lines]
    slack = 2.5
    n = C._asr_repair(lines, _asr(), logp, bounds=[(s - slack, e + slack) for s, e in zip(starts, ends)])
    after = [[round(r["start"], 2) for r in x["wres"]] for x in lines]
    return before, after, n, notes


def test_guard_group_alignment_is_correct():
    before, _after, _n, notes = _run()
    assert before == [[2.0, 2.4, 2.8], [5.0, 5.4, 5.8]], before
    assert notes.crossings_left == 0


def test_asr_repair_does_not_move_a_word_onto_the_next_line():
    before, after, n, _ = _run()
    a_end, b_start = after[0][-1], after[1][0]
    assert a_end < b_start, (f"ASR repair moved {n} word(s): line A's last word now starts at {a_end:.2f} s, on line B's "
                             f"first word ({b_start:.2f} s); before the repair it was at {before[0][-1]:.2f} s")
