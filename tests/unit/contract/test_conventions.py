"""conventions.py against hand-computed values (independent of the golden generator)."""
import math
import random

import pytest

from mvh.contract import conventions as cv

R = list(range(100))  # v[i] = i: easy to compute means by hand


# ---------------------------------------------------------------- frames
def test_frame_of_centred_and_early():
    assert cv.frame_of(1.0, 24) == 24
    assert cv.frame_of(1.0, {"fps": 24, "early": True}) == 24
    assert cv.frame_of(0.0208, 24) == 0            # boundary at 1/48 = 0.0208333
    assert cv.frame_of(0.0209, 24) == 1
    assert cv.frame_of(0.0209, {"fps": 24, "early": True}) == 0
    assert cv.frame_of(0.0, {"fps": 24, "frame0": 1}) == 1
    assert cv.frame_of(1.0, 23.976) == 24           # floor(23.976 + 0.5)
    assert cv.frame_of(1.0, {"fps": 23.976, "early": True}) == 23
    assert cv.frame_of(0.0208, 25) == 1             # frame 0 = [-0.02, 0.02)
    assert cv.frame_of(-0.5, 24) == -12             # negative times map to negative frames


def test_time_of_and_windows():
    assert cv.time_of(25, {"fps": [24000, 1001], "frame0": 1}) == pytest.approx(1.001, abs=1e-12)
    assert cv.time_of(30, 30) == 1.0
    a, b = cv.frame_window(24, 24)
    assert a == pytest.approx(1 - 1 / 48) and b == pytest.approx(1 + 1 / 48)
    a, b = cv.frame_window(24, {"fps": 24, "early": True})
    assert a == pytest.approx(1.0) and b == pytest.approx(1 + 1 / 24)
    assert cv.frame_centre(24, {"fps": 24, "early": True}) == pytest.approx(1 + 1 / 48)


def test_frame_count():
    assert cv.frame_count(10.0, 24) == 240
    assert cv.frame_count(10.0, 23.976) == 240      # 239.76 -> 240
    assert cv.frame_count(316.587, 30) == 9498
    assert cv.frame_count(316.587, 24) == 7599
    assert cv.frame_count(0.0, 24) == 0
    assert cv.n_curve_frames(44100 * 10, 44100) == 1000
    assert cv.n_curve_frames(44100 * 10 + 1, 44100) == 1001
    assert cv.n_curve_frames(48000 * 3, 48000, 1) == 3


@pytest.mark.parametrize("fps", [23.976, [24000, 1001], 24, 25, 29.97, [30000, 1001], 30, 60])
@pytest.mark.parametrize("frame0", [0, 1])
@pytest.mark.parametrize("early", [False, True])
def test_roundtrip(fps, frame0, early):
    fr = {"fps": fps, "frame0": frame0, "early": early}
    for n in range(frame0, frame0 + 20000, 7):
        assert cv.frame_of(cv.time_of(n, fr), fr) == n
        a, b = cv.frame_window(n, fr)
        assert cv.frame_of(a + 1e-7, fr) == n and cv.frame_of(b - 1e-7, fr) == n


# ---------------------------------------------------------------- policies
def test_policies_24fps_centred():
    fr = {"fps": 24}
    assert list(cv.samples_in_frame(0, fr, 100, 100)) == [0, 1, 2]
    assert list(cv.samples_in_frame(1, fr, 100, 100)) == [3, 4, 5, 6]
    assert cv.curve_frame(R, 0, fr, 100, "mean") == pytest.approx(1.0)
    assert cv.curve_frame(R, 1, fr, 100, "mean") == pytest.approx(4.5)
    assert cv.curve_frame(R, 1, fr, 100, "max") == 6
    assert cv.curve_frame(R, 1, fr, 100, "linear") == pytest.approx(100 / 24)
    assert cv.curve_frame(R, 1, fr, 100, "hold") == 4


def test_policies_24fps_early_and_60fps():
    fr = {"fps": 24, "early": True}
    assert list(cv.samples_in_frame(0, fr, 100, 100)) == [0, 1, 2, 3, 4]
    assert cv.curve_frame(R, 0, fr, 100, "mean") == pytest.approx(2.0)
    assert cv.curve_frame(R, 0, fr, 100, "linear") == pytest.approx(100 / 48)
    assert list(cv.samples_in_frame(1, 60, 100, 100)) == [1, 2]
    assert list(cv.samples_in_frame(0, {"fps": 60, "frame0": 1}, 100, 100)) == []   # frame 0 is before the song
    # fps above the curve rate: an empty frame falls back to lerp at the instant
    assert cv.curve_frame(R, 3, 120, 100, "mean") == pytest.approx(2.5)


def test_curve_at_clamps_and_hold():
    assert cv.curve_at(R, -1.0) == 0
    assert cv.curve_at(R, 5.0) == 99
    assert cv.curve_at(R, 0.123) == pytest.approx(12.3)
    assert cv.curve_at(R, 0.124, policy="hold") == 12
    assert cv.curve_at(R, 0.125, policy="hold") == 13       # nearest, half rounds up


