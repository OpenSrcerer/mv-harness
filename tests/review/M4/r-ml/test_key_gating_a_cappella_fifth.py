"""R-ML M4 round 5 (R5-M2): R4-M1 is only partly fixed. The carve-out needs S-KEY's top key to be EXACTLY the winner, so
when S-KEY lands on the fifth neighbour (its most common error) a tonal a-cappella line is again labelled
key:no_tonal_evidence.

Signal: the synthetic song's lead-vocal stem (A minor, synthetic, no real lyrics) transposed up 3 semitones by
resampling (C minor). Probe out/_wip/r-ml-m4-r5/probe6.log, case vocals_shift3 (real S-KEY, real lv-chordia):
no-chord share 1.0; KS, Temperley and Albrecht all C minor (top correlations 0.77 / 0.71 / 0.90, the same peaky chroma
as the untransposed stem); S-KEY votes G minor (the fifth neighbour, p_max 0.337). Result: C minor at 0.30 with
key:no_tonal_evidence + key:low_confidence. The other five transpositions (-5, -3, -2, +2, +5) keep their key at
0.66-0.97 with key:chroma_only. The "no tonal evidence" label is false: three profiles agree on a peaked chroma and
S-KEY votes for a closely related key. A lower confidence would be fair; the label is not.

Fast test: stub S-KEY on G minor at p 0.3 in every window (the real 0.337 is a mean over windows of differing answers;
a constant 0.3 reproduces the real output and flags exactly) and lv-chordia's real output (one N segment).
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


def _vocals_up3() -> np.ndarray:
    from scipy.signal import resample_poly

    from mvh.io.audio import decode

    if not STEM.is_file():
        pytest.skip(f"missing {STEM}")
    y = np.asarray(decode(STEM, sr=SR22, mono=True).samples, np.float32).reshape(-1)
    return resample_poly(y, 1000, int(round(1000 * 2 ** (3 / 12)))).astype(np.float32)


class _SKeyAt:
    def __init__(self, key: str = "G minor", p: float = 0.3):
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


def _assert_tonal_label_kept(res):
    g, flags = res.key_meta["global"], res.key_meta["flags"]
    assert res.summary["no_chord_share"] >= 0.9
    assert g["key"] == "C minor", g
    assert "key:no_tonal_evidence" not in flags, (g, flags,
                                                  {k: v.get("top", [None])[0] for k, v in res.key_meta["methods"].items()})


def test_a_cappella_with_skey_on_the_fifth_is_not_atonal_stub_skey():
    y = _vocals_up3()
    dur = len(y) / SR22

    def lv():
        return [{"start_time": 0.0, "end_time": dur, "chord": "N"}]

    _assert_tonal_label_kept(_analyse(y, _SKeyAt(), lv))


@pytest.mark.real
def test_a_cappella_with_skey_on_the_fifth_is_not_atonal_real_models(skey, tmp_path):
    from scipy.io import wavfile

    from mvh.stages.harmony import chords as C
    from mvh.testing import heavy

    y = _vocals_up3()
    wav = tmp_path / "vocals_up3_22k.wav"
    wavfile.write(str(wav), SR22, y.astype(np.float32))

    def lv():
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            return C.run_lv_chordia(wav, "submission")
        finally:
            os.chdir(cwd)

    with heavy("r-ml-m4-r5-test", threads=3):
        res = _analyse(y, skey, lv)
    _assert_tonal_label_kept(res)
