"""instruments on the synthetic song (real CED/CLAP inference, one shared run) and the CED recipe."""

from __future__ import annotations

import numpy as np
import pytest
from tests.synth.m3b.fxctx import read_curve
from tests.synth.m3b.scoring import events, jload

pytestmark = [pytest.mark.slow, pytest.mark.timeout(5400)]  # includes waiting for a machine-wide heavy slot


def _overlap(segs, a, b):
    return sum(max(0.0, min(s["t"] + s["d"], b) - max(s["t"], a)) for s in segs)


def test_ced_output_is_already_a_probability():
    """docs/SPIKE.md: never apply a sigmoid. Silence must read ~0 (a sigmoid over logits would give >= 0.5)."""
    from mvh.runner.models import handle
    from mvh.stages.instruments.ced import CedTagger
    from mvh.testing import heavy

    t = CedTagger(dict(handle("ced_base_onnx").files), threads=3)
    tone = 0.3 * np.sin(2 * np.pi * 440 * np.arange(4 * 16000) / 16000)
    y = np.concatenate([np.full(4 * 16000, 1e-3), tone]).astype(np.float32)  # quiet noise floor, then a tone
    with heavy("builder-m3b:pytest", threads=3):
        p = t.frames(y, 8)
    assert p.shape == (8, 527)
    assert 0.0 <= p.min() and p.max() <= 1.0
    assert float(np.median(p)) < 0.05
    sil = t.frames(np.zeros(16000 * 3, np.float32), 3)
    assert sil.max() == 0.0  # silent windows are skipped (probability 0)


def test_instruments_on_synth(synth_out, truth):
    ins = events(synth_out, "instruments")
    by = {}
    for it in ins:
        by.setdefault(it["instrument"], []).append(it)
        assert 0 <= it["conf"] <= 1 and it["d"] > 0 and it["evidence"] in ("stem", "tagger", "both")
    # drums and bass play almost the whole song (truth: drums 0.5-54.5, bass from 5.0); voice in 9-42 s
    assert _overlap(by["drums"], 1.0, 32.5) > 0.9 * 31.5
    assert _overlap(by["bass"], 5.0, 32.5) > 0.85 * 27.5
    assert _overlap(by["voice"], 9.0, 41.5) > 0.8 * 32.5
    assert _overlap(by.get("voice", []), 0.0, 8.5) < 1.5          # nothing sung before 9 s
    assert _overlap(by.get("voice", []), 43.0, 56.5) < 1.5        # instrumental after the duet
    assert "guitar" not in by                                    # the guitar stem is digital silence
    meta = jload(synth_out / "meta/instruments.json")
    assert {r["instrument"] for r in meta["summary"]} >= {"drums", "bass", "voice"}
    assert meta["vocal_style"]["dominant"] in ("singing", "speech")
    assert meta["vocal_style"]["shares"]["rap"] < 0.1           # no rap in a sung duet
    assert abs(sum(meta["vocal_style"]["shares"].values()) - 1.0) < 1e-3


def test_curves_on_the_1hz_grid(synth_out, truth):
    n = -(-truth["n_samples"] // truth["sr"])
    for cid in ("inst.voice", "inst.drums", "inst.synth_pad", "vstyle.singing", "vstyle.speech", "vstyle.rap"):
        v = read_curve(synth_out, "instruments_1hz", cid)
        assert v.size == n and np.isfinite(v).all() and v.min() >= 0 and v.max() <= 1
    # vstyle.* never exceeds the voice probability
    voice = read_curve(synth_out, "instruments_1hz", "inst.voice")
    tot = sum(read_curve(synth_out, "instruments_1hz", f"vstyle.{s}") for s in ("singing", "speech", "rap"))
    assert np.all(tot <= voice + 1e-4)
    vs = events(synth_out, "vocal_style")
    assert vs and all(it["style"] in ("singing", "speech", "rap") for it in vs)
