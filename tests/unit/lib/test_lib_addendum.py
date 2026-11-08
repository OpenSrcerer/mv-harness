"""Addendum golden cases (src/mvh/assets/golden/addendum-vectors.json) against lib/mvh_load.py:
vizState, the lyric_at singer join, the meaning_at merge, the texture NaN fill and spectrum_window bytes.
The JS side runs the same cases in addendum.test.mjs."""

from __future__ import annotations

import json
import math
from pathlib import Path

import make_addendum
import numpy as np
import pytest

from mvh.contract.curvefile import ChannelData, assemble
from mvh.contract.events import dumps_events, dumps_json, make_envelope

REPO = Path(__file__).resolve().parents[3]
ADD = REPO / "src" / "mvh" / "assets" / "golden" / "addendum-vectors.json"
TOL = 1e-6


def close(actual, expected, where="$"):
    if expected is None:
        assert actual is None, f"{where}: expected None, got {actual!r}"
    elif isinstance(expected, bool):
        assert bool(actual) is expected and isinstance(actual, (bool, np.bool_)), (
            f"{where}: {actual!r} != {expected!r}"
        )
    elif isinstance(expected, (int, float)):
        assert not isinstance(actual, bool) and abs(float(actual) - expected) <= TOL * (1 + 1e-9) + 1e-12, (
            f"{where}: {actual!r} != {expected!r}"
        )
    elif isinstance(expected, str):
        assert actual == expected, f"{where}: {actual!r} != {expected!r}"
    elif isinstance(expected, list):
        actual = list(actual)
        assert len(actual) == len(expected), f"{where}: length {len(actual)} != {len(expected)}"
        for i, e in enumerate(expected):
            close(actual[i], e, f"{where}[{i}]")
    else:
        assert isinstance(actual, dict), f"{where}: {actual!r}"
        for k, e in expected.items():
            assert k in actual, f"{where}: missing {k}"
            close(actual[k], e, f"{where}.{k}")


@pytest.fixture(scope="module")
def add():
    with open(ADD, encoding="utf-8") as fh:
        return json.load(fh)


def write_song(inp: dict, out: Path) -> Path:
    """The addendum's inline song as a contract song folder (written with the contract writers)."""
    chans = [
        ChannelData(cid, np.asarray([np.nan if x is None else x for x in v], dtype=np.float32))
        for cid, v in inp["channels"].items()
    ]
    chans.append(ChannelData("spectrum128", np.asarray(inp["spectrum"], dtype=np.uint8)))
    assemble(out, chans)
    files = []
    for name, items in inp["events"].items():
        p = out / "events" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dumps_events(make_envelope(name, items, {})))
        files.append({"path": f"events/{name}.json", "kind": "events", "stage": "t", "events": name})
    for rel, doc in (
        ("lyrics/lyrics.json", inp["lyrics"]),
        ("meaning/meaning.json", inp["meaning"]),
        ("manifest.json", {"source": {"duration_s": inp["duration_s"]}, "files": files}),
    ):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dumps_json(doc))
    return out


@pytest.fixture(scope="module")
def song(ml, add, tmp_path_factory):
    return ml.load(write_song(add["song"], tmp_path_factory.mktemp("addendum") / "song"))


def test_addendum_file_is_current():
    assert ADD.read_text(encoding="utf-8") == make_addendum.dumps(make_addendum.build())


def test_viz_state(song, add):
    for t, fr, exp in add["viz_state"]:
        close(song.viz_state(t, fr), exp, f"viz {t} {fr}")


def test_lyric_at(song, add):
    for t, exp in add["lyric_at"]:
        got = song.lyric_at(t)
        close(got, exp, f"lyric {t}")
        if exp["line"] is not None:
            assert sorted(got["line"]) == sorted(exp["line"])


def test_meaning_at(song, add):
    for t, exp in add["meaning_at"]:
        got = song.meaning_at(t)
        assert sorted(got) == sorted(exp)
        close(got, exp, f"meaning {t}")


def test_texture_nan_fill(song, add):
    x = add["texture_nan_fill"]
    td = song.texture_data(x["ids"], width=x["width"])
    assert td["height"] == x["height"]
    close(td["data"].tolist(), x["data"])
    assert all(math.isfinite(v) for v in td["data"].tolist())


def test_spectrum_window(song, add):
    for t, s, exp in add["spectrum_window"]:
        assert song.spectrum_window(t, s).tolist() == exp
