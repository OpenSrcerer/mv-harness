"""W3 round-1 fixes (fixer-m5-r3): header / speaker-marker parsing, the generic-outro second signal, the VAD-gap
regions and the mutual-span G1 helpers. Synthetic text only; fast (no models)."""

from __future__ import annotations

import numpy as np

from mvh.stages.lyrics import asr as R
from mvh.stages.lyrics import core as C
from mvh.stages.lyrics import text as T


def test_section_word_any_position():
    assert T._section_word("Final Chorus") == "chorus"
    assert T._section_word("Pre Chorus") == "pre-chorus"
    assert T._section_word("Post-Chorus 2") == "post-chorus"
    assert T._section_word("Verse1") == "verse"
    assert T._section_word("Bill Nye") is None


def test_plain_headers_and_markers():
    assert T._header("VERSE 2")[:3] == (True, None, "verse")
    assert T._header("Chorus x3") == (True, None, "chorus", 3)
    assert T._header("(Chorus)")[:3] == (True, None, "chorus")
    assert T._header("Verse 2: Bill Nye")[:3] == (True, "Bill Nye", "verse")
    # a lone 'Name:' line is only a marker CANDIDATE; the file accepts the set (M5-D54, see test_r4_fixes.py)
    assert T._lone_marker("Neil deGrasse Tyson:") == "Neil deGrasse Tyson"
    assert T._header("Neil deGrasse Tyson:")[0] is False
    assert T._header("[Bill Nye:]")[:2] == (True, "Bill Nye")
    for lyric in ("Chorus of angels in the night", "Time: it slips away", "And then she said:", "Tell me why:"):
        assert T._header(lyric)[0] is False, lyric


def test_battle_with_name_lines_parses_hints():
    txt = "Newton:\nline a one\nline a two\nNye:\nline b one\nNewton:\nline c one"
    s = T.parse_txt(txt)
    assert [x["speaker"] for x in s["lines"]] == ["Newton", "Newton", "Nye", "Newton"]
    assert len(s["lines"]) == 4


def test_single_bare_name_header_does_not_label_file():
    # one recurring bare name is not enough to call the file labelled (>= 2 distinct names needed)
    assert T._file_labelled("[Ad-libs]\nla la\n[Ad-libs]\nla la la") is False
    assert T._file_labelled("[Ann]\none\n[Bob]\ntwo\n[Ann]\nthree") is True


def _seg(text, ns, lp):
    ws = text.split()
    return {"start": 60.0, "end": 60.0 + 0.4 * len(ws), "text": " " + text, "avg_logprob": lp, "no_speech_prob": ns,
            "compression_ratio": 1.2,
            "words": [{"w": " " + w, "start": 60.0 + 0.4 * i, "end": 60.3 + 0.4 * i, "p": 0.9} for i, w in enumerate(ws)]}


def test_generic_phrase_needs_weak_logprob_with_no_speech():
    act = np.ones(18000, np.float32)
    assert R.filter_segments([_seg("bye bye bye", 0.7, -0.3)], act, 100.0, 0.25)[0]       # confident sung: kept
    assert not R.filter_segments([_seg("bye bye bye", 0.7, -0.8)], act, 100.0, 0.25)[0]   # no-speech + weak: dropped
    assert not R.filter_segments([_seg("bye bye bye", 0.1, -1.2)], act, 100.0, 0.25)[0]   # very weak alone: dropped


def test_uncovered_regions():
    act = np.zeros(30000, np.float32)
    act[1000:5000] = 1           # 10-50 s sung, ASR covers 10-30 s
    act[20000:20300] = 1         # a 3 s blip: too short
    segs = [{"start": 10.0, "end": 30.0}]
    reg = R.uncovered_regions(segs, act, 100.0, min_s=6.0)
    assert len(reg) == 1 and abs(reg[0][0] - 30.51) < 0.02 and abs(reg[0][1] - 50.0) < 0.02
    assert R.uncovered_regions([{"start": 0.0, "end": 300.0}], act, 100.0) == []


def test_mutual_span_helpers():
    sp = C._merge_spans([(5.0, 7.0), (1.0, 3.0), (2.5, 4.0)])
    assert sp == [(1.0, 4.0), (5.0, 7.0)]
    assert C._inside(3.5, sp) and not C._inside(4.5, sp)


def test_canonicalise_snaps_near_misses_in_time_only():
    ref = [(10.0, "lanterns"), (10.5, "over"), (11.0, "river"), (40.0, "harbour")]
    aw = [{"n": "lantern", "start": 10.1}, {"n": "over", "start": 10.6}, {"n": "rivers", "start": 11.1},
          {"n": "harbor", "start": 12.0}, {"n": "cat", "start": 11.2}]
    out, n = R.canonicalise(aw, ref)
    assert out == ["lanterns", "over", "river", "harbor", "cat"] and n == 2   # 'harbor' is 28 s from 'harbour'
    assert R.match_score(out, [r for _, r in ref])["lcs_matched"] == 3
