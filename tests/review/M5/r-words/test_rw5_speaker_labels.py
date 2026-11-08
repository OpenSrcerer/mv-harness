# ruff: noqa: E501
"""R-WORDS M5 (major): one-off "Word: ..." lyric lines are parsed as speaker labels.

``text._label_split`` accepts any capitalised word (up to 4) followed by ``": "`` as a speaker label unless it is
in a short stop list. In an otherwise unlabelled lyric file (the normal LRCLIB case: newton's and jeremy's entries
have no labels at all) a sung line such as ``Time: it slips away`` therefore

1. loses its first sung word: ``Time`` is cut from the line text, so it is never aligned, never exported and
   never reaches lyrics.json (silent lyric data loss);
2. sets ``speaker`` for that line AND every later line (the parsers carry the speaker forward until a header);
3. with two such lines (``Time:``, ``Mama:``) the lyrics carry two distinct ``speaker_hint`` values, and the voices
   stage switches to ``n_source = "hints"`` with k = 2 and forces every hinted line to the hint's voice, overriding
   the acoustic clustering (voices/core.py: ``elif len(hints) >= 2``), i.e. a one-singer song is split in two voices
   at the first pseudo-label.

Labelled sources ("Newton: ...", "[Verse 1: Nye]") must keep working; the fix must tell a one-off colon in a lyric
line from a label (e.g. accept inline labels only when the file is labelled: a label recurs or headers name
speakers, or confirm against the ASR that the label word is not sung at the line start).
Synthetic text only.
"""
from __future__ import annotations

from mvh.stages.lyrics import text as T

UNLABELLED = "\n".join([
    "[00:01.00] Paper lanterns over the river",
    "[00:03.00] Time: it slips away from me",
    "[00:05.00] Carry the light",
    "[00:07.00] Mama: I am coming home",
    "[00:09.00] Copper bells along the harbor",
])


def test_one_off_colon_lines_keep_their_sung_words():
    src = T.parse_lrc(UNLABELLED)
    texts = [ln["text"] for ln in src["lines"]]
    # every sung word of the file must survive the parse
    assert "Time" in texts[1].split()[0], f"first word of line 2 was cut: now starts {texts[1].split()[0]!r}"
    assert "Mama" in texts[3].split()[0], f"first word of line 4 was cut: now starts {texts[3].split()[0]!r}"


def test_one_off_colon_lines_do_not_create_speaker_hints():
    src = T.parse_lrc(UNLABELLED)
    hints = [ln["speaker"] for ln in src["lines"]]
    # two distinct pseudo-labels -> two hints -> voices would force k = 2 from them
    assert len({h for h in hints if h}) < 2, f"pseudo-labels became speaker hints: {hints}"


def test_real_labels_still_parse():
    """Guard for the fix: a labelled battle keeps its labels."""
    lab = "\n".join([
        "[00:01.00] Newton: I am the one who wrote the laws",
        "[00:03.00] you are a TV host",
        "[00:05.00] Nye: Science rules the day",
        "[00:07.00] Newton: Gravity holds you down",
    ])
    src = T.parse_lrc(lab)
    assert [ln["speaker"] for ln in src["lines"]] == ["Newton", "Newton", "Nye", "Newton"]
    assert src["lines"][0]["text"].startswith("I am")
