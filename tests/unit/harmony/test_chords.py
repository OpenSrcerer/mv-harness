import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.synth import m4  # noqa: E402

from mvh.stages.harmony import chords as C  # noqa: E402
from mvh.stages.harmony import core  # noqa: E402
from mvh.stages.harmony.chroma import compute_chroma  # noqa: E402

BEATS = [{"t": round(i * 0.5, 3), "beat_index": i, "in_pulse": True} for i in range(40)]


def _acc(truth, mine, t0=0.2, t1=None, step=0.05, field=("root_pc", "quality")):
    t1 = t1 or max(c["t"] + c["d"] for c in truth) - 0.6
    ok = n = 0
    for t in np.arange(t0, t1, step):
        a = next(c for c in truth if c["t"] <= t < c["t"] + c["d"])
        b = next((c for c in mine if c["t"] <= t < c["t"] + c["d"]), None)
        n += 1
        ok += b is not None and all(a[f] == b[f] for f in field)
    return ok / n


def test_segs_from_lv_cover_the_song_and_parse_inversions():
    segs = C.segs_from_lv([{"start_time": 0.5, "end_time": 3.0, "chord": "D:maj/5"}, {"start_time": 3.0, "end_time": 6.0, "chord": "Bb:min"},
                           {"start_time": 7.0, "end_time": 9.0, "chord": "N"}], 10.0)
    assert segs[0].label == "N" and segs[0].t == 0.0 and abs(segs[0].d - 0.5) < 1e-9          # lead-in is N
    assert (segs[1].root, segs[1].quality, segs[1].bass) == (2, "maj", 9) and segs[1].label == "D:maj"
    assert segs[2].label == "Bb:min" and segs[2].root == 10                                  # lv spelling kept
    assert abs(sum(s.d for s in segs) - 10.0) < 1e-9
    assert all(abs(a.end - b.t) < 1e-9 for a, b in zip(segs, segs[1:]))


def test_snap_to_beats_moves_boundaries_and_drops_collapsed_segments():
    raw = [C.Seg(0.0, 1.07, 0, "maj", None, "C:maj"), C.Seg(1.07, 0.06, 7, "maj", None, "G:maj"), C.Seg(1.13, 1.88, 9, "min", None, "A:min"),
           C.Seg(3.01, 2.0, 5, "maj", None, "F:maj")]
    out = C.snap_to_beats(raw, BEATS, 5.01)
    # 1.07 and 1.13 both snap to 1.0: the 60 ms G chord collapses
    assert [s.label for s in out] == ["C:maj", "A:min", "F:maj"]
    assert [round(s.t, 3) for s in out] == [0.0, 1.0, 3.0]
    assert abs(out[-1].end - 5.01) < 1e-9


def test_snap_merges_equal_neighbours_and_keeps_far_boundaries():
    raw = [C.Seg(0.0, 1.0, 0, "maj", None, "C:maj"), C.Seg(1.0, 1.0, 0, "maj", None, "C:maj"), C.Seg(2.0, 2.0, 7, "maj", None, "G:maj")]
    out = C.snap_to_beats(raw, BEATS, 4.0)
    assert len(out) == 2 and out[0].d == 2.0
    # a boundary with no beat nearby (beats only up to 0.5 s) keeps its time
    out2 = C.snap_to_beats([C.Seg(0, 3.0, 0, "maj", None, "C:maj"), C.Seg(3.0, 2.0, 7, "maj", None, "G:maj")], BEATS[:2], 5.0)
    assert abs(out2[1].t - 3.0) < 1e-9


def test_assign_beat_index():
    segs = [C.Seg(0.0, 1.0, 0, "maj"), C.Seg(1.02, 1.0, 7, "maj"), C.Seg(2.3, 1.0, 5, "maj")]
    C.assign_beat_index(segs, BEATS)
    assert [s.beat_index for s in segs] == [0, 2, None]          # 2.3 s is 0.2 s from a beat (> 35 % of the interval)


def test_template_decode_recovers_a_rendered_progression():
    x, sr, tr = m4.progression([(0, "maj"), (9, "min"), (5, "maj"), (7, "maj")], repeats=3)
    cf = compute_chroma(m4.resample(x, sr, 22050))
    segs = C.template_decode(cf, C.beat_windows(tr["beats"], tr["duration"]))
    assert _acc(tr["chords"], C.to_items(segs), field=("root_pc", "quality")) >= 0.95


def test_verify_scores_right_chords_above_wrong_ones_and_finds_bass():
    x, sr, tr = m4.progression([(0, "maj"), (7, "maj")], repeats=3)
    cf = compute_chroma(m4.resample(x, sr, 22050))
    windows = C.beat_windows(tr["beats"], tr["duration"])
    right = [C.Seg(c["t"], c["d"], c["root_pc"], c["quality"], None, c["label"]) for c in tr["chords"]]
    wrong = [C.Seg(c["t"], c["d"], (c["root_pc"] + 2) % 12, "min", None, "x") for c in tr["chords"]]
    C.verify_segments(right, cf, None, windows)
    C.verify_segments(wrong, cf, None, windows)
    assert np.mean([s.conf for s in right]) > 0.75 and np.mean([s.conf for s in wrong]) < 0.45
    assert [s.bass for s in right[:2]] == [0, 7]


def test_n_segments_over_silence_are_confident_and_bass_null():
    cf = compute_chroma(np.zeros(22050 * 3, np.float32))
    s = [C.Seg(0.0, 3.0, None, "N")]
    C.verify_segments(s, cf, None, None)
    assert s[0].conf > 0.7 and s[0].bass is None


def test_analyse_without_lv_chordia_falls_back_to_templates():
    x, sr, tr = m4.progression([(0, "maj"), (5, "maj"), (7, "maj"), (0, "maj")], repeats=2)
    y = m4.resample(x, sr, 22050)
    res = core.analyse(y, tr["duration"], math.ceil(tr["duration"] * 100), tr["beats"], tr["bars"], None, None, {})
    assert res.chord_source == "template" and "chords:template" in res.fallbacks and "key:no_skey" in res.fallbacks
    assert _acc(tr["chords"], res.chords) >= 0.95
    assert res.key_meta["global"]["key"] == "C major"
    # contract shape: gapless cover, labels consistent with root/quality, conf in 0..1
    items = res.chords
    assert abs(items[0]["t"]) < 1e-9 and abs(items[-1]["t"] + items[-1]["d"] - tr["duration"]) < 1e-4
    for a, b in zip(items, items[1:]):
        assert abs(a["t"] + a["d"] - b["t"]) < 1e-5
    for c in items:
        assert 0.0 <= c["conf"] <= 1.0 and (c["label"] == "N") == (c["root_pc"] is None)


def test_analyse_survives_an_lv_chordia_failure():
    x, sr, tr = m4.progression([(0, "maj"), (7, "maj")], repeats=3)
    y = m4.resample(x, sr, 22050)

    def boom():
        raise RuntimeError("no checkpoint")

    res = core.analyse(y, tr["duration"], math.ceil(tr["duration"] * 100), tr["beats"], tr["bars"], boom, None, {})
    assert res.chord_source == "template" and any("lv-chordia failed" in w for w in res.warnings)


def test_silence_has_no_chords():
    y = np.zeros(22050 * 8, np.float32)
    beats = [{"t": i * 0.5, "beat_index": i, "in_pulse": False} for i in range(16)]
    res = core.analyse(y, 8.0, 800, beats, [], None, None, {})
    assert [c["label"] for c in res.chords] == ["N"] and res.summary["no_chord_share"] == 1.0
