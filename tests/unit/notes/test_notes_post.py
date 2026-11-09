"""Pure note post-processing and the MIDI tempo map (no models)."""

from __future__ import annotations

import io

import numpy as np

from mvh.stages.notes import post
from mvh.stages.notes.midi import PPQ, TempoMap, smf_bytes


def test_note_names_c4_is_60():
    assert post.note_name(60) == "C4" and post.note_name(69) == "A4" and post.note_name(33) == "A1"
    assert post.note_name(61) == "C#4"


def test_monophonic_keeps_one_note_at_a_time():
    ns = [(0.0, 1.0, 40, 0.8), (0.5, 1.5, 47, 0.7), (0.51, 0.7, 52, 0.2), (2.0, 2.5, 33, 0.6), (2.005, 2.4, 45, 0.3)]
    m = post.monophonic(ns)
    for a, b in zip(m, m[1:]):
        assert a[1] <= b[0] + 1e-9
    assert [n[2] for n in m] == [40, 47, 33]  # weak inner note dropped; simultaneous onsets: stronger (lower) wins
    assert m[0][1] == 0.5


def test_merge_fragments_and_octave_ghost():
    ons = np.array([1.0, 2.0])
    ns = [(1.0, 1.08, 40, 0.5), (1.08, 1.6, 40, 0.6), (2.0, 2.3, 47, 0.7), (2.3, 2.38, 35, 0.4), (2.38, 2.9, 47, 0.7)]
    m = post.merge_fragments(ns, ons)
    assert (1.0, 1.6, 40) == tuple(m[0][:3])
    assert all(n[2] != 35 for n in m)  # octave-below ghost between two notes removed


def test_mask_by_activity():
    act = np.zeros(500)
    act[100:300] = 1
    ns = [(1.2, 1.8, 40, 0.5), (3.5, 4.0, 41, 0.5)]
    assert post.mask_by_activity(ns, act) == [ns[0]]
    assert post.mask_by_activity(ns, None) == ns


def test_stats_and_velocities():
    items = [{"midi": 33}, {"midi": 45}, {"midi": 40}]
    s = post.stats(items, 10.0)
    assert s["count"] == 3 and s["lowest"] == 33 and s["highest"] == 45 and s["density_per_s"] == 0.3
    assert abs(sum(s["pc_histogram"]) - 1) < 1e-3 and s["pc_histogram"][9] > 0.6
    assert post.stats([], 10.0)["lowest"] is None
    v = post.velocities(np.array([-40.0, -20.0, -10.0]), np.array([0.5, 0.5, 0.5]))
    assert np.all(np.diff(v) > 0) and v.min() >= 0.15 and v.max() <= 1.0


def test_tempo_map_beats_on_quarters_and_seconds_round_trip():
    import mido

    beats = [0.5 + 0.5 * i for i in range(16)] + [8.5 + 0.6 * i for i in range(8)]  # 120 BPM then 100 BPM
    tm = TempoMap.from_grid(beats, [(0.5, 4), (8.5, 3)])
    assert tm.lead_quarters == 1
    tk = tm.ticks(np.array(beats))
    assert np.allclose(tk, (np.arange(len(beats)) + 1) * PPQ)
    assert float(tm.ticks(0.0)) == 0.0
    notes = [{"t": 0.25, "d": 0.5, "midi": 40, "vel": 0.8}, {"t": 9.1, "d": 0.3, "midi": 45, "vel": 0.5},
             {"t": 14.0, "d": 1.0, "midi": 47, "vel": 1.0}]
    data = smf_bytes({"bass": notes, "piano": []}, tm)
    mf = mido.MidiFile(file=io.BytesIO(data))
    assert mf.ticks_per_beat == PPQ and len(mf.tracks) == 3
    t, ons = 0.0, []
    for msg in mf:  # mido converts ticks to seconds through the tempo map
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            ons.append(round(t, 3))
    assert np.allclose(ons, [0.25, 9.1, 14.0], atol=0.002)
    sigs = [m for m in mf.tracks[0] if m.type == "time_signature"]
    assert [s.numerator for s in sigs] == [4, 3]


def test_tempo_map_survives_a_long_beatless_gap():
    """MEGAFAUNA's grid has gaps: a 30 s hole must not produce an out-of-range MIDI tempo."""
    import mido

    beats = [0.5 * i for i in range(1, 20)] + [40.0 + 0.5 * i for i in range(10)]
    tm = TempoMap.from_grid(beats)
    assert all(1 <= us <= 16777215 for _tk, us in tm.tempo_events())
    notes = [{"t": 20.0, "d": 1.0, "midi": 40, "vel": 0.5}, {"t": 41.0, "d": 0.5, "midi": 41, "vel": 0.5}]
    data = smf_bytes({"bass": notes}, tm)
    t, ons = 0.0, []
    for msg in mido.MidiFile(file=io.BytesIO(data)):
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            ons.append(t)
    assert np.allclose(ons, [20.0, 41.0], atol=0.003)
