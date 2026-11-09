"""vocals against synthetic ground truth: vibrato 'sung' sines (range +-1 semitone, PLAN §7) and the synthetic song."""

from __future__ import annotations

import numpy as np
import pytest
from tests.synth.m3b.fxctx import read_curve
from tests.synth.m3b.scoring import events, jload, note_f1

pytestmark = [pytest.mark.slow, pytest.mark.timeout(5400)]  # includes waiting for a machine-wide heavy slot
RANGE_TOL = 1.0  # semitones (PLAN §7)


def test_sung_sine_range_within_one_semitone():
    """RMVPE + SwiftF0 arbitration and the range statistics on harmonic vibrato tones (truth exact)."""
    import soxr
    from rmvpe_onnx import RMVPE
    from swift_f0 import SwiftF0
    from tests.synth import primitives as Prim

    from mvh.runner.models import handle
    from mvh.stages.vocals import pitch as P
    from mvh.testing import heavy

    notes = [(0.5 + 0.6 * i, 0.5, m) for i, m in enumerate([50, 53, 55, 57, 60, 62, 64, 62, 60, 57, 55, 53, 67, 50])]
    x, sr, tr = Prim.sung_sine(notes, vib_cents=40.0)
    y = soxr.resample(x, sr, 16000).astype(np.float32)
    n = -(-x.size * 100 // sr)
    with heavy("builder-m3b:pytest", threads=3):
        t, f, c, _ = RMVPE(model_path=str(next(iter(handle("rmvpe_onnx").files.values()))), device="cpu").predict(y, 16000)
        r = SwiftF0(threads=3).detect(y, 16000, fmin=46.875, fmax=2093.75)
    rm = P.to_grid(np.asarray(t), P.hz_to_midi(np.asarray(f)), n)
    rc = P.to_grid(np.asarray(t), np.asarray(c), n, fill=0.0)
    sw = P.to_grid(np.asarray(r.timestamps) + 0.008, P.hz_to_midi(np.where(r.pitch_hz > 0, r.pitch_hz, np.nan)), n)
    sc = P.to_grid(np.asarray(r.timestamps) + 0.008, np.asarray(r.confidence), n, fill=0.0)
    a = P.arbitrate(rm, rc, sw, sc)
    midi = P.drop_short(P.fix_octave_islands(a.midi), 5)
    truth = np.array([np.nan if v is None else v for v in tr["midi_100hz"]], float)[:n]
    both = np.isfinite(truth) & np.isfinite(midi)
    assert both.sum() / np.isfinite(truth).sum() > 0.9               # voicing recall
    assert np.mean(np.abs(midi[both] - truth[both]) < 0.5) > 0.95     # raw pitch accuracy (50 cents)
    assert np.isfinite(midi).sum() <= np.isfinite(truth).sum() * 1.08  # few false voiced frames
    q = np.nanpercentile(midi, [2, 98])
    tq = np.nanpercentile(truth, [2, 98])
    assert np.all(np.abs(q - tq) <= RANGE_TOL), (q, tq)
    ns = P.segment_notes(midi)
    lo, hi = P.sustained_extremes(ns, P.midi_to_hz(midi))
    assert abs(lo["midi"] - 50) <= RANGE_TOL and abs(hi["midi"] - 67) <= RANGE_TOL
    p, r_, f1 = note_f1([{"t": x["t"], "d": x["d"], "midi": x["midi"]} for x in ns], tr["notes"])
    assert f1 >= 0.9, (p, r_, f1)


def test_vocals_stage_on_synth(synth_out, truth):
    vr = jload(synth_out / "meta/vocal_range.json")
    t = truth["vocal_range"]
    assert vr["present"] is True and vr["voiced_s"] >= 8
    assert abs(vr["p2"] - t["p2"]) <= RANGE_TOL and abs(vr["p98"] - t["p98"]) <= RANGE_TOL
    assert abs(vr["lowest"]["midi"] - t["lowest"]["midi"]) <= RANGE_TOL
    assert abs(vr["highest"]["midi"] - t["highest"]["midi"]) <= RANGE_TOL
    assert vr["lowest"]["name"] == "G3" and vr["highest"]["name"] == "A4"
    assert vr["p2"] <= vr["p10"] <= vr["median_midi"] <= vr["p90"] <= vr["p98"]
    assert vr["register"] in ("bass", "baritone", "tenor", "alto", "mezzo", "soprano") and 0 < vr["conf"] <= 0.9


def test_vocal_curves_follow_the_contract(synth_out, truth):
    from mvh.contract import curvefile

    n = -(-truth["n_samples"] * 100 // truth["sr"])
    midi = read_curve(synth_out, "vocal", "vocal.midi")
    f0 = read_curve(synth_out, "vocal", "vocal.f0_hz")
    voiced = read_curve(synth_out, "vocal", "vocal.voiced")
    p01 = read_curve(synth_out, "vocal", "vocal.pitch01")
    conf = read_curve(synth_out, "vocal", "vocal.conf")
    assert midi.size == n == f0.size == voiced.size == p01.size == conf.size
    assert np.array_equal(voiced == 1, np.isfinite(midi)) and np.array_equal(np.isfinite(f0), np.isfinite(midi))
    assert np.isfinite(p01).all() and p01.min() >= 0 and p01.max() <= 1 and np.isfinite(conf).all()
    gap_edge = ~np.isfinite(midi)[1:] | ~np.isfinite(midi)[:-1]
    assert np.max(np.abs(np.diff(p01))[gap_edge]) <= 0.5 + 1e-6  # eased through gaps: no jumps
    from pathlib import Path

    fx = Path(__file__).resolve().parents[2] / "contract" / "synth"
    ix = curvefile.read_index(fx)
    tm, _ = curvefile.read_channel(fx, ix, "vocal.midi")
    tv, ev = np.isfinite(tm), np.isfinite(midi)
    both = tv & ev
    assert both.sum() / tv.sum() >= 0.85 and both.sum() / ev.sum() >= 0.85      # voicing recall / precision
    assert np.mean(np.abs(tm[both] - midi[both]) < 0.5) >= 0.95                # raw pitch accuracy
    assert np.isfinite(midi[: int(8.5 * 100)]).sum() == 0                       # no voice before the first line


def test_vocal_notes_phrases_and_midi(synth_out, truth):
    import io

    import mido

    vn = events(synth_out, "notes.vocals")
    p, r, f = note_f1(vn, truth["notes"]["vocals"], tol=0.1)
    assert f >= 0.75, (p, r, f)
    ph = events(synth_out, "vocal_phrases")
    assert 4 <= len(ph) <= 16 and [x["id"] for x in ph] == [f"VP{i + 1:03d}" for i in range(len(ph))]
    for x in ph:
        assert x["min_midi"] <= x["median_midi"] <= x["max_midi"] + 0.5 and x["d"] > 0
    mf = mido.MidiFile(file=io.BytesIO((synth_out / "notes/vocals.mid").read_bytes()))
    assert [t.name for t in mf.tracks] == ["tempo map", "vocals"]
    assert sum(1 for m in mf.tracks[1] if m.type == "note_on" and m.velocity > 0) == len(vn)
