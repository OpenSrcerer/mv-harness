# ruff: noqa: E501
"""R-DSP M2 finding F5 (major, real songs, opt-in -m real): the 2-of-3 downbeat vote counts madmom's downbeats
unshifted although the stage itself detects (and flags) madmom's global one-beat phase error, so where the other
trackers are weak the known-wrong tracker flips the bar phase through a spurious 3-beat bar.

Versatile (130 BPM, 4/4 electronic, no 3/4 anywhere per SPIKE/bench-music): rhythm flags
``downbeat_phase_off:madmom:-1`` (madmom's downbeats sit on fused beat 4 in 24 of 29 bars before 203 s), yet it
inserts a 3-beat bar at 203.1 s (bar 110) and from 204.5 s to the end (about 13 bars) the fused downbeats agree with
madmom (F 1.00) and with allin1 not at all (F 0.00; allin1's own phase is unchanged across the song: its downbeats
fall on fused beat 1 before and on beat 2 after the inserted bar). Internal votes after 204.4 s: allin1 7 x beat 2,
beat_this 6 x beat 1 / 5 x beat 2, madmom 10 x beat 1; with madmom corrected by its own detected shift the vote is
22 : 6 for keeping the phase.

The W0 raw tracker outputs (tests/.cache/real/versatile: beat_this logits, madmom RNN activations) are replayed
instead of running inference (same arrays the trackers produce on the canonical mix), so no heavy slot is needed."""
import json

import numpy as np
import pytest
from tests.synth.m2.testing import REPO, doc, events

from mvh.stages.rhythm.fusion import f_measure

SLUG = "versatile"
CACHE = REPO / "tests" / ".cache" / "real" / SLUG
FX = REPO / "tests" / "contract" / f"real-{SLUG}"


@pytest.fixture(scope="module")
def rhythm_out(tmp_path_factory):
    if not (CACHE / "beat_this" / "logits_beat.npy").is_file() or not (FX / "_intermediate" / "ingest").is_dir():
        pytest.skip("W0 real-song cache / fixture for versatile not present")
    from tests.synth.m2.ctx import run_stage

    import mvh.stages.rhythm.trackers as T

    bl = np.load(CACHE / "beat_this" / "logits_beat.npy").astype(np.float32).reshape(-1)
    dl = np.load(CACHE / "beat_this" / "logits_downbeat.npy").astype(np.float32).reshape(-1)
    act = np.load(CACHE / "madmom_dbn" / "rnn_activations.npy").astype(np.float32)
    mp = pytest.MonkeyPatch()
    mp.setattr(T, "beat_this_logits", lambda mono, sr, ck: (bl, dl))
    mp.setattr(T, "madmom_activations", lambda x: act)
    out = tmp_path_factory.mktemp("versatile") / "rhythm"
    try:
        run_stage("rhythm", FX, out, slug=SLUG, threads=6)
    finally:
        mp.undo()
    return out


@pytest.mark.real
@pytest.mark.timeout(1200)
def test_no_phase_flip_toward_the_flagged_tracker(rhythm_out):
    tempo = doc(rhythm_out, "meta/tempo.json")
    assert "downbeat_phase_off:madmom:-1" in tempo["qa"]["flags"]          # the stage knows madmom is one beat off
    beats = events(rhythm_out, "beats")
    fused = np.array([b["t"] for b in beats if b["beat_in_bar"] == 1 and b["bar"] > 0 and b["in_pulse"]])
    with open(CACHE / "allin1" / "allin1.json", encoding="utf-8") as fh:
        a1 = np.array(json.load(fh)["downbeats"], float)
    late = 204.4
    f_late = f_measure(fused[fused >= late], a1[a1 >= late], 0.07)
    assert f_late >= 0.8, f"fused downbeats after {late} s vs allin1: F={f_late:.2f}; meter changes {tempo['meter']['changes']}"


@pytest.mark.real
@pytest.mark.timeout(1200)
def test_no_spurious_three_beat_bar_in_a_four_four_track(rhythm_out):
    bars = events(rhythm_out, "bars")
    odd = [(b["bar"], b["t"], b["beats_in_bar"]) for b in bars if b["bar"] > 0 and b["in_pulse"] and b["beats_in_bar"] != 4]
    assert odd == [], odd
