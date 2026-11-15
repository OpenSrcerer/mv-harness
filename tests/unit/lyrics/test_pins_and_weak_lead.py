"""D82 without models: the full vocals stem where the lead stem is weak (vocal_env), and line pins (overrides
``lyrics.pins``) in the anchors, the group alignment and the final enforcement. Synthetic signals and words only."""

from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.lyrics import align as A
from mvh.stages.lyrics import core as C
from mvh.stages.lyrics import vocal_env as VE

SR = 16000


# ------------------------------------------------------------------------------------------------ weak lead
def _noise(seconds: float, level_db: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * SR)) * 10 ** (level_db / 20)).astype(np.float32)


def _song(backing_spans, lead_spans, total=40.0):
    """lead: -20 dB inside lead_spans, -60 dB elsewhere; vocals = lead + backing (-20 dB inside backing_spans)."""
    lead = _noise(total, -60, 1)
    back = _noise(total, -90, 2)
    for a, b in lead_spans:
        lead[int(a * SR):int(b * SR)] = _noise(b - a, -20, 3)
    for a, b in backing_spans:
        back[int(a * SR):int(b * SR)] = _noise(b - a, -20, 4)
    return lead, lead + back


def test_a_group_hook_in_the_backing_stem_is_found():
    lead, voc = _song(backing_spans=[(10, 20)], lead_spans=[(0, 10), (20, 30)])
    reg = VE.weak_lead_regions(lead, voc, SR)
    assert len(reg) == 1 and abs(reg[0][0] - 10) < 1.0 and abs(reg[0][1] - 20) < 1.0
    out = VE.blend_regions(lead, voc, SR, reg)
    mid, verse = slice(12 * SR, 18 * SR), slice(2 * SR, 8 * SR)
    assert np.allclose(out[mid], voc[mid]) and np.allclose(out[verse], lead[verse])
    assert len(out) == len(lead) and out.dtype == np.float32


def test_harmonies_and_short_ad_libs_are_not_a_weak_lead():
    # a backing harmony under the lead (both loud): the lead is not weaker than the vocals by 8 dB
    lead, voc = _song(backing_spans=[(0, 30)], lead_spans=[(0, 30)])
    assert VE.weak_lead_regions(lead, voc, SR) == []
    # a 2 s backing ad-lib while the lead rests: shorter than min_s
    lead, voc = _song(backing_spans=[(12, 14)], lead_spans=[(0, 10), (20, 30)])
    assert VE.weak_lead_regions(lead, voc, SR) == []
    # silence everywhere
    z = np.zeros(5 * SR, np.float32)
    assert VE.weak_lead_regions(z, z, SR) == []


def test_two_runs_close_together_are_one_region():
    lead, voc = _song(backing_spans=[(10, 15), (16, 21)], lead_spans=[(0, 10), (21, 30)])
    reg = VE.weak_lead_regions(lead, voc, SR)
    assert len(reg) == 1 and reg[0][0] < 11 and reg[0][1] > 20


class _Audio:
    def __init__(self, x):
        self.samples, self.sr = x[None, :], SR


class _Ctx:
    def __init__(self, lead, voc):
        self.a = {"lead_vocals": lead, "vocals": voc}

    def audio(self, name, sr=None, mono=True):
        return _Audio(self.a[name])


def test_pick_alignment_signal_names_what_it_used():
    lead, voc = _song(backing_spans=[(10, 20)], lead_spans=[(0, 10), (20, 30)])
    name, x, sr, reg = VE.pick_alignment_signal(_Ctx(lead, voc), SR)
    assert name == "lead_vocals+vocals" and sr == SR and len(reg) == 1 and len(x) == len(lead)
    name, x, sr, reg = VE.pick_alignment_signal(_Ctx(lead, voc), SR, enabled=False)
    assert name == "lead_vocals" and reg == [] and np.array_equal(x, lead)
    name, x, sr, reg = VE.pick_alignment_signal(_Ctx(lead, lead), SR)        # nothing in the backing stem
    assert name == "lead_vocals" and reg == []


# ------------------------------------------------------------------------------------------------ pins: reading
def _ln(*words):
    return {"words": list(words), "text": " ".join(words), "src_t": None, "src_end": None, "src_wt": [None] * len(words)}


def test_read_pins_checks_index_key_and_order():
    lines = [_ln("a1", "a2"), _ln("h1", "h2"), _ln("b1"), _ln("h1", "h2")]
    key = C._pin_key("h1 h2")
    assert key == C._pin_key("H1,  h2!") and key != C._pin_key("b1")            # the normalised text
    warns: list[str] = []
    pins = C._read_pins(lines, {"lyrics.pins": [{"index": 1, "t": 20.0, "key": key, "line": "L002"},
                                                {"index": 3, "t": 60.5}]}, warns)
    assert pins == {1: 20.0, 3: 60.5} and not warns
    assert [bool(x.get("pinned")) for x in lines] == [False, True, False, True]
    warns = []
    lines = [_ln("a1", "a2"), _ln("h1", "h2"), _ln("b1"), _ln("h1", "h2")]
    pins = C._read_pins(lines, {"lyrics.pins": [{"index": 2, "t": 30.0, "key": key},      # the text at 2 is not the hook
                                                {"index": 9, "t": 1.0}, {"index": 0, "t": -1}, {"t": 3.0},
                                                {"index": 1, "t": 50.0}, {"index": 3, "t": 40.0}]}, warns)   # 3 before 1
    assert pins == {1: 50.0} and len(warns) == 2 and "4 lyric pin(s) no longer match" in warns[0] and "earlier" in warns[1]
    assert C._read_pins(lines, {}, []) == {}


