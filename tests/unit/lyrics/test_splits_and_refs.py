"""D83 without models: splitting a lyric line into bars, stable references (r12, r12p1, r12w4) and corrections keyed
by them; the voices stage's forced voices by reference and voice merges. Synthetic words only."""
from __future__ import annotations

import pytest

from mvh.stages.lyrics import core as C
from mvh.stages.voices import core as VC


def _line(order, words, t0, step=0.5, origin="source"):
    k = len(words)
    return {"order": order, "origin": origin, "words": list(words), "text": " ".join(words), "toks": [[1]] * k,
            "wres": [{"start": t0 + i * step, "end": t0 + i * step + 0.3, "score": 0.9} for i in range(k)],
            "wt": [t0 + i * step for i in range(k)], "wd": [0.3] * k, "src_wt": [None] * k, "src_wp": [None] * k,
            "backing": False, "speaker": None, "timing_source": "ctc", "dev": None, "pinned": False}


def _song():
    return [_line(0, ["a1", "a2"], 1.0), _line(1, ["h1", "h2", "h3", "h4", "h5"], 5.0), _line(2, ["b1", "b2"], 10.0),
            _line(2, ["x1"], 20.0, origin="expanded")]


def test_a_line_split_into_bars():
    lines = _song()
    key = C._pin_key("h1 h2 h3 h4 h5")
    warns: list[str] = []
    out = C._apply_splits(lines, {"lyrics.splits": [{"index": 1, "at": [2, 4], "key": key}]}, warns)
    assert not warns and len(out) == 6
    parts = [x for x in out if x["order"] == 1]
    assert [x["words"] for x in parts] == [["h1", "h2"], ["h3", "h4"], ["h5"]]
    assert [(x["part"], x["word0"]) for x in parts] == [(0, 0), (1, 2), (2, 4)]
    assert [x["wt"] for x in parts] == [[5.0, 5.5], [6.0, 6.5], [7.0]]                # each word keeps its time
    assert [len(x["wres"]) for x in parts] == [2, 2, 1] and parts[2]["text"] == "h5"
    assert parts[0]["source_text"] == "h1 h2 h3 h4 h5"
    C._assign_refs(out)
    assert [x["ref"] for x in out] == ["r0", "r1p0", "r1p1", "r1p2", "r2", None]       # an added line has none


@pytest.mark.parametrize("splits", [
    [{"index": 1, "at": [2], "key": "not-the-key"}],   # the text changed since the split was set
    [{"index": 7, "at": [1]}],                         # no such source line
    [{"index": 3, "at": [1]}],                         # the added line is not a source line
    [{"at": [1]}],
])
def test_bad_splits_are_ignored_with_a_warning(splits):
    warns: list[str] = []
    out = C._apply_splits(_song(), {"lyrics.splits": splits}, warns)
    assert len(out) == 4 and len(warns) == 1


def test_split_positions_at_the_edges_do_nothing():
    out = C._apply_splits(_song(), {"lyrics.splits": [{"index": 1, "at": [0, 5, 9]}]}, [])
    assert len(out) == 4


def _overridden(ovr, splits=None):
    lines = _song()
    C._assign_legacy_ids(lines)
    lines = C._apply_splits(lines, {"lyrics.splits": splits or []}, [])
    C._assign_refs(lines)
    warns: list[str] = []
    C._apply_overrides(lines, ovr, warns)
    return lines, warns


def test_word_references_follow_the_word_into_its_bar():
    splits = [{"index": 1, "at": [2]}]
    lines, warns = _overridden({"lyrics.words": {"r1w3": {"t": 7.25, "d": 0.4}, "r1w0": {"t": 4.9}}}, splits)
    assert not warns
    p0, p1 = [x for x in lines if x["order"] == 1]
    assert p0["wt"][0] == 4.9 and p1["wt"][1] == 7.25 and p1["wd"][1] == 0.4       # r1w3 is the 2nd word of bar 2