def test_flash_rule_all_fps():
    rnd = random.Random(7)
    for _ in range(400):
        t = rnd.uniform(0.05, 9.9)
        lo, hi = cv.flash_samples(t)
        for fps in (23.976, 24, 25, 29.97, 30, 50, 59.94, 60, 100, [24000, 1001]):
            for early in (False, True):
                fr = {"fps": fps, "early": early}
                n = cv.frame_of(t, fr)
                idx = cv.samples_in_frame(n, fr, 100, 1000)
                assert lo in idx or hi in idx, (t, fps, early)


# ---------------------------------------------------------------- NaN-aware pitch
def test_nan_aware():
    v = [60.0, math.nan, 62.0, math.nan, math.nan]
    assert cv.nan_aware_at(v, 0.4) == 60.0              # neighbour unvoiced, nearest voiced
    assert cv.nan_aware_at(v, 0.6) == 60.0              # nearest unvoiced -> hold last voiced
    assert cv.nan_aware_at(v, 1.6) == 62.0              # nearest (2) voiced
    assert cv.nan_aware_at(v, 4.0) == 62.0              # trailing gap holds
    assert cv.nan_aware_at([math.nan, 61.0], 0.0) == 61.0   # leading gap: first voiced after
    assert math.isnan(cv.nan_aware_at([math.nan] * 3, 1.0))
    assert cv.curve_at([math.nan] * 3, 0.01, nan_aware=True) == 0.0
    # mean over a 24 fps frame: voiced samples only
    w = [60.0, 62.0, math.nan, 70.0]
    assert cv.curve_frame(w, 0, 24, 100, "mean", nan_aware=True) == pytest.approx(61.0)
    assert cv.curve_frame(w, 0, 24, 100, "max", nan_aware=True) == 62.0


# ---------------------------------------------------------------- beats and counts
def _beats():
    # pickup beat at 0.25 (bar 0, beat 4), then 4/4 from 0.75, every 0.5 s
    out = [{"beat_index": 0, "t": 0.25, "bar": 0, "beat_in_bar": 4, "beats_in_bar": 4, "in_pulse": True}]
    for i in range(1, 10):
        out.append({"beat_index": i, "t": 0.25 + 0.5 * i, "bar": (i - 1) // 4 + 1, "beat_in_bar": (i - 1) % 4 + 1,
                    "beats_in_bar": 4, "in_pulse": i != 5})
    return out


def test_beat_pos_phase_bar_phase():
    b = _beats()
    assert cv.beat_pos(0.5, b) == {"value": 0.5, "in_pulse": True}
    assert cv.beat_pos(0.0, b) == {"value": -0.5, "in_pulse": False}         # before the grid
    assert cv.beat_pos(4.75 + 0.25, b)["value"] == pytest.approx(9.5)       # after: last IBI
    assert cv.beat_pos(2.6, b)["in_pulse"] is False                          # beats 4-5: beat 5 virtual
    assert cv.beat_phase(1.0, b)["value"] == pytest.approx(0.5)
    assert cv.bar_phase(0.5, b)["value"] == pytest.approx(0.875)            # pickup = tail of bar 0
    assert cv.bar_phase(0.75, b)["value"] == 0.0
    assert cv.bar_phase(1.5, b)["value"] == pytest.approx(0.375)            # beat 2.5 of bar 1
    assert cv.beat_pos(1.0, [])["value"] == 2.0                             # 120 BPM default grid


def test_count():
    b = _beats()
    counts = [{"id": "E000", "start_beat": -3, "len": 4, "first_count": 5, "partial": True, "lead_in": True, "accents": [0, 0, 0, 0.5]},
              {"id": "E001", "start_beat": 1, "len": 8, "first_count": 1, "partial": False, "lead_in": False,
               "accents": [1, .1, .2, .3, .4, .5, .6, .7]}]
    c = cv.count_at(0.75, b, counts)
    assert (c["eight_id"], c["count"], c["sub"], c["phase"], c["accent"]) == ("E001", 1, 0, 0.0, 1)
    c = cv.count_at(1.125, b, counts)                     # beat pos 1.75 -> count 1, sub 3 ("a")
    assert (c["count"], c["sub"]) == (1, 3)
    c = cv.count_at(2.25, b, counts)                      # beat pos 4.0 -> count 4
    assert (c["count"], c["accent"]) == (4, .3)
    c = cv.count_at(0.25, b, counts)                      # the pickup beat is lead-in count 8
    assert (c["eight_id"], c["count"], c["lead_in"]) == ("E000", 8, True)
    c = cv.count_at(-2.0, b, counts)                      # before the lead-in
    assert c["eight_id"] is None and c["count"] is None
    assert cv.SUB_NAMES == ("", "e", "&", "a")


