# ruff: noqa: E501  (long lines)
"""The managed block of meaning/intent.md: the viewer must never disturb what the user wrote."""
from __future__ import annotations

import pytest

from mvh.stages.viewer import intent_block as ib

USER = "# What this song means to me\n\n## The story\nTwo figures keep a harbour lit.\n\n## Never show\n- fire\n"


def _sec(**kw):
    base = {"t0": 9.0, "t1": 17.0, "label": "verse#1", "feel": "call and response", "meaning": "line one\nline two",
            "movement": "", "camera": "", "palette": "#1B2A49, #f2a541", "do_not": "no fire\nno text"}
    base.update(kw)
    return base


def test_append_preserves_user_text_and_roundtrips():
    st = ib.merge(ib.empty(), {"voices": {"V1": {"character_id": "C1", "name": "The Lamplighter"}}, "sections": {"S02": _sec()}})
    out = ib.apply(USER, st)
    assert out.startswith(USER)  # everything the user wrote is untouched, byte for byte
    back = ib.parse(out)
    assert back["voices"]["V1"] == {"character_id": "C1", "name": "The Lamplighter"}
    s = back["sections"]["S02"]
    assert (s["t0"], s["t1"], s["label"]) == (9.0, 17.0, "verse#1")
    assert s["meaning"] == "line one / line two"  # one line per value
    assert s["palette"] == "#1b2a49, #f2a541"
    assert s["do_not"] == ["no fire", "no text"]


def test_update_replaces_only_the_block():
    st = ib.merge(ib.empty(), {"voices": {"V1": {"character_id": "C1", "name": "A"}}})
    once = ib.apply(USER, st)
    st2 = ib.merge(ib.parse(once), {"voices": {"V1": {"character_id": "C2", "name": "B"}}})
    twice = ib.apply(once, st2)
    assert twice.count(ib.BEGIN) == 1 and twice.startswith(USER)
    assert ib.parse(twice)["voices"]["V1"]["character_id"] == "C2"
    # text the user adds AFTER the block survives a later update
    tail = twice + "\n## Later\nmore\n"
    again = ib.apply(tail, ib.merge(ib.parse(tail), {"voices": {"V2": {"character_id": "C3", "name": "C"}}}))
    assert again.endswith("## Later\nmore\n") and set(ib.parse(again)["voices"]) == {"V1", "V2"}


def test_empty_state_removes_block_and_never_creates_one():
    assert ib.apply(USER, ib.empty()) == USER
    st = ib.merge(ib.empty(), {"voices": {"V1": {"character_id": "C1", "name": "A"}}})
    with_block = ib.apply(USER, st)
    removed = ib.apply(with_block, ib.merge(ib.parse(with_block), {"voices": {"V1": None}}))
    assert ib.BEGIN not in removed and removed.strip() == USER.strip()


def test_new_file_gets_a_title():
    st = ib.merge(ib.empty(), {"voices": {"V1": {"character_id": "C1", "name": "A"}}})
    out = ib.apply("", st)
    assert out.startswith("# What this song means") and ib.parse(out)["voices"]["V1"]["name"] == "A"


def test_section_with_no_content_is_dropped():
    st = ib.merge(ib.empty(), {"sections": {"S02": _sec()}})
    st = ib.merge(st, {"sections": {"S02": _sec(feel="", meaning="", palette="", do_not="")}})
    assert st["sections"] == {}


@pytest.mark.parametrize("patch", [
    {"voices": {"X1": {"character_id": "C1", "name": "a"}}},
    {"voices": {"V1": {"character_id": "nope", "name": "a"}}},
    {"sections": {"S02": _sec(palette="red")}},
    {"sections": {"S02": _sec(t1=1.0)}},
    {"sections": {"S02": _sec(feel="x" * 5000)}},
    {"sections": {"bad": _sec()}},
])
def test_rejects_bad_patches(patch):
    with pytest.raises(ib.IntentError):
        ib.merge(ib.empty(), patch)


def test_marker_text_inside_a_value_cannot_break_the_block():
    st = ib.merge(ib.empty(), {"sections": {"S02": _sec(meaning="a <!-- mvh-viewer:end --> b")}})
    out = ib.apply(USER, st)
    assert out.count(ib.END) == 1 and out.count(ib.BEGIN) == 1
    assert "S02" in ib.parse(out)["sections"]
