"""D84 without models: a bar's own start and end (lyrics.lines {key: {start, end}}) widen the line's span and never
move a word or leave one outside it. Synthetic words only."""
from __future__ import annotations

import jsonschema

from mvh.contract import catalog
from mvh.stages.lyrics import core as C


def _line(order, words, t0, step=0.5):
    k = len(words)
    return {"order": order, "origin": "source", "words": list(words), "text": " ".join(words), "toks": [[1]] * k,
            "wres": [{"start": t0 + i * step, "end": t0 + i * step + 0.3, "score": 0.9} for i in range(k)],
            "wt": [t0 + i * step for i in range(k)], "wd": [0.3] * k, "src_wt": [None] * k, "src_wp": [None] * k,
            "backing": False, "speaker": None, "timing_source": "ctc", "dev": None, "pinned": False}


def _lines(ovr, splits=None):
    lines = [_line(0, ["a1", "a2"], 1.0), _line(1, ["h1", "h2", "h3", "h4"], 5.0)]
    C._assign_legacy_ids(lines)
    lines = C._apply_splits(lines, {"lyrics.splits": splits or []}, [])
    C._assign_refs(lines)
    C._apply_overrides(lines, {"lyrics.lines": ovr}, [])
    return lines


def test_a_wider_bar_moves_no_word():
    lines = _lines({"r0": {"start": 0.4, "end": 3.0}})
    assert lines[0]["wt"] == [1.0, 1.5] and lines[0]["wd"] == [0.3, 0.3]
    assert C._line_span(lines[0]) == (0.4, 3.0)
    assert C._line_span(lines[1]) == (5.0, 6.8)                     # untouched line: its words' span


def test_a_bar_never_leaves_a_word_outside():
    lines = _lines({"r0": {"start": 1.3, "end": 1.2}})               # narrower than its words
    assert C._line_span(lines[0]) == (1.0, 1.8)


def test_the_bar_edges_survive_a_nudge_of_the_line():
    lines = _lines({"r0": {"dt": 1.0, "end": 4.0}})
    assert lines[0]["wt"] == [2.0, 2.5]                               # words moved by dt, the end is absolute
    assert C._line_span(lines[0]) == (2.0, 4.0)


def test_a_whole_line_key_on_a_split_line_sets_the_first_start_and_the_last_end():
    key = C._pin_key("h1 h2 h3 h4")
    lines = _lines({"r1": {"start": 4.0, "end": 9.0}}, splits=[{"index": 1, "at": [2], "key": key}])
    parts = [x for x in lines if x["order"] == 1]
    assert C._line_span(parts[0]) == (4.0, 5.8) and C._line_span(parts[1]) == (6.0, 9.0)
    lines = _lines({"r1p1": {"start": 5.9}}, splits=[{"index": 1, "at": [2], "key": key}])
    assert C._line_span([x for x in lines if x.get("part") == 1][0]) == (5.9, 6.8)


def test_the_contract_accepts_bar_edges():
    sch = catalog.OVERRIDES if hasattr(catalog, "OVERRIDES") else None
    if sch is None:
        import json
        import pathlib
        sch = json.loads((pathlib.Path(__file__).parents[3] / "schema" / "envelope" / "overrides.schema.json").read_text("utf-8"))
    lines = sch["properties"]["lyrics"]["properties"]["lines"]
    jsonschema.validate({"r3": {"start": 1.5}, "r3p1": {"end": 4.0, "dt": 0.1}}, lines)
