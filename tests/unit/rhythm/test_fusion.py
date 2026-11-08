# ruff: noqa: E501
"""Rhythm fusion core on synthetic activations (no models, fast)."""
import numpy as np
import pytest

from mvh.stages.rhythm import fusion as fu


def _act(beats, n, width=2.0):
    t = np.arange(n) / fu.FPS
    a = np.zeros(n)
    for b in beats:
        a = np.maximum(a, np.exp(-0.5 * ((t - b) * fu.FPS / width) ** 2))
    return 0.05 + 0.9 * a


def test_f_measure_basics():
    ref = np.arange(0.5, 10, 0.5)
    assert fu.f_measure(ref, ref) == 1.0
    assert fu.f_measure(ref + 0.06, ref, 0.07) == 1.0
    assert fu.f_measure(ref + 0.08, ref, 0.07) == 0.0
    p_, r_ = 1.0, 10 / 19
    assert abs(fu.f_measure(ref[::2], ref) - 2 * p_ * r_ / (p_ + r_)) < 1e-9


def test_track_beats_on_activation_120bpm():
    truth = np.arange(0.5, 30, 0.5)
    act = _act(truth, 3100)
    frames = fu.track_beats(act, 100, 144)
    est = frames / fu.FPS
    est = est[(est > 0.4) & (est < 29.6)]          # the HMM also walks through the empty edges (no-pulse later)
    assert fu.f_measure(est, truth, 0.07) >= 0.98
    assert np.max(np.abs(est - truth[np.argmin(np.abs(truth[None, :] - est[:, None]), axis=1)])) < 0.006


def test_track_beats_picks_the_strong_phase_at_half_tempo():
    # activation peaks at 240 BPM, alternating strong / weak: tracking at 120 BPM must take the strong ones
    t8 = np.arange(0.5, 20, 0.25)
    n = 2100
    tt = np.arange(n) / fu.FPS
    act = np.full(n, 0.05)
    for k, b in enumerate(t8):
        h = 0.9 if k % 2 == 0 else 0.35
        act = np.maximum(act, 0.05 + h * np.exp(-0.5 * ((tt - b) * fu.FPS / 2.0) ** 2))
    est = fu.track_beats(act, 100, 144) / fu.FPS
    est = est[(est > 0.4) & (est < 19.8)]
    assert fu.f_measure(est, t8[::2], 0.07) >= 0.98


def test_tempo_arbitration_prefers_consensus_and_records_alternatives():
    n = 6000
    truth = np.arange(0.5, 59, 0.5)
    drum = np.zeros(n)
    for k, b in enumerate(truth):
        drum[int(round(b * 100))] = 1.0                       # kick/snare on every beat
        drum[int(round((b + 0.25) * 100))] = 0.2              # light 8ths
    arb = fu.arbitrate_tempo({"beat_this": 240.0, "madmom": 120.0, "allin1": 120.4, "librosa": 119.8},
                             [(120.0, 1.0), (60.0, 0.7), (240.0, 0.6)], drum)
    assert abs(arb.bpm - 120.0) < 1.0
    rel = {c["relation"] for c in arb.candidates}
    assert "x0.5" in rel                       # 240 is outside the 50-230 BPM candidate range
    assert arb.candidates[0]["relation"] == "x1"


def test_tempo_arbitration_override_forces_level():
    drum = np.zeros(3000)
    arb = fu.arbitrate_tempo({"beat_this": 120.0}, [], drum, forced=60.0)
    assert arb.bpm == 60.0 and not arb.ambiguous


def test_metrical_evidence_separates_octaves():
    n = 6000
    drum = np.zeros(n)
    for b in np.arange(0.5, 59, 0.5):
        drum[int(round(b * 100))] = 1.0
    ok = fu.metrical_evidence(drum, 120.0)
    slow = fu.metrical_evidence(drum, 60.0)
    fast = fu.metrical_evidence(drum, 240.0)
    assert ok["score"] > slow["score"] and ok["score"] > fast["score"]
    assert slow["contrast"] < 0.2 and fast["coverage"] < 0.7


def test_decode_meter_pickup_and_three_four_bar():
    # 1 pickup beat, 4 bars of 4/4, one 3/4 bar, 2 bars of 4/4
    pos_truth = [4] + [1, 2, 3, 4] * 4 + [1, 2, 3] + [1, 2, 3, 4] * 2
    score = np.array([2.6 if p == 1 else 0.3 for p in pos_truth])
    mp = fu.decode_meter(score)
    assert list(mp.position) == pos_truth
    assert list(mp.meter[17:20]) == [3, 3, 3]
    assert not mp.irregular.any()


def test_decode_meter_follows_majority_vote_phase():
    # two voters say phase 0, one says phase +1: the 2-of-3 vote wins
    n = 64
    votes = np.zeros(n)
    votes[0::4] += 2.0
    votes[1::4] += 1.0
    mp = fu.decode_meter(votes)
    assert all(mp.position[i] == 1 for i in range(0, n, 4))


def test_estimate_lag_recovers_tracker_latency():
    times = np.arange(0.5, 40, 0.5)
    tr = fu.Transients(times.copy(), np.full(len(times), 30.0))
    lag, nm, thr = fu.estimate_lag(times + 0.02, tr)
    assert lag == pytest.approx(-0.02, abs=1e-6) and nm >= 20 and thr == 15.0


def test_transients_find_click_onsets():
    from tests.synth.primitives import click_track

    x, sr, tr = click_track(120.0, 8.0)
    t = fu.transients(x, sr)
    onsets = np.array([b["t"] for b in tr["beats"]])
    err = [np.min(np.abs(t.times - o)) for o in onsets]
    assert max(err) < 0.003


def test_regularize_grid_virtual_gap_and_tail():
    beats = np.r_[np.arange(1.0, 10.0, 0.5), np.arange(12.0, 20.0, 0.5)]
    flags = np.ones(len(beats), bool)
    b, ip = fu.regularize_grid(beats, flags, 22.0)
    gap = b[(b > 9.6) & (b < 11.9)]
    assert np.allclose(np.diff(gap), 0.5, atol=1e-6) and not ip[(b > 9.6) & (b < 11.9)].any()
    assert b[-1] < 22.0 and b[-1] > 21.0 and not ip[-1]
    assert b[0] == 1.0


def test_pulse_flags_silence():
    beats = np.arange(0.5, 20, 0.5)
    act = _act(beats, 2000)
    level = np.full(2000, -20.0)
    level[1000:1200] = -120.0          # 10..12 s digital silence
    fl, _ = fu.pulse_flags(beats, act, level)
    assert not fl[(beats >= 10.0) & (beats < 11.9)].any()
    assert fl[(beats < 9.5) | (beats > 12.5)].all()


def test_feel_labels_half_time_section():
    beats = np.arange(0.5, 60, 0.5)
    trk = {"a": np.r_[np.arange(0.5, 30, 1.0), np.arange(30.0, 60, 0.5)],
           "b": np.r_[np.arange(0.5, 30, 1.0), np.arange(30.0, 60, 0.5)]}
    lab = fu.feel_labels(beats, trk)
    assert (lab[beats < 25] == "half_time").mean() > 0.9
    assert (lab[beats > 35] == "normal").all()
    segs = fu.tempo_segments(beats, np.ones(len(beats), bool), lab, 60.0)
    assert [s["feel"] for s in segs] == ["half_time", "normal"]
    assert segs[0]["t"] == 0.0 and abs(segs[-1]["t"] + segs[-1]["d"] - 60.0) < 1e-6
