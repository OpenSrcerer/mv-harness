"""Real-song snapshots for the whole M5 chain (identity -> lyrics -> voices -> lipsync), opt-in (-m real or
MVH_REAL_TESTS=1). Upstream = tests/contract/real-<slug>; LRCLIB answers are replayed from the W0 recordings in
tests/.cache/real/<slug>/http (gitignored; the stage's request keys are rebuilt from them), MusicBrainz is not
called (offline). Asserts tolerant snapshots and the PLAN §7.3 song checks. Never prints lyric text."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.real, pytest.mark.models]

REPO = Path(__file__).resolve().parents[3]
SONGS = {"jeremy": REPO / "songs" / "Jeremy (Redux Version).flac",
         "newton-vs-nye": REPO / "songs" / "Sir Isaac Newton vs Bill Nye.flac",
         "megafauna": Path(r"C:\Users\OpenSrcerer\Desktop\playground\viz\MEGAFAUNA.flac"),
         "versatile": Path(r"C:\Users\OpenSrcerer\Desktop\playground\viz\Versatile.flac")}


def _seed_lrclib(slug: str, http_dir: Path, title: str, artist: str, album: str | None, duration: float) -> None:
    from tests.synth.m5.fakehttp import seed_cache

    src = REPO / "tests" / ".cache" / "real" / slug / "http"
    d = int(round(duration))
    base = "https://lrclib.net/api/"
    plan = [("get_with_album.json", "get", {"track_name": title, "artist_name": artist, "album_name": album or "", "duration": d}),
            ("get_no_album.json", "get", {"track_name": title, "artist_name": artist, "duration": d}),
            ("search_track_artist.json", "search", {"track_name": title, "artist_name": artist}),
            ("search_q.json", "search", {"q": f"{title} {artist}"})]
    reqs = []
    for fn, ep, params in plan:
        if album is None and fn == "get_with_album.json":
            continue
        body = json.loads((src / fn).read_text(encoding="utf-8"))
        status = int(body.get("statusCode", 200)) if isinstance(body, dict) and "statusCode" in body else 200
        reqs.append({"method": "GET", "url": base + ep, "params": params, "status": status, "body": body})
    seed_cache(http_dir, reqs)


def _chain(slug: str, tmp: Path):
    from tests.synth.m5.harness import Harness, slot

    if not SONGS[slug].is_file() or not (REPO / "tests" / ".cache" / "real" / slug / "http").is_dir():
        pytest.skip(f"{slug}: song or W0 cache missing")
    h = Harness(REPO / "tests" / "contract" / f"real-{slug}", tmp, slug=slug, input_audio=SONGS[slug])
    h.run("identity")
    ident = h.json("identity", "meta/identity.json")
    _seed_lrclib(slug, tmp / "_http" / "lyrics", ident["title"], ident["artist"], ident["album"], ident["duration_s"])
    recs = {}
    for st in ("lyrics", "voices", "lipsync"):
        with slot(f"builder-m5:real-test:{slug}:{st}"):
            recs[st] = h.run(st)
    return h, recs


@pytest.fixture(scope="module")
def jeremy(tmp_path_factory):
    return _chain("jeremy", tmp_path_factory.mktemp("jeremy"))


@pytest.fixture(scope="module")
def newton(tmp_path_factory):
    return _chain("newton-vs-nye", tmp_path_factory.mktemp("newton"))


def test_jeremy(jeremy):
    h, recs = jeremy
    d = h.json("lyrics", "lyrics/lyrics.json")
    assert d["source"]["kind"] == "lrclib" and d["source"]["lrclib_id"] == 22859144      # the 316.587 s entry
    assert abs(d["source"]["duration_diff_s"]) < 0.05
    assert d["grade"] in ("A", "B", "C") and d["lyrics_match_score"] >= 0.70
    assert d["coverage"] >= 0.70
    assert abs(d["source"]["offset_applied_s"]) < 0.2                                     # -0.11 s is below the trigger
    last = max(w["t"] + w["d"] for w in d["words"])
    assert last < 222.0                                                                   # no words in the wordless outro
    assert 38 <= len(d["lines"]) <= 44
    m = h.json("voices", "meta/voices.json")
    assert 1 <= m["n_voices"] <= 2
    mo = h.curve("lipsync", "vocal.mouth_open")
    assert len(mo) == -(-13961472 * 100 // 44100) and mo[int(240 * 100):int(300 * 100)].max() > 0.05   # ungated outro


def test_newton(newton):
    h, recs = newton
    d = h.json("lyrics", "lyrics/lyrics.json")
    assert d["source"]["kind"] == "lrclib" and d["source"]["lrclib_id"] == 3921433       # synced beats plain within 2 s
    assert d["source"]["offset_s"] == pytest.approx(-1.33, abs=0.2) and d["gate"]["checks"]["G6"]["applied"]
    assert d["grade"] in ("A", "B") and d["lyrics_match_score"] >= 0.75
    assert d["gate"]["checks"]["G5"]["pass"] is True
    first = d["lines"][0]                                                                 # the announcer intro (M5-D11)
    assert first["t"] < 5.0 and all("asr_only" in w.get("flags", []) for w in d["words"] if w["line_id"] == first["id"])
    m = h.json("voices", "meta/voices.json")
    assert 3 <= m["n_voices"] <= 4                                                        # W0: A B A C + announcer
    spans0 = h.json("voices", "events/voice_spans.json")["items"]
    v_intro = next(s["voice_id"] for s in spans0 if s["line_id"] == first["id"])
    assert all(s["voice_id"] != v_intro for s in spans0 if s["line_id"] != first["id"])   # its own voice
    spans = h.json("voices", "events/voice_spans.json")["items"]
    lead = [s for s in spans if s["role"] == "lead"]
    runs = 1 + sum(1 for a, b in zip(lead, lead[1:]) if a["voice_id"] != b["voice_id"])
    assert runs <= 12                                                                     # blocks, not scatter
    chans = recs["lipsync"]["result"]["summary"]["channels"]
    assert sum(1 for c in chans if c.startswith("vocal.mouth_open.V")) >= 3
    assert recs["lipsync"]["result"]["summary"]["overlap_frac"] < 0.15


@pytest.mark.parametrize("slug", ["megafauna", "versatile"])
def test_electronic(slug, tmp_path):
    h, recs = _chain(slug, tmp_path)
    d = h.json("lyrics", "lyrics/lyrics.json")
    if slug == "megafauna":
        assert d["source"]["kind"] in ("embedded", "transcribed")
        assert d["alignment"]["stem"] == "vocals" and d["asr"]["vad_retry"]["used"]         # M5-D18, M5-D19
        assert d["lyrics_match_score"] >= 0.4 and d["asr"]["words"] >= 40
        m = h.json("voices", "meta/voices.json")
        assert m["n_voices"] <= 2                                                         # M5-D21 small sample
        if d["grade"] == "D":
            assert all(s["review"] for s in h.json("voices", "events/voice_spans.json")["items"])   # M5-D22
    else:
        assert d["source"]["kind"] in ("none", "transcribed") and d["source"]["lrclib_id"] is None   # false friends rejected
    mo = h.curve("lipsync", "vocal.mouth_open")
    assert np.all(np.isfinite(mo)) and mo.max() <= 1.0
