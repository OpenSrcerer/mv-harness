"""R-WORDS M5 round 5 (major, R4-1 not fully fixed): M5-D54 accepts lone 'Name:' candidates as speaker markers when
ONE of them recurs with different text after it, and that branch never applies the pronoun / verb check
(``_strict_name``) nor the Title Case guard that the other branch uses (``text._scan_labels``: ``recurring or
strict``). So a quote-introducing sung line that is used twice ('I said to John:' before two different quotes) or a
Title Case 'She Said:' refrain still deletes every colon-ending sung line in the file, the file becomes labelled, and
the deleted lyric text becomes the speaker_hint (voices then forces k = number of such lines and copies the text into
meta/voices.json voices[].hint). The R4-1 suggested fix asked for exactly this rejection of pronoun/verb candidates.

Synthetic text only (invented lines).
"""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import text as T

STORY = [
    "I said to John:",
    "you never come home at night",
    "walking down the road alone",
    "I said to John:",
    "carry me home again my friend",
    "I prayed to God:",
    "feeling every star in sight",
]
TITLE = [
    "She Said:",
    "Walking Down The Road Tonight",
    "He Said:",
    "Never Coming Back Again My Friend",
    "She Said:",
    "Carry Me Home Across The Water",
    "Down By The River Side Tonight",
]


def _lrc(lines):
    return "\n".join(f"[00:{10 + 3 * i:02d}.00]{t}" for i, t in enumerate(lines))


@pytest.mark.parametrize("lines,fmt", [(STORY, "txt"), (STORY, "lrc"), (TITLE, "txt"), (TITLE, "lrc")],
                         ids=["story_recurs_txt", "story_recurs_lrc", "titlecase_recurs_txt", "titlecase_recurs_lrc"])
def test_recurring_sung_colon_line_is_kept(lines, fmt):
    src = T.parse_txt("\n".join(lines)) if fmt == "txt" else T.parse_lrc(_lrc(lines))
    got = [ln["text"] for ln in src["lines"]]
    hints = sorted({ln["speaker"] for ln in src["lines"] if ln["speaker"]})
    assert len(got) == len(lines), (f"{len(lines) - len(got)} sung line(s) ending in ':' were deleted as speaker "
                                    f"markers ({len(got)} of {len(lines)} lines kept)")
    assert not hints, f"{len(hints)} lyric line(s) became speaker hints"


def test_guard_recurring_battle_markers_still_work():
    names = ["Bill Nye", "Isaac Newton", "Bill Nye", "Isaac Newton"]
    body = []
    for i, n in enumerate(names):
        body += [f"{n}:", f"verse line {i} one", f"verse line {i} two"]
    src = T.parse_txt("\n".join(body))
    assert [ln["speaker"] for ln in src["lines"]] == [n for n in names for _ in range(2)]
