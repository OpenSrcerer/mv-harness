"""lyrics sources: parsers (LRC + A2, SRT, VTT, TXT, Lyricsfile), encodings, labels, repeats; the LRCLIB cascade
and ranking on synthetic recorded HTTP. Synthetic text only; fast (no models)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.synth.m5.fakehttp import FIXTURES

from mvh.stages.lyrics import lrclib as LR
from mvh.stages.lyrics import text as T

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"


def test_lrc_a2_word_tags_and_end():
    src = T.parse_lrc((SYNTH / "_truth" / "lyrics_input.lrc").read_text(encoding="utf-8"))
    assert src["format"] == "lrc" and src["has_word_sync"] and len(src["lines"]) == 10
    l0 = src["lines"][0]
    assert l0["t"] == pytest.approx(9.0) and l0["end"] == pytest.approx(10.97)
    assert [w["t"] for w in l0["words"][:2]] == [pytest.approx(9.0), pytest.approx(9.5)]
    assert src["meta"]["ti"] == "Lanterns on the Tide"


def test_lrc_repeats_offset_and_labels():
    txt = "[offset:+500]\n[00:10.00][00:30.00]Ann: Same hook here\n[00:12.00]Ann: my line\n[00:14.00]\n[00:20.00](ooh ooh)\n"
    src = T.parse_lrc(txt)
    ts = [round(x["t"], 2) for x in src["lines"]]
    assert ts == [9.5, 11.5, 19.5, 29.5]                     # offset +500 ms shows lyrics earlier; repeats expanded
    assert src["lines"][1]["speaker"] == "Ann" and src["lines"][1]["text"] == "my line"
    assert src["lines"][1]["end"] == pytest.approx(13.5)     # an empty timestamp ends the previous line
    assert src["lines"][2]["backing"] is True


def test_srt_vtt():
    srt = "1\n00:00:01,000 --> 00:00:02,500\nHello there\n\n2\n00:00:03,000 --> 00:00:04,000\nBob: second line\n\n3\n00:00:05,000 --> 00:00:06,000\nBob: third line\n"
    s = T.parse_srt(srt)
    assert [x["t"] for x in s["lines"]] == [1.0, 3.0, 5.0] and s["lines"][1]["speaker"] == "Bob"
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Zira>One <00:00:01.500>two <00:00:02.000>three\n"
    v = T.parse_vtt(vtt)
    assert v["has_word_sync"] and v["lines"][0]["speaker"] == "Zira"
    assert [w["t"] for w in v["lines"][0]["words"]] == [1.0, 1.5, 2.0]
    assert T.parse_any(vtt, "x.vtt")["format"] == "vtt" and T.parse_any(srt, "x.srt")["format"] == "srt"


def test_txt_headers_repeats_and_speakers():
    txt = "[Verse 1: Newton]\nOne two three\nFour (x2)\n[Chorus]\nla la\n(ooh yeah)\n[Verse 2: Nye]\nNye: five six\n[Chorus]\n(Repeat chorus)\nBob & Ann: last line"
    s = T.parse_txt(txt)
    rows = [(x["text"], x["speaker"], x["backing"]) for x in s["lines"]]
    assert rows[0] == ("One two three", "Newton", False)
    assert rows[1] == rows[2] == ("Four", "Newton", False)                 # (x2)
    assert rows[3] == ("la la", None, False) and rows[4][2] is True        # a section header resets the speaker
    assert rows[5] == ("five six", "Nye", False)
    assert [r[0] for r in rows[6:10]] == ["la la", "(ooh yeah)", "la la", "(ooh yeah)"]   # empty [Chorus] + (Repeat chorus)
    assert rows[-1] == ("last line", "Bob & Ann", False)


def test_lyricsfile_yaml_words():
    y = ("version: '1.0'\nmetadata:\n  title: X\n  duration_ms: 56500\n  language: en\nlines:\n"
         "- text: Paper lanterns\n  start_ms: 9000\n  end_ms: 10970\n  words:\n  - text: 'Paper '\n    start_ms: 9000\n  - text: lanterns\n    start_ms: 9500\n")
    s = T.parse_lyricsfile(y)
    assert s["has_word_sync"] and s["meta"]["language"] == "en"
    assert [w["t"] for w in s["lines"][0]["words"]] == [9.0, 9.5]


@pytest.mark.parametrize("enc,bom", [("utf-8", b"\xef\xbb\xbf"), ("utf-16-le", b"\xff\xfe"), ("utf-16-le", b""), ("cp1252", b"")])
def test_read_text_file_encodings(tmp_path, enc, bom):
    text = "Café line one\nNaïve two\n"
    p = tmp_path / "l.txt"
    p.write_bytes(bom + text.encode(enc))
    got, warn = T.read_text_file(p)
    assert got.replace("\r", "") == text
    assert (warn is not None) == (enc == "cp1252" or (enc == "utf-16-le" and not bom))


def test_display_words_and_tokens():
    dw = T.display_words("— Bob & Ann, 1999 ... 2nd café")
    assert dw[0].startswith("—") and dw[-1] == "café"
    tm = T.TokenMaker({c: i for i, c in enumerate("-aientoutsrmkldghybpwcvjzf'qx")})
    assert len(tm.tokens("1999")) > 10 and len(tm.tokens("&")) == 3 and tm.tokens("...") == []
    assert T.line_key("Don’t STOP, now!") == "dont stop now"


def test_lrclib_cascade_and_ranking():
    from tests.synth.m5.fakehttp import FakeHttp

    fx = json.loads((FIXTURES / "lrclib_synth.json").read_text(encoding="utf-8"))
    rules = [{"method": r["method"], "url_endswith": "/api/" + r["url"].rsplit("/api/", 1)[1],
              "params": r["params"], "exact": True, "status": r["status"], "body": r["body"]} for r in fx["requests"]]
    http = FakeHttp(rules)
    pool, log = LR.query_lrclib(http, title="Lanterns on the Tide", artist="mv-harness fixture", album="Synthetic Sessions", duration_s=56.5)
    assert [x["step"] for x in log] == ["get", "get", "search", "search"]          # ALWAYS search, never get-cached
    assert all("get-cached" not in s["url"] for s in http.seen)
    ranked = LR.rank(pool, title="Lanterns on the Tide", artist="mv-harness fixture", duration_s=56.5)
    ch = LR.choose(ranked)
    assert ch is not None and ch.id == fx["expected_choice"]                      # synced within 2 s beats a closer plain entry
    by = {c.id: c for c in ranked}
    assert by[900001].verdict == "accept_flag" and "version_mismatch" in by[900001].flags   # the /get near miss (2.5 s)
    assert by[900004].verdict == "reject_text"                                     # false friend
    src = LR.candidate_source(ch)
    assert src["has_line_sync"] and len(src["lines"]) == 10


def test_lrclib_far_duration_rejected():
    c = LR.Candidate(1, {"trackName": "A", "artistName": "B", "duration": 120.0, "syncedLyrics": "[00:01.00] x"}, "search")
    r = LR.rank({1: c}, title="A", artist="B", duration_s=100.0)
    assert r[0].verdict == "reject_duration" and LR.choose(r) is None