# ------------------------------------------------------------------------------------------------ pins: anchors
def _aw(words, t0, step=1.0):
    return [{"n": w, "start": t0 + k * step, "end": t0 + k * step + 0.5} for k, w in enumerate(words)]


def _hook_song():
    """verse a, hook (two lines), verse b, hook again. The ASR heard the verses and only the SECOND pass of the hook."""
    lines = [_ln("a1", "a2", "a3"), _ln("h1", "h2", "h3", "h4"), _ln("k1", "k2"), _ln("b1", "b2", "b3"),
             _ln("h1", "h2", "h3", "h4"), _ln("k1", "k2")]
    aw = _aw(["a1", "a2", "a3"], 10) + _aw(["b1", "b2", "b3"], 40) + _aw(["h1", "h2", "h3", "h4"], 60) + _aw(["k1", "k2"], 64)
    act = np.ones(8000, np.float32)
    return lines, aw, act


def test_without_pins_the_unheard_hook_is_spread_from_the_verse():
    lines, aw, act = _hook_song()
    starts, ends, frac = C._asr_anchors(lines, aw, act, 80.0)
    assert starts[0] == 10.0 and starts[3] == 40.0 and starts[4] == 60.0
    assert starts[1] == pytest.approx(12.5) and frac == pytest.approx(12 / 18)      # right after the verse: too early


def test_a_pin_places_the_hook_and_the_lines_up_to_the_next_anchor():
    lines, aw, act = _hook_song()
    starts, ends, _ = C._asr_anchors(lines, aw, act, 80.0, {1: 20.0})
    assert starts[1] == 20.0
    # the pinned line and the unheard line after it share 20 s .. 40 s (the next anchor) by word count (4 + 2 words)
    assert ends[1] == pytest.approx(20 + 20 * 4 / 6) and starts[2] == pytest.approx(ends[1]) and ends[2] <= 40.0
    assert starts[0] == 10.0 and starts[3] == 40.0 and starts[4] == 60.0             # the heard lines stay
    assert all(e > s for s, e in zip(starts, ends)) and starts == sorted(starts)
    assert [x["src_t"] for x in lines] == starts


def test_an_anchor_on_the_wrong_side_of_a_pin_is_dropped():
    # the ASR heard the hook once, late; the text match gives those words to the FIRST pass (lines 1, 2)
    lines, _aw_all, act = _hook_song()
    aw = _aw(["a1", "a2", "a3"], 10) + _aw(["h1", "h2", "h3", "h4"], 60) + _aw(["k1", "k2"], 64)
    starts, _e, _f = C._asr_anchors(lines, aw, act, 80.0)
    assert starts[1] == 60.0                                                          # the first pass sits on the second
    starts, ends, _f = C._asr_anchors(lines, aw, act, 80.0, {4: 60.0})                # the user pins the second pass
    assert starts[4] == 60.0 and starts[1] < 60.0 and starts[2] < 60.0 and starts[3] < 60.0
    assert starts == sorted(starts) and ends[3] <= 60.0


def test_pin_source_times_for_a_synced_source():
    lines = [_ln("a"), _ln("h", "i"), _ln("k"), _ln("b")]
    for x, t in zip(lines, (10.0, 100.0, 104.0, 40.0)):                               # the hook's source times are wrong
        x["src_t"], x["src_end"], x["src_wt"] = t, t + 2.0, [t + 0.1 * k for k in range(len(x["words"]))]
    C._pin_source_times(lines, {1: 20.0, 3: 40.0}, 120.0)
    assert lines[1]["src_t"] == 20.0 and lines[1]["src_end"] == 22.0 and lines[1]["src_wt"] == pytest.approx([20.0, 20.1])
    assert lines[2]["src_t"] == pytest.approx(30.0) and lines[2]["src_wt"] == [None]  # 104 s is past the next pin: re-spread
    assert lines[0]["src_t"] == 10.0 and lines[3]["src_t"] == 40.0


# ------------------------------------------------------------------------------------------------ pins: alignment
def _emissions(n_frames: int, plan: dict[int, tuple[list[int], float]]) -> np.ndarray:
    """log-probs with blank everywhere except the listed frames: {frame: (tokens, log-prob of each token)}."""
    lp = np.full((n_frames, 29), -8.0, np.float32)
    lp[:, 0] = -0.01
    for f, (toks, p) in plan.items():
        for j, t in enumerate(toks):
            lp[f + 2 * j:f + 2 * j + 2, t] = p
            lp[f + 2 * j:f + 2 * j + 2, 0] = -8.0
    return lp


