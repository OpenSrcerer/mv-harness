# ruff: noqa: E501
"""lyrics on the synthetic song through the real models (faster-whisper large-v3, MMS_FA), scored against the
generator truth (tests/contract/synth/_truth/truth.json). PLAN §7: word alignment on TTS, median onset error
< 80 ms. Three source paths: a plain-text user file (ASR anchors), synthetic LRCLIB with a +1.3 s version offset
(global offset detection), and transcription (no text at all)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from tests.synth.m5.fakehttp import FIXTURES, seed_cache

pytestmark = pytest.mark.models

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"
TRUTH = json.loads((SYNTH / "_truth" / "truth.json").read_text(encoding="utf-8"))


def _run(tmp, ext=None, seed_lrclib=False, overrides=None):
    from tests.synth.m5.harness import Harness
    from tests.synth.m5.harness import slot as heavy

    h = Harness(SYNTH, tmp, input_audio=SYNTH / "_truth" / "synth-song.flac", overrides=overrides)
    if seed_lrclib:
        fx = json.loads((FIXTURES / "lrclib_synth.json").read_text(encoding="utf-8"))
        seed_cache(tmp / "_http" / "lyrics", fx["requests"])
    with heavy("builder-m5:lyrics-test", threads=6):
        rec = h.run("lyrics", params_ext=ext or {})
    return h, rec, h.json("lyrics", "lyrics/lyrics.json")


def _onset_errors(words):
    tw = TRUTH["words"]
    assert len(words) == len(tw)
    assert [w["text"].strip(",.!?").lower() for w in words] == [w["text"].lower() for w in tw]
    return np.array([abs(a["t"] - b["t"]) for a, b in zip(words, tw)])


@pytest.fixture(scope="module")
def txt_run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("txt"), {"lyrics": str(SYNTH / "_truth" / "lyrics_input.txt")})


@pytest.fixture(scope="module")
def lrclib_run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("lrclib"), seed_lrclib=True, overrides={"lyrics.lines": {"L002": {"dt": 0.25}}})


@pytest.fixture(scope="module")
def asr_run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("asr"))


def test_plain_text_alignment_on_tts(txt_run):
    h, rec, d = txt_run
    err = _onset_errors(d["words"])
    assert np.median(err) < 0.080, np.median(err)          # PLAN §7 threshold
    assert np.mean(err < 0.3) >= 0.95
    assert d["source"]["kind"] == "user" and d["source"]["format"] == "txt"
    assert d["grade"] in ("A", "B") and d["coverage"] >= 0.9 and d["lyrics_match_score"] >= 0.9
    assert d["alignment"]["mode"] == "anchored"
    # structure links and groups
    sec = {s["id"]: s for s in json.loads((SYNTH / "events" / "sections.json").read_text(encoding="utf-8"))["items"]}
    for ln in d["lines"]:
        s = sec[ln["section_id"]]
        assert s["t"] - 0.5 <= ln["t"] < s["t"] + s["d"]
    by_text = {}
    for ln in d["lines"]:
        by_text.setdefault(ln["text"], set()).add(ln["text_group"])
    assert all(len(v) == 1 for v in by_text.values())
    rep = [ln for ln in d["lines"] if ln["repeat_group"]]
    assert len(rep) == 4 and len({ln["repeat_group"] for ln in rep}) == 2          # the repeated chorus pair
    assert all(w["id"].startswith(w["line_id"] + ".") for w in d["words"])
    # exports exist and carry every line
    lrc = (h.stage_dir("lyrics") / "lyrics" / "lyrics.lrc").read_text(encoding="utf-8")
    assert lrc.count("\n[0") >= len(d["lines"])


def test_lrclib_offset_detection(lrclib_run):
    h, rec, d = lrclib_run
    assert d["source"]["kind"] == "lrclib" and d["source"]["lrclib_id"] == 900003
    assert d["source"]["offset_s"] == pytest.approx(-1.3, abs=0.15)              # G6: detected and applied
    assert d["source"]["offset_applied_s"] == pytest.approx(d["source"]["offset_s"])
    assert d["gate"]["checks"]["G6"]["applied"] and not d["source"]["version_mismatch"]
    assert d["gate"]["checks"]["G5"]["pass"] is True
    err = _onset_errors([w for w in d["words"]])
    # L002 was nudged by +0.25 s through overrides.json (lyrics.lines)
    l2 = [i for i, w in enumerate(d["words"]) if w["line_id"] == "L002"]
    assert np.median(err[l2]) == pytest.approx(0.25, abs=0.08)
    rest = np.delete(err, l2)
    assert np.median(rest) < 0.080
    assert next(ln for ln in d["lines"] if ln["id"] == "L002")["timing_source"] == "user"
    assert d["lrclib"]["chosen"]["id"] == 900003 and d["lrclib"]["requests"] == 4
    # the summary and provenance never carry lyric text
    blob = json.dumps(rec["result"]) + json.dumps(d["provenance"])
    assert "lanterns" not in blob.lower() and "harbor" not in blob.lower()


def test_transcription_path(asr_run):
    h, rec, d = asr_run
    assert d["source"]["kind"] == "transcribed" and "lyrics:transcribed" in rec["result"]["fallbacks"]
    assert d["lyrics_match_score"] is None and d["grade"] in ("B", "C")
    assert len(d["words"]) >= 45
    # word timing against the truth for LCS-matched words
    import difflib

    tw = TRUTH["words"]
    a = [w["text"].strip(",.!?").lower() for w in d["words"]]
    b = [w["text"].lower() for w in tw]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    err = [abs(d["words"][blk.a + k]["t"] - tw[blk.b + k]["t"]) for blk in sm.get_matching_blocks() for k in range(blk.size)]
    assert len(err) >= 45 and np.median(err) < 0.080
