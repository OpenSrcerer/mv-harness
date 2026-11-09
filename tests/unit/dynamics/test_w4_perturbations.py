"""W4A-STABLE (M1 dynamics): the contract synth re-analysed at 48 kHz and 12 dB quieter keeps its loud / quiet parts.

The root cause was a hard 2-bar minimum: parts are downbeat-snapped, so the synthetic decay tail (52.5-56.5 s) is exactly
2 bars long and survived at 48 kHz (median bar 2.0000 s) but was merged at 44.1 kHz (2.0005 s); the same 1 ms decided
whether the 9.0 s verse entry (4.0 s after the 5.0 s impact) was a part boundary. Synthetic audio only (the contract
fixture's mix); spectral + loudness + dynamics, about 30 s. The arrangement boundaries (impact, stop / silence, drop,
drop half, decay tail) must agree; the intro -> verse step at 9.0 s is a weak novelty peak near the threshold and may
come and go (its part has the same level either way)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from tests.synth.m1.harness import run_m1
from tests.synth.m1.markers import REPO

SYNTH = REPO / "tests" / "contract" / "synth"


@pytest.fixture(scope="module")
def synth_mix():
    from mvh.io import audio as aio

    d = aio.decode(SYNTH / "audio" / "mix.flac")
    with open(SYNTH / "events" / "bars.json", encoding="utf-8") as fh:
        bars = json.load(fh)["items"]
    return np.asarray(d.samples, np.float32), int(d.sr), bars


def _parts(x, sr, bars, out):
    r = run_m1(x, sr, out, bars=bars)
    return [(round(p["t"], 2), p["level"]) for p in r["ctx"]["dynamics"].written_events("dynamics")["items"]]


@pytest.fixture(scope="module")
def base(synth_mix, tmp_path_factory):
    x, sr, bars = synth_mix
    return _parts(x, sr, bars, tmp_path_factory.mktemp("base"))


def test_the_decay_tail_is_its_own_part(base):
    starts = [t for t, _ in base]
    assert any(abs(t - 52.5) <= 0.05 for t in starts), base


ARRANGEMENT = (5.0, 32.5, 34.5, 42.5, 52.5)


def _same(base, got):
    a, b = [t for t, _ in base if t != 9.0], [t for t, _ in got if t != 9.0]
    for t in ARRANGEMENT:
        assert any(abs(t - s) <= 0.05 for s in b), (t, base, got)
    assert len(a) == len(b) and all(abs(p - q) <= 0.05 for p, q in zip(a, b)), (base, got)


def test_resampling_to_48k_keeps_the_part_boundaries(synth_mix, base, tmp_path):
    import soxr

    x, sr, bars = synth_mix
    y = np.stack([soxr.resample(c, sr, 48000) for c in x]).astype(np.float32)
    _same(base, _parts(y, 48000, bars, tmp_path))


def test_a_12db_quieter_master_keeps_the_part_boundaries(synth_mix, base, tmp_path):
    x, sr, bars = synth_mix
    _same(base, _parts(x * np.float32(10 ** (-12 / 20)), sr, bars, tmp_path))


def test_w4v_silence_threshold_moves_with_the_master_level():
    """W4V-GAIN-REAL: the silence threshold is relative only (the absolute -45 LUFS cap bound on loud masters only, so a
    -12 dB copy of MEGAFAUNA got a 2.95 s silence instead of 1.28 s)."""
    from mvh.stages.dynamics import STAGE
    from mvh.stages.dynamics.detect import silence_threshold

    rel = float(STAGE.params["silence_rel_lu"])
    assert STAGE.params["silence_cap_lufs"] is None
    for integ in (-6.0, -10.8, -20.4):
        assert abs(silence_threshold(integ, rel, None) - silence_threshold(integ - 12.0, rel, None) - 12.0) < 1e-9
    assert silence_threshold(-90.0, rel, None) > -70.0  # digital silence stays silent
