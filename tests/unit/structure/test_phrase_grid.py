"""Phrase layout (F7-r4, made local by F8-r5): a section that is not a whole number of phrases puts its remainder
first (a pickup phrase) only on its own evidence: its start was snapped back to an impact, or the boundary evidence at
the pickup end beats the evidence where a trailing remainder would start. Other sections never vote."""
import numpy as np

from mvh.stages.structure import phrase_layout


def _starts(layout):
    return [(k, e) for k, e, _ in layout]


def test_snapped_section_gets_a_leading_pickup_phrase():
    # verse snapped one bar back to an impact (8 instead of 9): 9 bars
    ranges = [(0, 8), (8, 17), (17, 25), (25, 33), (33, 41)]
    lay = phrase_layout(ranges, 8, lead={1})
    verse = [(k, e) for k, e, i in lay if i == 1]
    assert verse == [(8, 9), (9, 17)]
    # the other sections are whole phrases, untouched
    assert [(k, e) for k, e, i in lay if i != 1] == [(0, 8), (17, 25), (25, 33), (33, 41)]


def test_no_evidence_keeps_the_remainder_at_the_end():
    ranges = [(0, 8), (8, 17), (17, 25), (25, 33), (33, 41)]
    assert [(k, e) for k, e, i in phrase_layout(ranges, 8) if i == 1] == [(8, 16), (16, 17)]
    ranges = [(0, 8), (8, 16), (16, 25), (25, 33)]
    assert [(k, e) for k, e, i in phrase_layout(ranges, 8) if i == 2] == [(16, 24), (24, 25)]


def test_whole_phrases_and_short_sections_unchanged():
    ranges = [(0, 4), (4, 12), (12, 18), (18, 26)]
    lay = phrase_layout(ranges, 8)
    assert _starts(lay) == [(0, 4), (4, 12), (12, 18), (18, 26)]


def test_local_evidence_decides_and_other_sections_do_not_vote():
    # a 12-bar section (phrase 8): strong boundary evidence at bar 12 (a + 4), none at bar 16 (b - 4) -> pickup first
    ev = np.zeros(60)
    ev[12] = 1.0
    ranges = [(0, 8), (8, 20), (20, 28), (28, 36), (36, 44)]
    assert [(k, e) for k, e, i in phrase_layout(ranges, 8, evidence=ev, margin=0.3) if i == 1] == [(8, 12), (12, 20)]
    # the same section with more (or fewer) sections elsewhere in the song: same phrasing
    for other in ([(0, 8), (8, 20), (20, 28)], [(0, 8), (8, 20), (20, 28), (28, 32), (32, 36), (36, 44), (44, 52)]):
        assert [(k, e) for k, e, i in phrase_layout(other, 8, evidence=ev, margin=0.3) if i == 1] == [(8, 12), (12, 20)]
    # evidence at the trailing position instead (a stop bar at b - 4) -> the remainder closes the section
    ev2 = np.zeros(60)
    ev2[16] = 1.0
    assert [(k, e) for k, e, i in phrase_layout(ranges, 8, evidence=ev2, margin=0.3) if i == 1] == [(8, 16), (16, 20)]
