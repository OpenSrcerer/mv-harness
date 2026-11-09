"""R-WORDS M5 round 3 (major, R2-1 only partly fixed): section headers and repeated chorus lines still become
speaker labels.

The R2-1 fix (M5-D35) stops LRC ID tags and bare headers with an instrumental word ([Guitar Solo]) from naming a
speaker. Two paths remain:

1. ``text._header`` recognises a section only by the header's FIRST word (``low.startswith(SECTION_WORDS)``). A bare
   multi-word header whose section word comes second is read as a speaker name: ``[Pre Chorus]`` (written without
   the hyphen), ``[Post Chorus]``, ``[Final Chorus]``, ``[Last Chorus]``, ``[Rap Verse]``, ``[Second Verse]``. Such a
   header usually recurs (a pre-chorus comes back), so ``_file_labelled`` counts it as a recurring bare ``[Name]``
   header and marks the file labelled. Every following line then carries the hint ``Pre Chorus`` / ``Post Chorus``;
   two of them are two distinct hints, so voices switches to ``n_source = "hints"`` and forces k = 2, assigning
   lines to "voices" by song section for a one-singer song. A one-off ``Time: ...`` line also loses its sung word.

2. A sung line that starts with ``Word:`` and is written out each time the chorus comes back counts as a
   "recurring label" (the same label twice), so the file is labelled and the sung word ``Time`` is cut from every
   chorus (lyrics text, words, alignment, mouth gate) and carried as a speaker hint to the following lines.
   The round-2 evidence named this case; the D35 rule ("a name recurs (>= 2) among inline labels") still accepts it
   although both occurrences prefix the SAME text (a repeated lyric, not a speaker turn).

Synthetic text only.
"""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import text as T

SECTION_TXT = "\n".join([
    "[Verse 1]", "Paper lanterns over the river", "Copper bells along the harbor",
    "[Pre Chorus]", "Hold the rope and pull it in", "Time: it slips away from me",
    "[Chorus]", "Carry the light", "Carry the light",
    "[Post Chorus]", "Ooh the tide is turning", "Lanterns on the tide",
    "[Verse 2]", "Salt upon the window", "Mama I am coming home",
    "[Pre Chorus]", "Hold the rope and pull it in", "Wind along the water",
    "[Chorus]", "Carry the light", "Carry the light",
    "[Post Chorus]", "Ooh the tide is turning", "Lanterns on the tide",
])


def test_bare_multiword_section_headers_are_not_speakers():
    src = T.parse_txt(SECTION_TXT)
    hints = sorted({ln["speaker"] for ln in src["lines"] if ln["speaker"]})
    assert not hints, (f"section headers became speaker hints {hints}: with >= 2 distinct hints voices forces "
                       f"k = {len(hints)} (n_source 'hints') on a one-singer song")


def test_one_off_colon_line_keeps_its_word_next_to_section_headers():
    src = T.parse_txt(SECTION_TXT)
    firsts = [ln["text"].split()[0] for ln in src["lines"]]
    assert "Time:" in firsts or "Time" in firsts, "the sung word 'Time' was cut as a speaker label"


@pytest.mark.parametrize("header", ["[Final Chorus]", "[Rap Verse]", "[Last Chorus]"])
def test_other_section_headers_are_sections(header):
    is_h, speaker, _sec, _rep = T._header(header, bare=True)
    assert is_h and speaker is None, f"{header} is read as speaker {speaker!r}"


def test_repeated_chorus_line_with_colon_keeps_its_word():
    txt = "\n".join(["[Chorus]", "Time: it slips away", "Carry the light",
                     "[Verse 2]", "Copper bells along the harbor", "Salt upon the window",
                     "[Chorus]", "Time: it slips away", "Carry the light"])
    src = T.parse_txt(txt)
    firsts = [ln["text"].split()[0] for ln in src["lines"]]
    hints = [ln["speaker"] for ln in src["lines"]]
    assert firsts[0].startswith("Time") and firsts[4].startswith("Time"), (
        f"a chorus line written out twice became a recurring 'label': lines now start {firsts}, hints {hints}")


def test_guard_battle_labels_with_varied_text_still_count():
    txt = "\n".join(["[Verse 1: Newton]", "I wrote the laws", "[Verse 2: Nye]", "Science rules",
                     "Newton: Gravity holds you down", "Nye: Bow ties forever"])
    src = T.parse_txt(txt)
    assert [ln["speaker"] for ln in src["lines"]] == ["Newton", "Nye", "Newton", "Nye"]