# ---------------------------------------------------------------- events
SEG = [{"id": "A", "t": 0.0, "d": 2.0}, {"id": "B", "t": 1.0, "d": 0.5}, {"id": "C", "t": 3.0, "d": 1.0}]
EV = [{"id": "Q1", "t": 0.0, "tier": 1}, {"id": "Q2", "t": 1.0, "tier": 4}, {"id": "Q3", "t": 1.0, "tier": 2}, {"id": "Q4", "t": 2.0, "tier": 3}]


def test_event_at():
    assert cv.event_at(SEG, 0.5)["item"]["id"] == "A"
    r = cv.event_at(SEG, 1.25)
    assert r["item"]["id"] == "B" and r["progress"] == pytest.approx(0.5) and r["t_left"] == pytest.approx(0.25)
    assert cv.event_at(SEG, 1.5)["item"]["id"] == "A"       # B ended (half-open)
    assert cv.event_at(SEG, 2.5) is None
    assert cv.event_at(EV, 1.0) is None                     # events without d never contain t


def test_next_prev_between_inframe():
    assert cv.event_next(EV, 0.0)["id"] == "Q2"
    assert cv.event_next(EV, 0.0, min_tier=2)["id"] == "Q3"
    assert cv.event_next(EV, 2.0) is None
    assert cv.event_prev(EV, 1.0)["id"] == "Q3"
    assert cv.event_prev(EV, 1.0, min_tier=1)["id"] == "Q1"
    assert cv.event_prev(EV, -0.1) is None
    assert [e["id"] for e in cv.event_between(EV, 0.0, 2.0)] == ["Q1", "Q2", "Q3"]
    assert [e["id"] for e in cv.event_in_frame(EV, 24, 24)] == ["Q2", "Q3"]
    assert [e["id"] for e in cv.event_in_frame(EV, 25, {"fps": 24, "frame0": 1})] == ["Q2", "Q3"]


def test_singer_at_order_and_mouth():
    sg = [{"t": 0, "d": 2, "voice_id": "V3", "character_id": "C3", "line_id": "L003", "lead_backing": "backing"},
          {"t": 0, "d": 2, "voice_id": "V2", "character_id": "C2", "line_id": "L002", "lead_backing": "lead"},
          {"t": 0, "d": 2, "voice_id": "V1", "character_id": "C1", "line_id": "L001", "lead_backing": "lead"},
          {"t": 5, "d": 1, "voice_id": "V1", "character_id": "C1", "line_id": "L004", "lead_backing": "lead"}]
    out = cv.singer_at(1.0, sg, lambda v, t: {"V1": .1, "V2": .2, "V3": .3}[v])
    assert [(x["voice_id"], x["mouth_open"]) for x in out] == [("V1", .1), ("V2", .2), ("V3", .3)]
    assert cv.singer_at(3.0, sg, lambda v, t: 0) == []


# ---------------------------------------------------------------- textures, pulse, osc, spectrum
def test_texture_wrap():
    a = [float(i) for i in range(10)]
    data, h, lay = cv.texture_data([a, [5.0, 6.0]], width=4)
    assert h == 4 and lay[0] == {"row0": 0, "rows": 3, "n": 10, "width": 4} and lay[1]["row0"] == 3
    assert data[:12] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9]          # padding repeats the last value
    assert data[12:16] == [5, 6, 6, 6]
    assert cv.texture_sample(data, lay[0], 0.035) == pytest.approx(3.5)   # across the row wrap (3 -> 4)
    for t in (0.0, 0.031, 0.077, 0.5):
        assert cv.texture_sample(data, lay[0], t) == pytest.approx(cv.curve_at(a, t))


def test_pulse_and_osc():
    hits = [{"t": 1.0}, {"t": 2.0, "strength": 0.5}]
    assert cv.pulse(1.0, hits) == 1.0
    assert cv.pulse(1.25, hits) == pytest.approx(0.01)                    # exp: 1 % after one decay length
    assert cv.pulse(1.125, hits, shape="linear") == pytest.approx(0.5)
    assert cv.pulse(1.95, hits, attack=0.1, shape="linear") == pytest.approx(0.25)   # 0.5 * (1 - 0.05/0.1)
    assert cv.pulse(0.5, hits) == 0.0
    b = [{"t": 0.0, "beat_in_bar": 1, "beats_in_bar": 4, "in_pulse": True}, {"t": 0.5, "beat_in_bar": 2, "beats_in_bar": 4, "in_pulse": True}]
    assert cv.osc(0.0, b) == pytest.approx(1.0)
    assert cv.osc(0.25, b) == pytest.approx(0.0)
    assert cv.osc(0.25, b, "square") == 0.0 and cv.osc(0.1, b, "square") == 1.0
    assert cv.osc(0.125, b, "saw") == pytest.approx(0.75)


def test_spectrum_rows():
    assert cv.spectrum_rows(1.234, 0.0, 500) == [123]
    assert cv.spectrum_rows(1.236, 0.03, 500) == [121, 122, 123, 124]
    assert cv.spectrum_rows(0.0, 0.02, 500) == [None, None, 0]
    assert cv.spectrum_rows(5.0, 0.0, 500) == [None]
