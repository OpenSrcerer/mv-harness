# ruff: noqa: E501
"""lyrics mechanics without models: the vendored CTC Viterbi against torchaudio (golden), alignment windows on
synthetic emissions, the G1-G8 gate and grades, the hallucination filter and match score, and the exports."""

from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import align as A
from mvh.stages.lyrics import asr as R
from mvh.stages.lyrics import ctc_viterbi as V
from mvh.stages.lyrics import exports as X
from mvh.stages.lyrics import grade as G


def _logsoftmax(x):
    return x - np.log(np.exp(x).sum(1, keepdims=True))


def test_vendored_viterbi_matches_torchaudio():
    torch = pytest.importorskip("torch")
    F = pytest.importorskip("torchaudio.functional")
    rng = np.random.default_rng(7)
    n = 0
    for k in range(40):
        T_, C = int(rng.integers(20, 300)), 29
        L = int(rng.integers(1, max(2, T_ // 3)))
        tg = rng.integers(1, C, L)
        if k % 3 == 0:
            tg[1::2] = tg[0::2][: len(tg[1::2])]           # repeated tokens need a blank in between
        lp = _logsoftmax(rng.normal(size=(T_, C)) * 3).astype(np.float32)
        try:
            a, s = F.forced_align(torch.from_numpy(lp)[None], torch.tensor([tg.tolist()], dtype=torch.int32), blank=0)
        except Exception:  # noqa: BLE001  (infeasible for both)
            with pytest.raises(ValueError):
                V.forced_align(lp, tg)
            continue
        path, sc = V.forced_align(lp, tg)
        assert np.array_equal(path, a[0].numpy())
        assert float(sc.sum()) == pytest.approx(float(s[0].sum()), abs=1e-3)
        n += 1
    assert n >= 30


def test_merge_tokens_spans():
    path = np.array([0, 3, 3, 0, 3, 5, 5, 0])
    sp = V.merge_tokens(path, np.ones(8) * 0.5)
    assert [(s.token, s.start, s.end) for s in sp] == [(3, 1, 3), (3, 4, 5), (5, 5, 7)]


def test_align_window_on_synthetic_emissions():
    # 3 "words" whose tokens are loud at known frames: the alignment must find them
    T_, C = 300, 29
    lp = np.full((T_, C), -8.0, np.float32)
    lp[:, 0] = -0.01
    plan = {50: [3, 4], 150: [5, 6, 7], 240: [8]}
    for f, toks in plan.items():
        for j, t in enumerate(toks):
            lp[f + 2 * j:f + 2 * j + 2, t] = -0.01
            lp[f + 2 * j:f + 2 * j + 2, 0] = -8.0
    res = A.align_window(lp, 0, T_, [plan[50], plan[150], plan[240]])
    assert [round(r["start"] / A.FR) for r in res] == [50, 150, 240]
    assert all(r["score"] > 0.9 for r in res)
    with pytest.raises(ValueError):
        A.align_window(lp, 0, 3, [[3, 4], [5, 6]])


def test_groups_split_on_span_and_gap():
    g = A.groups([0, 5, 10, 40, 41], [5, 10, 14, 41, 45])
    assert g == [[0, 1, 2], [3, 4]]


def test_gate_grades():
    base = {"G1": 0.85, "G2": 0.9, "G3": 0.4, "G4": 0.02, "G5": 0.9, "offset_s": -1.33,
            "G7": {"within_250ms": 0.9, "bias_s": 0.1}, "G8": 1.3}
    assert G.gate(base)["grade"] == "A"
    assert G.gate({**base, "G1": 0.76})["grade"] == "B"                           # jeremy-like
    assert G.gate({**base, "G3": 0.2, "G5": 0.5})["grade"] == "C"
    assert G.gate({**base, "G1": 0.5})["grade"] == "D"                            # G1 never alone
    assert G.gate({**base, "G2": 0.55})["grade"] == "D"
    # M5-D20: G1 needs ASR evidence
    few = G.gate({**base, "G1": 0.0, "asr_words": 2, "asr_mean_p": 0.5})
    assert few["checks"]["G1"]["pass"] is None and few["checks"]["G1"]["note"] == "asr_insufficient" and few["grade"] == "B"
    weak = G.gate({**base, "G1": 0.53, "asr_words": 75, "asr_mean_p": 0.64})
    assert weak["checks"]["G1"]["pass"] is False and weak["checks"]["G1"]["note"] == "asr_unreliable" and weak["grade"] == "C"
    assert G.gate({**base, "G1": 0.53, "asr_words": 75, "asr_mean_p": 0.9})["grade"] == "D"   # confident ASR: wrong text
    g = G.gate({**base, "G5": None, "G7": {"within_250ms": 0.1, "bias_s": 0.9}})
    assert g["checks"]["G5"]["pass"] is None and g["checks"]["G7"]["pass"] is None   # not applicable, not failed
    assert g["checks"]["G6"]["applied"] and not g["checks"]["G6"]["version_mismatch"]
    assert G.gate({**base, "offset_s": 3.5})["checks"]["G6"]["version_mismatch"]
    t = G.gate({"G2": 0.95, "G3": 0.5, "G4": 0.0, "transcribed": True, "asr_mean_p": 0.9})
    assert t["grade"] == "B" and G.gate({"G2": 0.95, "G3": 0.5, "G4": 0.0, "transcribed": True, "asr_mean_p": 0.5})["grade"] == "D"


def test_onset_lift_and_agreement():
    on = np.arange(0, 60, 0.5)
    assert G.onset_lift(on, on[::3] + 0.01) > 1.5
    ag = G.asr_agreement([(t + 0.3, t) for t in np.arange(0, 10, 1.0)])
    assert ag["bias_s"] == pytest.approx(0.3) and ag["within_250ms"] == 1.0 and ag["within_250ms_raw"] == 0.0


def _seg(text, t0, t1, p=0.9, **kw):
    ws = text.split()
    step = (t1 - t0) / len(ws)
    return {"start": t0, "end": t1, "text": " " + text, "avg_logprob": kw.get("lp", -0.2), "no_speech_prob": kw.get("ns", 0.1),
            "compression_ratio": kw.get("cr", 1.2), "words": [{"w": " " + w, "start": t0 + i * step, "end": t0 + (i + 1) * step, "p": p} for i, w in enumerate(ws)]}


def test_hallucination_filter():
    segs = [_seg("paper lanterns over the river", 1, 3), _seg("[Music]", 4, 5), _seg("la la la la la la la la", 6, 8),
            _seg("thanks for watching", 9, 10), _seg("ok fine words here", 11, 12, p=0.1),
            _seg("quiet words in reverb", 20, 22), _seg("the music of the night", 30, 32)]
    act = np.zeros(4000, np.float32)
    act[100:1300] = 1
    act[3000:3300] = 1
    kept, dropped = R.filter_segments(segs, act, 100.0, min_word_p=0.25)
    texts = [s["text"].strip() for s in kept]
    assert texts == ["paper lanterns over the river", "the music of the night"]      # 'music' inside a lyric survives
    assert dropped.get("non_lyric_tag") == 2 and dropped.get("ngram_loop", 0) + dropped.get("low_unique_ratio", 0) == 1
    assert dropped.get("low_word_prob") == 1 and dropped.get("inactive_vocals") == 1


def test_match_score():
    m = R.match_score("a b c d".split(), "a b x d e".split())
    assert m["lcs_matched"] == 3 and m["precision"] == 0.75 and m["recall"] == 0.6
    assert R.match_score([], ["a"])["f1"] == 0.0


def test_exports():
    lines = [{"id": "L001", "t": 9.0, "d": 1.97, "text": "Paper lanterns", "backing": False, "speaker_hint": "Ann"},
             {"id": "L002", "t": 12.0, "d": 1.0, "text": "(ooh)", "backing": True, "speaker_hint": None}]
    words = [{"id": "L001.01", "line_id": "L001", "t": 9.0, "d": 0.47, "text": "Paper", "conf": 1},
             {"id": "L001.02", "line_id": "L001", "t": 9.5, "d": 1.47, "text": "lanterns", "conf": 1},
             {"id": "L002.01", "line_id": "L002", "t": 12.0, "d": 1.0, "text": "(ooh)", "conf": 1}]
    meta = {"title": "T", "artist": "A", "album": "B", "duration_s": 56.5}
    lrc = X.to_lrc(meta, lines, words)
    assert "[00:09.00] <00:09.00> Paper <00:09.50> lanterns <00:10.97>" in lrc and "[length:00:56.50]" in lrc
    vtt = X.to_vtt(lines, words)
    assert vtt.startswith("WEBVTT") and "00:00:09.000 --> 00:00:10.970" in vtt and "<v Ann>Paper <00:00:09.500>lanterns" in vtt
    srt = X.to_srt(lines)
    assert "00:00:09,000 --> 00:00:10,970" in srt
    ass = X.to_ass(meta, lines, words)
    assert "{\\k47}Paper {\\k3}{\\k147}lanterns" in ass and ",Backing," in ass
    from mvh.stages.lyrics import text as T

    back = T.parse_lrc(lrc)
    assert [round(w["t"], 2) for w in back["lines"][0]["words"]] == [9.0, 9.5]           # the LRC round-trips