def test_a_pinned_line_cannot_start_before_its_pin():
    # line 1's tokens sound at 13.0 s (strongly: the tail of something else) and at 14.0 s (where it is sung)
    lp = _emissions(1000, {500: ([3, 4], -0.01), 650: ([5, 6], -0.01), 700: ([5, 6], -0.6)})
    toks = [[[3, 4]], [[5, 6]]]
    res, _n = A.align_groups(lp, [10.0, 14.0], [11.0, 15.0], toks)
    assert res[1][0]["start"] == pytest.approx(13.0, abs=0.03)
    res, _n = A.align_groups(lp, [10.0, 14.0], [11.0, 15.0], toks, pins=[False, True])
    assert res[0][0]["start"] == pytest.approx(10.0, abs=0.03) and res[1][0]["start"] == pytest.approx(14.0, abs=0.03)


def test_the_global_offset_does_not_move_a_pin():
    lp = _emissions(1500, {500: ([3, 4], -0.01)})
    res, _n = A.align_groups(lp, [10.0], [11.0], [[[3, 4]]], offset=6.0, ctx=0.5, slack=0.5, pins=[True])
    assert res[0][0]["start"] == pytest.approx(10.0, abs=0.03)
    res, _n = A.align_groups(lp, [10.0], [11.0], [[[3, 4]]], offset=6.0, ctx=0.5, slack=0.5)
    assert res[0][0]["start"] > 15.0                                                   # unpinned: the window moved away


def test_no_pins_is_the_old_behaviour():
    lp = _emissions(1000, {500: ([3, 4], -0.01), 650: ([5, 6], -0.01)})
    toks = [[[3, 4]], [[5, 6]]]
    a, na = A.align_groups(lp, [10.0, 13.0], [11.0, 14.0], toks, offset=0.2)
    b, nb = A.align_groups(lp, [10.0, 13.0], [11.0, 14.0], toks, offset=0.2, pins=[False, False])
    assert a == b and na.as_dict() == nb.as_dict()


def _w(start, dur=0.3):
    return {"start": start, "end": start + dur, "score": 0.9, "tok_scores": [0.9]}


def test_enforce_pins_is_a_fixed_point():
    lines = [{"wres": [_w(5.0), _w(5.5)], "src_t": 5.0},
             {"wres": [_w(31.0), None, _w(32.0)], "src_t": 20.0},        # pinned at 20: landed 11 s late
             {"wres": [_w(18.0)], "src_t": 24.0},                         # between the pins but before the first
             {"wres": [_w(40.1), _w(41.0)], "src_t": 40.0},               # pinned at 40: within the tolerance
             {"wres": [None], "src_t": 50.0}]
    moved = C._enforce_pins(lines, {1: 20.0, 3: 40.0}, n_src=5)
    assert moved == 2
    assert [r["start"] for r in lines[1]["wres"] if r] == pytest.approx([20.0, 21.0])
    assert lines[1]["wres"][1] is None and lines[1]["wres"][0]["end"] == pytest.approx(20.3)
    assert lines[2]["wres"][0]["start"] == pytest.approx(24.0)            # moved to its expected start
    assert lines[3]["wres"][0]["start"] == pytest.approx(40.1)            # the aligner's snap is kept
    assert lines[0]["wres"][0]["start"] == 5.0
    assert C._enforce_pins(lines, {1: 20.0, 3: 40.0}, n_src=5) == 0


def test_pin_bounds_stop_at_the_pins():
    b = C._pin_bounds([(0.0, 30.0), (10.0, 70.0), (15.0, 90.0), (50.0, 99.0)], {1: 20.0, 3: 60.0})
    assert b[0] == (0.0, pytest.approx(20.0 + A.SEAM_MARGIN_S))
    assert b[1] == (pytest.approx(20.0 - A.PIN_TOL), pytest.approx(60.0 + A.SEAM_MARGIN_S))
    assert b[2][0] == pytest.approx(20.0 - A.PIN_TOL) and b[3] == (pytest.approx(60.0 - A.PIN_TOL), 99.0)


# ------------------------------------------------------------------------------------------------ contract
def test_pins_are_an_override_of_the_lyrics_stage():
    from mvh.contract import catalog
    from mvh.runner.spec import load_stage_specs

    assert catalog.OVERRIDE_KEYS["lyrics.pins"] == "lyrics"
    assert "lyrics.pins" in load_stage_specs()["lyrics"].override_keys
    item = catalog.OVERRIDES["properties"]["lyrics"]["properties"]["pins"]["items"]
    assert item["required"] == ["index", "t"] and set(item["properties"]) == {"index", "t", "key", "line"}
    line = catalog.FILE_SCHEMAS["files/lyrics"]["properties"]["lines"]["items"]
    assert {"source_index", "pin_key", "pinned"} <= set(line["properties"]) and "pinned" not in line["required"]
