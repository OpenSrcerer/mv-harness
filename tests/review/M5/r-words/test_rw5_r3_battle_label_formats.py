"""R-WORDS M5 round 3 (major, new): two common speaker-label formats of user-supplied lyrics lose the labels.

The rap battle (3 rappers + an announcer) is M5's stress test, and speaker labels in the lyrics source are the
only way voices gets the per-line voice from the text (``n_source = "hints"``, D3 ``speaker_hint``); the
embedding estimate is only a lower bound (SPIKE §6).

1. ``[Name:]`` (bracketed name with a trailing colon, the performer marker of AZLyrics-style and wiki-style lyric
   pages): ``text._header`` splits on the colon and takes the TEXT AFTER it as the speaker. That text is empty, so
   the speaker is None; the header is dropped and no line carries a hint. A battle written this way gets no
   speaker hints at all.
2. ``Name:`` alone on its own line (the speaker on one line, the verse below): ``_LABEL_RE`` needs text after the
   colon, so the line is not a label. It becomes a LYRIC line: the performer's name is aligned to the audio as sung
   words, enters lyrics.json and the exports, and counts in G1-G4 and the mouth gate.

Synthetic text only (character names, invented verse lines).
"""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import text as T

NAMES = ["Announcer", "Sir Isaac Newton", "Bill Nye", "Sir Isaac Newton", "Bill Nye", "Neil deGrasse Tyson"]


def _battle(shape: str) -> str:
    body = []
    for i, n in enumerate(NAMES):
        body += [shape.format(n=n), f"verse line {i} one", f"verse line {i} two"]
    return "\n".join(body)


@pytest.mark.parametrize("shape", ["[{n}:]", "{n}:"], ids=["bracket_name_colon", "name_colon_line"])
def test_battle_speaker_markers_become_hints(shape):
    src = T.parse_txt(_battle(shape))
    texts = [ln["text"] for ln in src["lines"]]
    hints = [ln["speaker"] for ln in src["lines"]]
    assert len(texts) == 2 * len(NAMES), (f"{len(texts) - 2 * len(NAMES)} speaker-marker line(s) became sung lyric lines "
                                          f"({len(texts)} lines for {2 * len(NAMES)} verse lines)")
    assert hints == [n for n in NAMES for _ in range(2)], f"speaker hints lost: {hints}"


def test_guard_bracket_name_without_colon_works():
    src = T.parse_txt(_battle("[{n}]"))
    assert [ln["speaker"] for ln in src["lines"]] == [n for n in NAMES for _ in range(2)]
