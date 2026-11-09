"""R-WORDS M5 (major): an LRCLIB entry flagged ``instrumental`` silences a sung song.

1. Ranking: ``lrclib.rank`` sorts accepted candidates by (synced first, word sync, |Δdur|); "usable" counts an
   ``instrumental`` entry like one with lyrics. Among unsynced candidates within 2 s an instrumental duplicate with
   a smaller |Δdur| (LRCLIB holds many user-submitted duplicates, some wrongly flagged instrumental) beats an
   entry that has the plain lyrics.
2. Consequence (core.run): ``chosen.instrumental`` sets ``instrumental_hint``; the transcription fallback is then
   skipped (``... and not instrumental_hint``) even when the ASR heard the whole song, so lyrics.json comes out
   ``instrumental: true`` with no lines and no words, voices gets nothing, and lipsync only has its ungated
   fallback. The ASR evidence (here 53 words at mean p 0.93 on the synthetic song) is never weighed against the flag.

Synthetic LRCLIB answers (tests/fixtures/http style, invented lyrics only).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mvh.stages.lyrics import lrclib as LR

REPO = Path(__file__).resolve().parents[4]
SYNTH = REPO / "tests" / "contract" / "synth"
TITLE, ARTIST, ALBUM = "Lanterns on the Tide", "mv-harness fixture", "Synthetic Sessions"


def _obj(i, dur, plain=None, synced=None, instr=False):
    return {"id": i, "name": TITLE, "trackName": TITLE, "artistName": ARTIST, "albumName": ALBUM, "duration": dur,
            "instrumental": instr, "hasWordSync": False, "lyricsfile": None, "plainLyrics": plain, "syncedLyrics": synced}


def test_entry_with_lyrics_beats_an_instrumental_duplicate():
    pool = {1: LR.Candidate(1, _obj(1, 57.5, plain="Paper lanterns over the river\nCarry the light"), "search"),
            2: LR.Candidate(2, _obj(2, 56.6, instr=True), "search")}
    c = LR.choose(LR.rank(pool, title=TITLE, artist=ARTIST, duration_s=56.5))
    assert c is not None and not c.instrumental, f"chose the instrumental duplicate {c.id if c else None} over the entry with lyrics"


@pytest.mark.models
def test_instrumental_flag_does_not_override_a_confident_asr(tmp_path):
    from tests.synth.m5.fakehttp import seed_cache
    from tests.synth.m5.harness import Harness, slot

    base = "https://lrclib.net/api/"
    q = {"track_name": TITLE, "artist_name": ARTIST}
    reqs = [
        {"url": base + "get", "params": {**q, "album_name": ALBUM, "duration": 56}, "status": 404, "body": {"statusCode": 404}},
        {"url": base + "get", "params": {**q, "duration": 56}, "status": 404, "body": {"statusCode": 404}},
        {"url": base + "search", "params": q, "status": 200, "body": [_obj(77, 56.6, instr=True)]},
        {"url": base + "search", "params": {"q": f"{TITLE} {ARTIST}"}, "status": 200, "body": []},
    ]
    seed_cache(tmp_path / "_http" / "lyrics", reqs)
    h = Harness(SYNTH, tmp_path)
    with slot("r-words-m5:review-test", threads=6):
        h.run("lyrics")
    d = h.json("lyrics", "lyrics/lyrics.json")
    assert d["lrclib"]["status"] == "chosen" and d["lrclib"]["chosen"]["instrumental"]       # the setup took effect
    assert d["asr"]["words"] >= 40                                                            # the ASR heard the song
    assert not d["instrumental"] and len(d["words"]) >= 40, (
        f"instrumental={d['instrumental']} with {len(d['words'])} words although the ASR kept {d['asr']['words']} words "
        f"(mean p {d['asr']['mean_word_p']})")