def test_line_references_move_a_bar_or_every_bar():
    splits = [{"index": 1, "at": [2]}]
    lines, _w = _overridden({"lyrics.lines": {"r1p1": {"dt": 2.0}, "r0": {"dt": -0.5}}}, splits)
    p0, p1 = [x for x in lines if x["order"] == 1]
    assert p0["wt"] == [5.0, 5.5] and p1["wt"] == [8.0, 8.5, 9.0]
    assert lines[0]["wt"] == [0.5, 1.0]
    lines, _w = _overridden({"lyrics.lines": {"r1": {"dt": 1.0}}}, splits)          # the whole source line: both bars
    assert [x["wt"][0] for x in lines if x["order"] == 1] == [6.0, 7.0]
    lines, _w = _overridden({"lyrics.lines": {"r1p0": {"dt": 1.0}}})               # part 0 of an unsplit line = the line
    assert [x["wt"][0] for x in lines if x["order"] == 1] == [6.0]


def test_old_ids_still_work_and_unknown_keys_warn():
    lines, warns = _overridden({"lyrics.lines": {"L002": {"dt": 1.0}}, "lyrics.words": {"L001.02": {"t": 1.7}, "r9w0": {"t": 1}}})
    assert lines[1]["wt"][0] == 6.0 and lines[0]["wt"][1] == 1.7 and len(warns) == 1


# ------------------------------------------------------------------------------------------------ voices
LINES = [{"id": "L001", "ref": "r0"}, {"id": "L002", "ref": "r1p0"}, {"id": "L003", "ref": "r1p1"}, {"id": "L004", "ref": None}]


def test_forced_voices_by_reference():
    f = VC.forced_voices(LINES, {"L004": "V2"}, {"r1": "V3", "r1p1": "V5", "L001": "V1", "r0": "V2"})
    assert f == {"L001": ("V2", "override"), "L002": ("V3", "override"), "L003": ("V5", "override"), "L004": ("V2", "intent")}
    assert VC.forced_voices(LINES, {}, {"r1": "nope"}) == {}


def test_merge_map_follows_chains_and_skips_cycles():
    warns: list[str] = []
    assert VC.merge_map({"V4": "V3", "V3": "V1", "V9": "V9", "x": "V1"}, warns) == {"V4": "V1", "V3": "V1"}
    assert not warns
    assert VC.merge_map({"V2": "V3", "V3": "V2"}, warns) == {} and len(warns) == 2


def test_the_contract_accepts_the_new_keys():
    from mvh.contract import catalog
    from mvh.runner import overrides as ovr

    doc = {"lyrics": {"lines": {"r1p1": {"dt": 0.5}, "L002": {"dt": 0.1}}, "words": {"r1w3": {"t": 7.0}, "L001.02": {"d": 0.2}},
                      "splits": [{"index": 1, "at": [2, 4], "key": "abc"}]},
           "voices": {"lines": {"r1p1": "V3"}, "merge": {"V3": "V1"}}}
    assert ovr.validate(doc) == []
    assert ovr.validate({"lyrics": {"lines": {"x1": {"dt": 1}}}})
    assert ovr.validate({"lyrics": {"splits": [{"index": 1, "at": [0]}]}})
    assert ovr.validate({"voices": {"merge": {"V3": "C1"}}})
    assert catalog.OVERRIDE_KEYS["lyrics.splits"] == "lyrics" and catalog.OVERRIDE_KEYS["voices.merge"] == "voices"


def test_an_old_id_key_keeps_meaning_the_line_as_numbered_before_the_split():
    """A correction written as L003.01 (b1) before line 2 was split still lands on b1, though the split renumbers it."""
    splits = [{"index": 1, "at": [2]}]
    lines, warns = _overridden({"lyrics.words": {"L003.01": {"t": 9.5}, "L002.04": {"t": 6.75}}, "lyrics.lines": {"L001": {"dt": 0.25}}}, splits)
    assert not warns
    b = next(x for x in lines if x["order"] == 2 and x["origin"] == "source")
    assert b["wt"][0] == 9.5 and b["legacy_id"] == "L003"
    p1 = [x for x in lines if x["order"] == 1][1]
    assert p1["wt"][1] == 6.75 and p1["legacy_id"] == "L002"          # L002.04 = h4, now the 2nd word of bar 2
    assert lines[0]["wt"] == [1.25, 1.75]
    lines, _w = _overridden({"lyrics.lines": {"L002": {"dt": 1.0}}}, splits)  # an old line key moves every bar of it
    assert [x["wt"][0] for x in lines if x["order"] == 1] == [6.0, 7.0]
