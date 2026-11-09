"""W4 R-ADVERSARY re-checks of the open W3 seams, on the NEWEST max run of each song (post-UD2 when present).

Each test is the evidence of one finding in docs/review/W4-adversary.md. Numbers only, never lyric text.

* W4A-VOCPHR (M3b vocals, was S04 "fixed"): MEGAFAUNA's vocal phrases cover 7.5 s of the 39.7 s of lyric-line time
  in which the vocals stem is active (stem_activity). The vocals stem is active 54-88 % of S08/S09/S12/S13 and the
  lines cover 53-100 %, yet the brief's vocals column says 8-21 %: the phrase / breath timing an agent animates from
  is missing for most of the singing.
* W4A-BACKING (M5 voices, S16): Newton's only BACKING voice span (V1 under V3, L021, 1.97 s, conf 0.68) is 22 %
  supported by backing_vocals stem activity (a 0.59 s burst); the rest opens a second mouth for 2.1 s with no backing
  voice in the stem.
* W4A-GROOVE (M2 choreo + M3a drums, S17), W4A-FEEL (M2 rhythm, S18), W4A-HATS (M3a drums, S19): still real after UD2.
"""

from __future__ import annotations

import bisect
from collections import Counter

import numpy as np


def _cov(a: float, b: float, segs) -> float:
    return sum(max(0.0, min(b, q["t"] + q["d"]) - max(a, q["t"])) for q in segs)


def test_w4a_vocal_phrases_cover_the_sung_lines_megafauna(real_folder):
    f = real_folder("megafauna")
    lines = f.json("lyrics/lyrics.json")["lines"] if f.has("lyrics/lyrics.json") else []
    assert len(lines) >= 5
    voc = [x for x in f.events("stem_activity") if x["stem"] == "vocals"]
    vp = f.events("vocal_phrases")
    # line time in which the vocals stem is active (independent of the vocals stage)
    sung = []
    for ln in lines:
        for s in voc:
            a, b = max(ln["t"], s["t"]), min(ln["t"] + ln["d"], s["t"] + s["d"])
            if b > a:
                sung.append({"t": a, "d": b - a})
    sung_s = sum(x["d"] for x in sung)
    assert sung_s >= 10.0, f"control: only {sung_s:.1f} s of line time with an active vocals stem"
    in_vp = sum(_cov(x["t"], x["t"] + x["d"], vp) for x in sung)
    share = in_vp / sung_s
    assert share >= 0.5, (f"megafauna: vocal_phrases cover {in_vp:.1f} s of the {sung_s:.1f} s of lyric-line time in which "
                          f"the vocals stem is active ({share:.0%}); {len(vp)} phrases, "
                          f"{sum(v['d'] for v in vp):.1f} s in all")


def test_w4a_backing_spans_are_backed_by_the_backing_stem_newton(real_folder):
    f = real_folder("newton-vs-nye")
    bv = [x for x in f.events("stem_activity") if x["stem"] == "backing_vocals"]
    spans = [v for v in f.events("voice_spans") if v.get("role") == "backing"]
    bad = []
    for v in spans:
        sup = _cov(v["t"], v["t"] + v["d"], bv) / max(1e-9, v["d"])
        if sup < 0.5 and v["d"] >= 0.75:
            bad.append((v["line_id"], v["voice_id"], round(v["t"], 2), round(v["d"], 2), round(sup, 2)))
    assert not bad, (f"newton-vs-nye: backing voice spans mostly without backing_vocals stem activity "
                     f"(line, voice, t, d, stem-supported share): {bad}")


def test_w4a_groove_ids_repeat_on_noisy_kits(real_folder):
    for slug in ("megafauna", "versatile"):
        f = real_folder(slug)
        gr = f.events("grooves")
        ids = Counter(g["groove_id"] for g in gr)
        sk = Counter((tuple(i for i, v in enumerate(g["pattern"]["kick"]) if v > 0),
                      tuple(i for i, v in enumerate(g["pattern"]["snare"]) if v > 0)) for g in gr)
        assert len(ids) / len(gr) <= 0.35, (f"{slug}: {len(ids)} groove ids for {len(gr)} bars; the kick/snare rows "
                                            f"alone give {len(sk)} distinct step patterns (transcription noise feeds the ids)")


def _beat_index(beats, t, tol=0.05):
    bt = [b["t"] for b in beats]
    i = bisect.bisect_left(bt, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(bt) and abs(bt[j] - t) <= tol and (best is None or abs(bt[j] - t) < abs(bt[best] - t)):
            best = j
    return None if best is None else beats[best]


def test_w4a_half_time_backbeat_is_labelled_newton(real_folder):
    f = real_folder("newton-vs-nye")
    beats = f.events("beats")
    c = Counter()
    for h in f.events("drum_hits"):
        if h["drum"] != "snare" or h["vel"] < 0.3:
            continue
        b = _beat_index(beats, h["t"])
        if b and b.get("in_pulse") and b.get("beats_in_bar") == 4:
            c[b["beat_in_bar"]] += 1
    n = sum(c.values())
    assert n >= 40
    tempo = f.json("meta/tempo.json")
    if c[3] / n >= 0.6 and (c[2] + c[4]) / n <= 0.3:
        half = (tempo.get("feel_shares") or {}).get("half_time", 0.0)
        assert tempo["feel"] == "half_time" or half >= 0.5, (
            f"newton-vs-nye: {c[3] / n:.0%} of {n} strong snares on beat 3 at {tempo['bpm']:.1f} BPM, feel={tempo['feel']!r}")


def test_w4a_jeremy_hats_lock_to_the_grid(real_folder):
    f = real_folder("jeremy")
    beats = f.events("beats")
    bt = np.array([b["t"] for b in beats])
    n = ok = 0
    for h in f.events("drum_hits"):
        if h["drum"] != "hat" or h["vel"] < 0.3:
            continue
        k = int(np.searchsorted(bt, h["t"], side="right")) - 1
        if k < 0 or k + 1 >= len(bt) or not (beats[k]["in_pulse"] and beats[k + 1]["in_pulse"]):
            continue
        x = (h["t"] - bt[k]) / (bt[k + 1] - bt[k]) * 4
        n += 1
        ok += abs(x - round(x)) / 4 <= 1 / 32
    assert n >= 100
    assert ok / n >= 0.6, f"jeremy: {ok / n:.0%} of {n} hats (vel >= 0.3) within 1/32 beat of a 16th (chance 25 %)"
