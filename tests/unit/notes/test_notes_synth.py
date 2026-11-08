# ruff: noqa: E501  (long numeric tables / docstrings)
"""notes against synthetic ground truth (PLAN §7: monophonic bass note F1 >= 0.8)."""

from __future__ import annotations

import io

import numpy as np
import pytest
from tests.synth.m3b.scoring import as_dicts, events, jload, note_f1

pytestmark = [pytest.mark.slow, pytest.mark.timeout(5400)]  # includes waiting for a machine-wide heavy slot
BASS_F1 = 0.8


def _bp():
    from mvh.runner.models import handle
    from mvh.stages.notes.bp import BasicPitch

    return BasicPitch(next(iter(handle("basic_pitch_nmp_onnx").files.values())), threads=3)


def _pipeline(bp, y, src):
    from mvh.stages.notes import post
    from mvh.stages.notes.bp import PRESETS

    pr = PRESETS[src]
    ns = bp.notes(y, pr)
    ons = post.audio_onsets(y, 22050, 600.0 if src == "bass" else None)
    ns = post.snap_onsets(ns, ons)
    if pr.mono:
        ns = post.monophonic(ns)
    ns = post.merge_fragments(ns, ons)
    if pr.mono:
        ns = post.monophonic(ns)
    return ns


def test_bass_line_primitive_f1():
    import soxr
    from tests.synth import primitives as P

    from mvh.testing import heavy

    x, sr, tr = P.midi_render(P.BASS_LINE, program="bass")
    y = soxr.resample(x, sr, 22050).astype(np.float32)
    with heavy("builder-m3b:pytest", threads=3):
        ns = _pipeline(_bp(), y, "bass")
    p, r, f = note_f1(as_dicts(ns), tr["notes"])
    assert f >= BASS_F1, (p, r, f)
    for a, b in zip(ns, ns[1:]):
        assert a[1] <= b[0] + 1e-6  # monophonic


def test_notes_stage_on_synth(synth_out, truth):
    res = jload(synth_out / "_done.json")["notes"]
    p, r, f = note_f1(events(synth_out, "notes.bass"), truth["notes"]["bass"])
    assert f >= BASS_F1, (p, r, f)
    p, r, f = note_f1(events(synth_out, "notes.piano"), truth["notes"]["piano"])
    assert f >= 0.8, (p, r, f)
    assert events(synth_out, "notes.guitar") == []          # guitar stem is digital silence
    other = events(synth_out, "notes.other")
    in_key = sum(it["midi"] % 12 in {0, 2, 4, 5, 7, 9, 11} for it in other)
    assert other and in_key >= 0.9 * len(other)              # the pad plays diatonic A minor / C major chords
    # synthetic piano is not recognised as a piano by CED: transcribed by basic-pitch, never the CRNN on a doubtful stem
    assert "piano:basic_pitch" in res["fallbacks"]
    for src in ("bass", "piano", "other"):
        for it in events(synth_out, f"notes.{src}"):
            assert 0 <= it["vel"] <= 1 and 0 <= it["conf"] <= 1 and it["d"] > 0
    meta = jload(synth_out / "notes/notes.json")
    assert set(meta["sources"]) == {"bass", "piano", "guitar", "other"}
    assert meta["sources"]["guitar"]["midi"] is None and meta["sources"]["bass"]["midi"] == "notes/bass.mid"
    assert 26 <= meta["sources"]["bass"]["lowest"] and meta["sources"]["bass"]["highest"] <= 50


def test_notes_mid_tempo_map_matches_the_beat_grid(synth_out, truth):
    import mido

    data = (synth_out / "notes/notes.mid").read_bytes()
    mf = mido.MidiFile(file=io.BytesIO(data))
    names = [t.name for t in mf.tracks]
    assert names == ["tempo map", "bass", "piano", "guitar", "other"]
    tempos = {m.tempo for m in mf.tracks[0] if m.type == "set_tempo"}
    assert 500000 in tempos  # 120 BPM synthetic song
    sigs = [m.numerator for m in mf.tracks[0] if m.type == "time_signature"]
    assert 3 in sigs and 4 in sigs  # bar 16 is in 3/4
    # first bass note onset in seconds survives the tick mapping
    t, first = 0.0, None
    for msg in mf:
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0 and msg.channel == 0:
            first = t
            break
    assert abs(first - events(synth_out, "notes.bass")[0]["t"]) < 0.003


def test_piano_gate_skips_silent_stem():
    """A silent / barely active piano stem never reaches the CRNN (W0: 378 invented notes on MEGAFAUNA)."""
    from mvh.stages.notes import _piano_gate

    ok, why = _piano_gate(None, {"piano_min_active_s": 1.0}, 0.05, None, 44100, 44100)
    assert not ok and "0.050" in why
