"""R-WORDS M5 round 2 (major, finding B not fixed): one-off "Word: ..." lines still become speaker labels.

The fix (M5-D32) treats inline ``Name:`` prefixes as labels only in a "labelled" file: a label recurs or a header
names a speaker. ``text._file_labelled`` decides "a header names a speaker" with ``_header()``, which matches ANY
bracketed line and takes the text after a colon as the speaker. Standard LRC ID tags are bracketed lines with a
colon: ``[ar:Artist]``, ``[ti:Title]``, ``[al:Album]``, ``[by:Creator]``, ``[length: 03:45]``, ``[offset:+0]``,
``[re:Editor]``. Almost every user-supplied or embedded LRC file starts with them, so such a file is always
"labelled" and finding B is back unchanged: ``Time: it slips away`` loses its sung word ``Time``, the hint is
carried to the following lines, and two pseudo-labels give two distinct hints (voices: ``n_source = "hints"``,
k = 2, lines forced to voices regardless of the audio).

A second path to the same failure: a section header that is not in SECTION_WORDS by its first word, e.g.
``[Guitar Solo]`` or ``[Sax Break]``, is read as a speaker name (no colon needed), so a plain TXT with two such
headers carries two speaker hints.

Synthetic text only.
"""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import text as T

BODY = [
    "[00:01.00] Paper lanterns over the river",
    "[00:03.00] Time: it slips away from me",
    "[00:05.00] Carry the light",
    "[00:07.00] Mama: I am coming home",
    "[00:09.00] Copper bells along the harbor",
]
ID_TAGS = {
    "ar_ti_al_by": ["[ar:mv-harness fixture]", "[ti:Lanterns on the Tide]", "[al:Fixture]", "[by:someone]"],
    "ar_only": ["[ar:mv-harness fixture]"],
    "length": ["[length: 03:45]"],
    "offset": ["[offset:+0]"],
}


@pytest.mark.parametrize("tags", list(ID_TAGS), ids=list(ID_TAGS))
def test_lrc_id_tags_do_not_turn_one_off_colons_into_labels(tags):
    src = T.parse_lrc("\n".join(ID_TAGS[tags] + BODY))
    firsts = [ln["text"].split()[0] for ln in src["lines"]]
    hints = [ln["speaker"] for ln in src["lines"]]
    assert firsts[1].startswith("Time") and firsts[3].startswith("Mama"), (
        f"LRC ID tag(s) {tags} made the file 'labelled': sung words cut, lines now start {firsts}")
    assert len({h for h in hints if h}) < 2, f"pseudo-labels became speaker hints: {hints}"


def test_section_headers_are_not_speakers():
    txt = "\n".join(["[Guitar Solo]", "Paper lanterns over the river", "Carry the light",
                     "[Sax Break]", "Copper bells along the harbor", "Carry the light"])
    src = T.parse_txt(txt)
    hints = [ln["speaker"] for ln in src["lines"]]
    assert len({h for h in hints if h}) < 2, f"instrumental section headers became speaker hints: {hints}"


def test_guard_labelled_battle_with_id_tags_keeps_labels():
    lab = "\n".join(["[ar:mv-harness fixture]",
                     "[00:01.00] Newton: I am the one who wrote the laws",
                     "[00:03.00] you are a TV host",
                     "[00:05.00] Nye: Science rules the day",
                     "[00:07.00] Newton: Gravity holds you down"])
    src = T.parse_lrc(lab)
    assert [ln["speaker"] for ln in src["lines"]] == ["Newton", "Newton", "Nye", "Newton"]
