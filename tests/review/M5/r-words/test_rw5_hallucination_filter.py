"""R-WORDS M5 (major): the Whisper hallucination filter keeps the best-known large-v3 hallucinations.

``asr.filter_segments`` matches ``thanks for watching``, ``subscribe``, ``amara.org`` and bracketed tags, but not
the equally common Whisper outputs ``Thank you for watching.``, ``Transcribed by https://otter.ai`` or
``Copyright WDR 2021`` (subtitle credits from the training data, emitted with high word probability on music,
reverb tails and stem bleed). The SPIKE notes the filter was never tested against a real hallucination.

Impact: on the transcription path every kept segment becomes a lyric line; with a supplied text, a kept segment of
>= 3 words after the last (or before the first) lyric line with p >= 0.6 is ADDED to lyrics.json as an
``asr_only`` line (core._expansion), and voices then embeds it as its own item (an "announcer"-like extra voice).
Synthetic segments: active vocals everywhere (the activity mask cannot help), confident words (p = 0.9).
"""
from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import asr as R

HALLUCINATIONS = [
    "Thank you for watching.",
    "Thank you for watching!",
    "Transcribed by https://otter.ai",
    "Copyright WDR 2021",
]


def _seg(text: str, p: float = 0.9, t0: float = 200.0) -> dict:
    ws = text.split()
    return {"start": t0, "end": t0 + 0.4 * len(ws), "text": " " + text, "avg_logprob": -0.2, "no_speech_prob": 0.1,
            "compression_ratio": 1.2,
            "words": [{"w": " " + w, "start": t0 + 0.4 * i, "end": t0 + 0.4 * i + 0.35, "p": p} for i, w in enumerate(ws)]}


@pytest.mark.parametrize("text", HALLUCINATIONS)
def test_known_whisper_hallucinations_are_dropped(text):
    act = np.ones(30000, np.float32)
    kept, dropped = R.filter_segments([_seg(text)], act, 100.0, min_word_p=0.25)
    assert not kept, f"hallucination kept by the filter (drops: {dropped})"


def test_ordinary_lyric_lines_survive():
    """Guard for the fix: plain lyric-like segments are kept."""
    act = np.ones(30000, np.float32)
    kept, _ = R.filter_segments([_seg("Paper lanterns over the river"), _seg("Carry the light", t0=210.0)], act, 100.0)
    assert len(kept) == 2
