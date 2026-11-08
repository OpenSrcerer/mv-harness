# ruff: noqa: E501  (long lines)
"""The viewer stage: what viewer.html contains, size caps, privacy switch, determinism, script validity."""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import zlib

import numpy as np
import pytest
from viewer_support import SYNTH, make_ctx

DATA_RE = re.compile(r'<script id="mvh-data" type="application/json">(.*?)</script>', re.S)


def _data(html: str) -> dict:
    m = DATA_RE.search(html)
    assert m, "no inline data block"
    return json.loads(m.group(1).replace("<\\/", "</"))


def _file(data: dict, rel: str) -> bytes:
    kind, n, z = data["files"][rel]
    raw = zlib.decompress(base64.b64decode(z))
    assert len(raw) == n
    return raw


def test_page_structure(built_html):
    html = built_html
    assert html.startswith("<!doctype html>")
    assert html.count("<!--MVH-EDIT-->") == 1  # the edit server injects its token here
    assert 'id="mvh-src"' in html and "export class Song" in html  # inline copy of lib/mvh.js
    # nothing may close the inline scripts early
    for block in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert "</script" not in block.lower()


def test_no_external_resources(built_html):
    # no CDN, no web fonts: the page works offline
    head = built_html.split('<script id="mvh-src"')[0]
    assert not re.search(r"(src|href)=\"https?://", head)
    assert "@import" not in head and "fonts.googleapis" not in built_html


def test_inline_data_matches_the_fixture(built_html):
    d = _data(built_html)
    assert d["slug"] == "synth" and abs(d["duration"] - 56.5) < 0.01
    assert d["title"] == "Lanterns on the Tide"
    beats = json.loads(_file(d, "events/beats.json"))
    ref = json.loads((SYNTH / "events" / "beats.json").read_text(encoding="utf-8"))
    assert beats["items"] == ref["items"]
    assert "meta/vocal_range.json" in d["files"] and "lyrics/lyrics.json" in d["files"] and "meaning/meaning.json" in d["files"]
    man = json.loads(_file(d, "manifest.json"))
    names = {f["events"] for f in man["files"]}
    assert {"beats", "sections", "singing", "cues"} <= names
    assert man["source"]["duration_s"] == d["duration"]


def test_reduced_curves_are_exact_copies(built_html):
    d = _data(built_html)
    idx = json.loads(_file(d, "curves/index.json"))
    ids = {c["id"] for c in idx["channels"]}
    assert {"bands.bass", "loud.short_term_lufs", "vocal.midi", "stem.drums.level", "tempo.bpm"} <= ids
    assert "timbre.centroid_hz" not in ids and "chroma.0" not in ids  # not drawn: not inlined
    ref = json.loads((SYNTH / "curves" / "index.json").read_text(encoding="utf-8"))
    refc = {c["id"]: c for c in ref["channels"]}
    for cid in ("bands.bass", "vocal.midi", "stem.bass.level"):
        c = next(c for c in idx["channels"] if c["id"] == cid)
        f = idx["files"][c["file"]]
        got = np.frombuffer(_file(d, f["path"]), dtype="<f4", count=c["n"], offset=c["offset_bytes"])
        rc = refc[cid]
        want = np.fromfile(SYNTH / ref["files"][rc["file"]]["path"], dtype="<f4", count=rc["n"], offset=rc["offset_bytes"])
        np.testing.assert_array_equal(got, want)  # NaN positions (unvoiced) included
        assert c["resample"] == rc["resample"] and c["rate_hz"] == rc["rate_hz"]
    sp = idx["files"]["spectrum128"]
    assert sp["dtype"] == "u8" and sp["n_channels"] == 128
    raw = _file(d, "curves/spectrum128.u8")
    assert raw == (SYNTH / "curves" / "spectrum128.u8").read_bytes()


def test_waveform_base_matches_audio(built_html):
    d = _data(built_html)
    w = d["wave"]
    assert w["hz"] == 1000 and abs(w["n"] - 56500) <= 2
    q = np.frombuffer(base64.b64decode(w["data"]), dtype=np.int8)
    assert q.size == 2 * w["n"] and np.all(q[0::2] <= q[1::2])
    assert q.max() == 127 or q.min() == -127  # scaled to the song peak
    # the digital silence pre-roll (first 0.5 s) is flat
    assert np.abs(q[: 2 * 400]).max() <= 1


def test_preview_audio_inlined_only_when_small(synth_dir):
    big = make_ctx({"inline_audio_max_mb": 0.01})
    from mvh.stages.viewer import run

    run(big)
    d = _data(big.writer.files["viewer.html"])
    assert d["audio_preview"] is None and "viewer:preview_not_inlined" in d["info"]["fallbacks"]
    ok = make_ctx({"inline_audio_max_mb": 50})
    run(ok)
    d2 = _data(ok.writer.files["viewer.html"])
    assert d2["audio_preview"] and base64.b64decode(d2["audio_preview"]) == (SYNTH / "audio" / "preview.opus").read_bytes()


def test_cap_drops_the_spectrogram_first(synth_dir):
    from mvh.stages.viewer import run

    ctx = make_ctx({"inline_cap_mb": 0.3})
    res = run(ctx)
    d = _data(ctx.writer.files["viewer.html"])
    assert "curves/spectrum128.u8" not in d["files"]
    assert "viewer:spectrogram_not_inlined" in res.fallbacks
    assert "spectrum128" not in json.loads(_file(d, "curves/index.json"))["files"]


def test_lyrics_privacy_switch(synth_dir):
    from mvh.stages.viewer import run

    lyr = json.loads((SYNTH / "lyrics" / "lyrics.json").read_text(encoding="utf-8"))
    sample = lyr["lines"][0]["text"]
    on = make_ctx()
    run(on)
    assert sample in zlib.decompress(base64.b64decode(_data(on.writer.files["viewer.html"])["files"]["lyrics/lyrics.json"][2])).decode("utf-8")
    off = make_ctx({"inline_lyrics": False})
    run(off)
    html = off.writer.files["viewer.html"]
    assert sample not in html and "lyrics/lyrics.json" not in _data(html)["files"]
    # the compressed bytes hide text anyway: also check the raw words are not stored in clear in any other file
    for rel in _data(html)["files"]:
        assert sample.encode() not in _file(_data(html), rel)


def test_missing_data_is_reported_not_fatal(synth_dir):
    from mvh.stages.viewer import run

    ctx = make_ctx(exclude=("events/drum_hits.json", "events/hit_points.json", "meaning/", "lyrics/"))
    res = run(ctx)
    assert res.status == "ok"
    assert {"hits", "meaning", "lyrics"} <= set(res.summary["lanes_without_data"])
    assert res.confidence is not None and res.confidence < 1.0


def test_deterministic(synth_dir):
    from mvh.stages.viewer import run

    a, b = make_ctx(), make_ctx()
    run(a)
    run(b)
    assert a.writer.files["viewer.html"] == b.writer.files["viewer.html"]


def test_declared_output_and_cache_key_covers_assets():
    from mvh.stages.viewer import STAGE

    assert [o.path for o in STAGE.outputs] == ["viewer.html"]
    assert STAGE.module == "M6a" and not STAGE.override_keys and STAGE.env == "main"
    assert len(STAGE.params["assets"]) == 16  # a changed viewer source changes the key


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_viewer_script_parses(built_html, tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", built_html, re.S)
    assert len(scripts) == 1
    p = tmp_path / "viewer.js"
    p.write_text(scripts[0], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:800]
