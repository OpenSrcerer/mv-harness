# ruff: noqa: E501
"""R-WORDS M5 round 3 (major, R2-3 only partly fixed): the "second signal" that lets a generic outro phrase drop a
whole segment fires on about half of the genuinely sung, confident segments of real songs.

M5-D37 drops a segment that contains ``see you (in the) next``, ``please like/share``, bare ``bye bye`` /
``goodbye`` / ``thank you`` when ``asr._generic_suspect`` finds a second signal. The first test is
``no_speech_prob > 0.4``. faster-whisper's no_speech_prob is computed once per 30 s decoding window and is high
on singing: on the cached W0 whisper output (tests/.cache/real/<slug>/whisper_cpu, counts only) the CONFIDENT
segments (mean word p >= 0.8, avg_logprob > -0.5) have no_speech_prob > 0.4 in 11 of 25 on jeremy (values 0.67 and
0.78) and 21 of 48 on newton-vs-nye (0.42); over all kept segments ``_generic_suspect`` fires (without any
activity mask) on 15 of 30 (jeremy) and 27 of 62 (newton). The general filter itself only trusts no_speech_prob
together with a low logprob (``no_speech > 0.8 and avg_logprob < -1``).

So a confident sung "bye bye bye" hook or "I will see you in the next life" in the middle of active vocals is
still dropped as ``non_lyric_tag`` whenever its 30 s window happens to carry jeremy's or newton's no_speech value.
The round-2 test passed only because it used no_speech_prob 0.05, which real sung segments rarely have.

Segment statistics below are the real values quoted above; the text is synthetic.
"""
from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import asr as R

LYRICS = ["I will see you in the next life", "Bye bye bye", "please share your light with me tonight"]
REAL_NO_SPEECH = {"jeremy_window": 0.67, "newton_window": 0.42 + 0.005}


def _seg(text: str, no_speech: float, t0: float = 60.0) -> dict:
    ws = text.split()
    return {"start": t0, "end": t0 + 0.4 * len(ws), "text": " " + text, "avg_logprob": -0.3, "no_speech_prob": no_speech,
            "compression_ratio": 1.2,
            "words": [{"w": " " + w, "start": t0 + 0.4 * i, "end": t0 + 0.4 * i + 0.3, "p": 0.9} for i, w in enumerate(ws)]}


@pytest.mark.parametrize("ns", list(REAL_NO_SPEECH), ids=list(REAL_NO_SPEECH))
@pytest.mark.parametrize("text", LYRICS, ids=["next_life", "bye", "please_share"])
def test_confident_sung_line_with_real_song_no_speech_is_kept(text, ns):
    active = np.ones(18000, np.float32)            # 180 s of active lead vocals
    kept, dropped = R.filter_segments([_seg(text, REAL_NO_SPEECH[ns])], active, 100.0, 0.25)
    assert kept, (f"a confident (p 0.9, logprob -0.3) segment at 60 s inside active vocals, with the no_speech_prob "
                  f"whisper gives sung windows ({REAL_NO_SPEECH[ns]}), was dropped as {dropped}")


def test_guard_plain_lyric_with_same_stats_is_kept():
    kept, _ = R.filter_segments([_seg("paper lanterns over the river", 0.67)], np.ones(18000, np.float32), 100.0, 0.25)
    assert kept


def test_guard_credit_string_still_dropped():
    kept, _ = R.filter_segments([_seg("Thank you for watching", 0.67)], np.ones(18000, np.float32), 100.0, 0.25)
    assert not kept
