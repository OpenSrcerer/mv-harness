import pytest

from mvh.contract import ids


@pytest.mark.parametrize("kind,good,bad", [
    ("section", ["S01", "S99", "S100"], ["S1", "s01", "S01a", "P01"]),
    ("phrase", ["P01", "P12"], ["P1", "P001x"]),
    ("eight", ["E000", "E001", "E1234"], ["E01", "E1"]),
    ("groove", ["G01"], ["G1"]),
    ("line", ["L001", "L1000"], ["L01", "L001.03"]),
    ("word", ["L001.03", "L012.10", "L001.100"], ["L001.3", "L01.03", "L001"]),
    ("voice", ["V1", "V12"], ["V0", "V01", "VP001"]),
    ("character", ["C1", "C3"], ["C0", "C01"]),
    ("motif", ["M1"], ["M01"]),
    ("cue", ["Q0001", "Q12345"], ["Q001", "Q1"]),
    ("vocal_phrase", ["VP001"], ["VP01", "V001"]),
    ("repeat_group", ["A", "Z", "AA", "AZ"], ["a", "AAA", "1"]),
    ("text_group", ["T01"], ["T1"]),
    ("line_group", ["LG01"], ["LG1", "L01"]),
])
def test_regexes(kind, good, bad):
    for s in good:
        assert ids.is_id(kind, s), (kind, s)
    for s in bad:
        assert not ids.is_id(kind, s), (kind, s)


def test_make_parse_roundtrip():
    for kind in ("section", "phrase", "eight", "groove", "line", "voice", "character", "motif", "cue", "edm_role",
                 "hit_point", "hold", "impact", "stop", "silence", "decay_tail", "vocal_phrase", "text_group", "line_group"):
        for n in (1, 7, 42, 1234):
            s = ids.make_id(kind, n)
            assert ids.parse_id(s) == (kind, n), s
    assert ids.make_id("section", 3) == "S03"
    assert ids.make_id("cue", 12) == "Q0012"
    assert ids.make_id("voice", 2) == "V2"
    assert ids.make_id("eight", 0) == "E000"
    with pytest.raises(ValueError):
        ids.make_id("section", 0)


def test_kind_disambiguation():
    assert ids.kind_of("VP001") == "vocal_phrase"
    assert ids.kind_of("V1") == "voice"
    assert ids.kind_of("LG01") == "line_group"
    assert ids.kind_of("L001") == "line"
    assert ids.kind_of("L001.03") == "word"
    assert ids.kind_of("B") == "repeat_group"
    assert ids.kind_of("nope") is None


def test_word_and_ref_helpers():
    assert ids.word_id("L001", 3) == "L001.03"
    assert ids.split_word_id("L012.11") == ("L012", 11)
    assert ids.ref_key("beat", 12) == "beat:12"
    assert ids.parse_ref_key("bar:0") == ("bar", 0)
    assert ids.occurrence_label("chorus", 2) == "chorus#2"
    assert [ids.repeat_group_label(n) for n in (1, 26, 27, 28, 52, 53)] == ["A", "Z", "AA", "AB", "AZ", "BA"]
    assert ids.slugify("Sir Isaac Newton vs Bill Nye") == "sir-isaac-newton-vs-bill-nye"
    assert ids.slugify("tëst ♪ 曲") == "test"
    assert ids.SLUG_RE.match("newton-vs-nye")


def test_channel_and_events_name_regexes():
    for c in ("bands.bass", "vocal.mouth_open.V2", "chroma.0", "stem.drums_kick.level", "mood.tag.happy"):
        assert ids.CHANNEL_ID_RE.match(c), c
    for n in ("beats", "notes.bass", "hits.kick", "onsets.bass"):
        assert ids.EVENTS_NAME_RE.match(n), n
    assert not ids.EVENTS_NAME_RE.match("Notes.Bass")
