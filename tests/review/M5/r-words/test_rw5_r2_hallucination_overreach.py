# ruff: noqa: E501
"""R-WORDS M5 round 2 (major, regression from the C fix): the extended hallucination filter deletes sung lyrics.

M5-D33 extended ``asr.NONLYRIC`` with YouTube-outro patterns that are matched with ``re.search`` anywhere in a
segment's text and drop the WHOLE segment, whatever its position, vocal activity or word confidence:
``see you (in the) next``, ``please (like|share)``, ``copyright``, ``.com``, and whole-segment ``bye ...`` /
``goodbye`` / ``thank you``. These are ordinary lyric phrases ("I'll see you in the next life", a chanted
"bye bye bye" hook, "please share your light with me"). Whisper segments on sung vocals hold one or two lines, so
each hit silently removes those lines from the ASR evidence: on the transcription path (no LRCLIB / embedded /
user text) they disappear from lyrics.json, the exports, voices and the mouth gate; with a supplied untimed text
they are missing as anchors and from the match score (G1) and agreement (G7).

The known hallucinations should still be dropped (guard below); the fix must not do it by phrase alone in the
middle of active vocals (e.g. only at the very start / end of the audio, outside vocal activity, with high
no_speech_prob, or for the specific credit strings).
Synthetic text only.
"""
from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import asr as R

LYRICS = [
    "I will see you in the next life",
    "please share your light with me tonight",
    "Bye bye bye",
    "see you next time across the water",
]
HALLUCINATIONS = ["Thank you for watching.", "Transcribed by https://otter.ai", "Copyright WDR 2021"]


def _seg(text: str, t0: float = 20.0) -> dict:
    ws = text.split()
    return {"start": t0, "end": t0 + 0.4 * len(ws), "text": " " + text, "avg_logprob": -0.2, "no_speech_prob": 0.05,
            "compression_ratio": 1.2,
            "words": [{"w": " " + w, "start": t0 + 0.4 * i, "end": t0 + 0.4 * i + 0.3, "p": 0.9} for i, w in enumerate(ws)]}


@pytest.mark.parametrize("text", LYRICS, ids=[f"lyric{i}" for i in range(len(LYRICS))])
def test_sung_lines_mid_song_are_kept(text):
    active = np.ones(6000, np.float32)            # 60 s of active lead vocals
    kept, dropped = R.filter_segments([_seg(text)], active, 100.0, 0.25)
    assert kept, f"a confident sung segment at 20 s inside active vocals was dropped as {dropped}"


@pytest.mark.parametrize("text", HALLUCINATIONS, ids=["thanks_watching", "otter", "copyright_wdr"])
def test_guard_known_hallucinations_still_dropped(text):
    kept, _ = R.filter_segments([_seg(text, 50.0)], np.ones(6000, np.float32), 100.0, 0.25)
    assert not kept
