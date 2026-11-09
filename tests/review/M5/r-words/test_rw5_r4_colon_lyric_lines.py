"""R-WORDS M5 round 4 (major, regression of the R3-3 fix M5-D47): a SUNG lyric line that ends with a colon and
starts and ends with a capitalised word is now read as a speaker marker ('Bill Nye:' rule in
``text._plain_header``). The line is deleted from the lyrics, the file becomes "labelled" at once
(``_file_labelled``: an explicit marker), and every following line carries the deleted lyric text as its
``speaker_hint``.

Consequences: sung words silently disappear from lyrics.json, the exports and the mouth gate; with two such lines
voices takes ``n_source = "hints"`` and forces k = 2 on a one-singer song (voices/core.py: ``len(hints) >= 2``); and
the lyric text is copied into ``meta/voices.json voices[].hint`` (outside lyrics/*, NF5). It also hits the
PRIMARY source: LRCLIB synced lyrics go through ``parse_lrc`` -> ``_header`` -> ``_plain_header`` too.

Lines that introduce a quote end with a colon ('I said to John:', 'I prayed to God:'); Title Case lyric files
(common in embedded tags) make every such line qualify ('Tell Me Why:' is protected only in sentence case).

Synthetic text only (invented lines).
"""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import text as T

STORY = [
    "I said to John:",
    "you never come home at night",
    "walking down the road alone",
    "I prayed to God:",
    "carry me home again my friend",
    "feeling every star in sight",
]
TITLE = [
    "Here We Go Again:",
    "Walking Down The Road Tonight",
    "Tell Me Why:",
    "Down By The River Side",
]


def _lrc(lines):
    return "\n".join(f"[00:{10 + 3 * i:02d}.00]{t}" for i, t in enumerate(lines))


@pytest.mark.parametrize("lines,fmt", [(STORY, "txt"), (STORY, "lrc"), (TITLE, "txt"), (TITLE, "lrc")],
                         ids=["story_txt", "story_lrc_synced", "titlecase_txt", "titlecase_lrc_synced"])
def test_sung_line_ending_in_colon_is_kept(lines, fmt):
    src = T.parse_txt("\n".join(lines)) if fmt == "txt" else T.parse_lrc(_lrc(lines))
    got = [ln["text"] for ln in src["lines"]]
    hints = sorted({ln["speaker"] for ln in src["lines"] if ln["speaker"]})
    assert len(got) == len(lines), (f"{len(lines) - len(got)} sung line(s) ending in ':' were deleted as speaker "
                                    f"markers ({len(got)} of {len(lines)} lines kept)")
    assert not hints, f"{len(hints)} lyric line(s) became speaker hints (voices forces k = {len(hints)})"


def test_guard_battle_marker_still_works():
    # a battle: the performer markers recur (each rapper has two verses)
    names = ["Bill Nye", "Isaac Newton", "Bill Nye", "Isaac Newton"]
    body = []
    for i, n in enumerate(names):
        body += [f"{n}:", f"verse line {i} one", f"verse line {i} two"]
    src = T.parse_txt("\n".join(body))
    assert [ln["speaker"] for ln in src["lines"]] == [n for n in names for _ in range(2)]
