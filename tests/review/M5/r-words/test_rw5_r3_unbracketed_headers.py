# ruff: noqa: E501
"""R-WORDS M5 round 3 (major, new): unbracketed section headers in user-supplied / embedded plain-text lyrics become
SUNG lyric lines.

``text.parse_txt`` recognises a section header only in brackets (``_HEADER_RE``: ``[...]`` / ``{...}``). The other
common ways lyric files mark sections are read as lyrics:

* ``Verse 1:`` / ``Chorus:`` / ``Bridge:`` alone on a line (``_LABEL_RE`` needs text after the colon, and section words
  are excluded from labels anyway), ``VERSE 1`` / ``CHORUS`` in capitals, ``Chorus x2`` (the repeat parser turns it
  into TWO lyric lines "Chorus"), and ``(Chorus)`` (becomes a BACKING lyric line instead of re-inserting the chorus).

End-to-end on the synthetic song (out/_wip/r-words-m5-r3/synth-plainhdr and synth-capshdr, the truth lyrics with
such headers): lyrics grade A, coverage 0.91, NO warning, 14 lines / 58 words where the song has 10 lines / 53 words.
"Verse 1:" is placed at 9.0 s, "Chorus:" at 16.92 s, "Bridge:" at 24.0 s, "(Chorus)" at 29.76 s; all four are written
to lyrics.json (words with times), lyrics.srt / .lrc / .vtt / .ass captions and they open the mouth gate. The gate
G1-G8 does not notice five phantom words among 58.

Synthetic text only.
"""
from __future__ import annotations

import re

import pytest

from mvh.stages.lyrics import text as T

BODY_V = ["Paper lanterns over the river", "Carry the light"]
BODY_C = ["We are the echo of the morning", "We will rise when the tide comes in"]
SECTION = re.compile(r"^\(?\s*(verse|chorus|bridge|pre-chorus|hook|intro|outro)\b\s*\d*\s*:?\s*(x\s*\d)?\s*\)?$", re.I)

CASES = {
    "colon": ["Verse 1:", *BODY_V, "Chorus:", *BODY_C, "Bridge:", "Hold your breath"],
    "caps": ["VERSE 1", *BODY_V, "CHORUS", *BODY_C, "BRIDGE", "Hold your breath"],
    "chorus_x2": ["Verse 1", *BODY_V, "Chorus x2", *BODY_C],
    "paren_chorus": ["[Verse 1]", *BODY_V, "[Chorus]", *BODY_C, "[Verse 2]", "Copper bells along the harbor", "(Chorus)"],
}


@pytest.mark.parametrize("name", list(CASES), ids=list(CASES))
def test_unbracketed_section_headers_are_not_sung_lines(name):
    src = T.parse_txt("\n".join(CASES[name]))
    texts = [ln["text"] for ln in src["lines"]]
    phantom = [t for t in texts if SECTION.match(t.strip())]
    assert not phantom, f"{name}: section headers became {len(phantom)} lyric line(s) {phantom} out of {len(texts)}"


def test_paren_chorus_reinserts_the_chorus():
    src = T.parse_txt("\n".join(CASES["paren_chorus"]))
    texts = [ln["text"] for ln in src["lines"]]
    assert texts.count(BODY_C[0]) == 2, f"'(Chorus)' did not re-insert the chorus: {texts}"


def test_guard_sung_line_starting_with_a_section_word_is_kept():
    src = T.parse_txt("Chorus of angels singing in the night\nVerses written on the wall")
    assert [ln["text"] for ln in src["lines"]] == ["Chorus of angels singing in the night", "Verses written on the wall"]
