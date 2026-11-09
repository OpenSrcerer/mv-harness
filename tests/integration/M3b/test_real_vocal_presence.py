"""Seam S04 (M3b, with M3a): MEGAFAUNA has a processed lead voice. lyrics aligns 14 lines from the embedded text,
voices finds V1, and meaning and the brief give it a character that sings, but meta/vocal_range.json (vocals) says
present=false, there are no vocal phrases or vocal notes, and meta/stems.json marks the vocals unconfirmed. The
modules disagree about whether the song has a singer (CR-M3b-1: presence should also use lyric coverage)."""

from __future__ import annotations


def test_real_megafauna_singer_and_vocal_presence_agree(real_song):
    s = real_song("megafauna")
    lines = s.json("lyrics/lyrics.json")["lines"]
    singing = s.events("singing")
    vr = s.json("meta/vocal_range.json")
    assert len(lines) >= 10 and len(singing) >= 10
    assert vr["present"] is True or len(s.events("vocal_phrases")) > 0, \
        "lyrics + singing say there is a singer, vocals says there is none"
