"""W3 round-2 fixes (fixer-m5-r4): lone 'Name:' marker lines are decided per file (M5-D54), the header long tail
(r4-m1) and joint speaker labels (r4-m2, M5-D55). Synthetic text only; fast (no models)."""

from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import text as T
from mvh.stages.voices.core import hint_parts


def _texts(src):
    return [ln["text"] for ln in src["lines"]]


def _hints(src):
    return [ln["speaker"] for ln in src["lines"]]


def test_colon_lyric_lines_stay_sung():
    story = "Mary told the crowd:\nwe are going home tonight\nall the lights are low\nThen Mary sang:\nhold me close again"
    s = T.parse_txt(story)
    assert len(s["lines"]) == 5 and not any(_hints(s))
    title = "Hold Me Close:\nUnder The Silver Moon\nCarry Me Home:\nAcross The Open Sea"
    s = T.parse_txt(title)
    assert len(s["lines"]) == 4 and not any(_hints(s))


def test_chorus_line_with_colon_written_twice_stays_sung():
    # the colon line recurs, but with the SAME line after it each time: a repeated lyric, not a speaker
    body = "Hold On Tight:\nnever let me go\nwalking on\nHold On Tight:\nnever let me go\nRun Away:\nfar from here"
    s = T.parse_txt(body)
    assert len(s["lines"]) == 7 and not any(_hints(s))


def test_duet_markers_once_each_in_sentence_case():
    s = T.parse_txt("Ann Lee:\nwe walk along the river\nthe night is cold\nBob Ray:\nand I will follow you")
    assert _hints(s) == ["Ann Lee", "Ann Lee", "Bob Ray"]


def test_markers_in_synced_lrc():
    names = ["Ann", "Bob", "Ann"]
    rows, t = [], 10
    for n in names:
        rows += [f"[00:{t:02d}.00]{n}:", f"[00:{t + 1:02d}.00]line by {n.lower()} {t}"]
        t += 3
    s = T.parse_lrc("\n".join(rows))
    assert _hints(s) == names and len(s["lines"]) == 3


@pytest.mark.parametrize("hdr,sec", [("*Chorus*", "chorus"), ("Chorus (repeat)", "chorus"), ("1st Verse:", "verse"),
                                     ("2nd Verse", "verse"), ("**Bridge**", "bridge")])
def test_header_long_tail(hdr, sec):
    assert T._header(hdr)[:3] == (True, None, sec)


def test_dash_and_paren_speaker_headers():
    assert T._header("[Verse 1 - Isaac Newton]")[:3] == (True, "Isaac Newton", "verse")
    assert T._header("Verse 2 - Bill Nye")[:3] == (True, "Bill Nye", "verse")
    assert T._header("Isaac Newton (Verse 1):")[:3] == (True, "Isaac Newton", "verse")
    assert T._header("[Intro: Spoken]")[1] is None
    # a sung line with a dash stays sung
    assert T._header("Chorus girls - dancing in the rain")[0] is False


def test_chorus_repeat_reinserts_block():
    s = T.parse_txt("Chorus:\nsing it loud\nsing it proud\nVerse 2:\nnew words here\nChorus (repeat)")
    assert _texts(s) == ["sing it loud", "sing it proud", "new words here", "sing it loud", "sing it proud"]


def test_lone_repeat_line_repeats_previous_line():
    s = T.parse_txt("one more time\n(x2)\nand then we go")
    assert _texts(s) == ["one more time", "one more time", "and then we go"]


def test_five_word_marker_name():
    body = "Bill Nye the Science Guy:\nline one\nIsaac Newton:\nline two\nBill Nye the Science Guy:\nline three"
    s = T.parse_txt(body)
    assert _hints(s) == ["Bill Nye the Science Guy", "Isaac Newton", "Bill Nye the Science Guy"]


def test_hint_parts():
    assert hint_parts("Ann") == ["Ann"]
    assert hint_parts("Ann & Bob") == ["Ann", "Bob"]
    assert hint_parts("Ann and Bob") == ["Ann", "Bob"]
    assert hint_parts("Ann, Bob + Cy") == ["Ann", "Bob", "Cy"]
    assert hint_parts("Both") == [] and hint_parts("All") == [] and hint_parts(None) == []
    assert hint_parts("Malcolm X") == ["Malcolm X"]


# r4-m4: the near-miss rule (M5-D53) must not lift a PARTLY different version towards the 0.70 G1 threshold
_VOCAB = ("river night morning silver window garden shadow thunder candle letter mirror summer winter people "
          "golden broken hollow yellow little middle simple trouble double heaven seven dragon wonder").split()
_OTHER = ("castle rocket planet engine marble pocket jacket basket ticket forest desert island harbor tunnel "
          "violin pepper ginger copper butter number").split()


def test_near_miss_does_not_lift_a_partly_different_version():
    from mvh.stages.lyrics import asr as R

    rng = np.random.default_rng(7)
    ref, aw, t = [], [], 0.0
    for li in range(40):
        line = [str(rng.choice(_VOCAB)) for _ in range(6)]
        sung = [str(rng.choice(_OTHER)) for _ in range(6)] if li % 5 == 4 else line   # every 5th line differs
        for a, b in zip(line, sung):
            ref.append((t, a))
            aw.append({"n": b, "start": t})
            t += 0.5
        t += 1.0
    exact = R.match_score([w["n"] for w in aw], [n for _, n in ref])["f1"]
    canon, n_snap = R.canonicalise(aw, ref)
    snapped = R.match_score(canon, [n for _, n in ref])["f1"]
    assert snapped - exact < 0.03, (exact, snapped, n_snap)
