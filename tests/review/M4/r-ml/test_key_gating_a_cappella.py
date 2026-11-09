"""R-ML M4 round 4: the R3-M1 fix (lv-chordia no-chord share >= 0.9 caps the key at 0.3 + key:no_tonal_evidence) also
fires on an a-cappella line, which is tonal: lv-chordia says N because there are no CHORDS, not because there is no KEY.

Signal: the synthetic song's lead-vocal stem (tests/contract/synth/stems/lead_vocals.flac, the A minor song of _truth;
synthetic, no real lyrics). Probe out/_wip/r-ml-m4-r4/probe.log, case synth_stem_vocals (real S-KEY, real lv-chordia):
no-chord share 1.0; S-KEY top A minor, recovered p_max 0.566 (voted); KS, Temperley and Albrecht all A minor. Round 3
(before the fix) gave A minor at 0.913 with no flags; now A minor at 0.30 flagged key:no_tonal_evidence +
key:low_confidence. The flag is false and a director agent is told to ignore a correct key on solo voice / a-cappella
intros / choral pieces. Band-limited noise (test_key_gating_band_noise.py) must stay gated, so the fix needs a
tonality measure that separates the two (e.g. chroma peakiness / harmonic-to-noise of the HPSS harmonic part, or
S-KEY plus a profile majority on a peaky chroma), not lv-chordia's chord/no-chord decision alone.

The fast test uses a stub S-KEY at the probability the real model gives (0.566 on A minor) and lv-chordia's real output
on this stem (one N segment); the real test runs the real S-KEY and lv-chordia.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pytest
from m4rml_signals import SR22, beat_grid

REPO = Path(__file__).resolve().parents[4]
STEM = REPO / "tests/contract/synth/stems/lead_vocals.flac"


def _vocals() -> np.ndarray:
    from mvh.io.audio import decode

    if not STEM.is_file():
        pytest.skip(f"missing {STEM}")
    y = np.asarray(decode(STEM, sr=SR22, mono=True).samples, np.float32).reshape(-1)
    return y


class _SKeyAt:
    """Stands in for keys.SKey: the recovered probability the real model gives on this stem (0.566 on A minor)."""

    def __init__(self, key: str = "A minor", p: float = 0.566):
        from mvh.stages.harmony import theory as T

        self.keymap = [T.key_name(pc, mode) for mode in ("major", "minor") for pc in range(12)]
        self.key, self.p = key, p

    def log_scores(self, y22):
        from mvh.stages.harmony import keys as K

        p = np.full(24, (1.0 - self.p) / 23)
        p[self.keymap.index(self.key)] = self.p
        return K.skey_log(p, self.keymap), p


def _analyse(y, skey, lv):
    from mvh.stages.harmony import core

    dur = len(y) / SR22
    beats, bars = beat_grid(dur)
    return core.analyse(y, dur, math.ceil(dur * 100), beats, bars, lv, skey, {})


def _assert_tonal_key_kept(res):
    g, flags = res.key_meta["global"], res.key_meta["flags"]
    assert res.summary["no_chord_share"] >= 0.9          # precondition: the chord model hears no chords
    assert g["key"] == "A minor", g
    assert "key:no_tonal_evidence" not in flags and g["conf"] >= 0.5, (g, flags, res.key_meta["agreement"],
                                                                      {k: v.get("top", [None])[0] for k, v in res.key_meta["methods"].items()})


def test_a_cappella_line_keeps_its_key_stub_models():
    y = _vocals()
    dur = len(y) / SR22

    def lv():                       # lv-chordia's real output on this stem (probe: no-chord share 1.0)
        return [{"start_time": 0.0, "end_time": dur, "chord": "N"}]

    _assert_tonal_key_kept(_analyse(y, _SKeyAt(), lv))


@pytest.mark.real
def test_a_cappella_line_keeps_its_key_real_models(skey, tmp_path):
    from scipy.io import wavfile

    from mvh.stages.harmony import chords as C
    from mvh.testing import heavy

    y = _vocals()
    wav = tmp_path / "vocals22k.wav"
    wavfile.write(str(wav), SR22, y.astype(np.float32))

    def lv():
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return C.run_lv_chordia(wav, "submission")
        finally:
            os.chdir(cwd)

    with heavy("r-ml-m4-r4-test", threads=3):
        res = _analyse(y, skey, lv)
    _assert_tonal_key_kept(res)
