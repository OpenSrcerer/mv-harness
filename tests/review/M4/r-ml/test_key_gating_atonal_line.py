"""R-ML M4 round 5 (R5-M1): the R4-M1 carve-out (``tonal_without_chords`` in keys.global_confidence) lets a hallucinated
key through on a line with NO key.

Signal: a monophonic line of uniformly random pitch classes (seed 28, 120 notes of 0.5 s, additive tones; no structure,
no tonic: a 12-tone / free-improv line). Probe out/_wip/r-ml-m4-r5/probe6.log, case atonal_s28_60s (real S-KEY and real
lv-chordia): lv-chordia no-chord share 1.0; S-KEY top C minor at recovered p_max 0.238 (just above the 0.2 voting floor,
vote weight 0.25); KS C minor, Temperley Eb major (relative), Albrecht C minor, mean top correlation 0.73 >= TONAL_PEAK.
Result: "C minor" conf 0.666 with flags [key:chroma_only, key:relative_ambiguity] and no key:low_confidence. Before the
R4-M1 fix the same input was capped at 0.3 with key:no_tonal_evidence.

Root cause: TONAL_PEAK is a Pearson correlation, which z-scores the chroma and so ignores how flat it is. The long-term
chroma of this line is nearly flat (normalised entropy 0.984, peak/mean 1.48) whereas the tonal a-cappella stems are
0.90 / 2.6-2.8 (out/_wip/r-ml-m4-r5/sum_entropy.py); a chance ripple on a flat distribution still correlates at 0.7 with
some profile. Of 17 random lines that pass the profile screen, this is the one where S-KEY's barely-voting guess also
agrees (out/_wip/r-ml-m4-r5/atonal_seeds.py: about a third of random lines pass the profile part on their own).

The fast test uses a stub S-KEY at the probability the real model gives (C minor, 0.238) and lv-chordia's real output (one
N segment); the real test runs both real models.
"""
from __future__ import annotations

import math
import os

import numpy as np
import pytest
from m4rml_signals import SR22, _note, beat_grid


def _atonal_line(seed: int = 28, seconds: int = 60, step: float = 0.5) -> np.ndarray:
    rr = np.random.default_rng(seed)
    y = np.concatenate([_note(57 + int(rr.integers(0, 12)), step, SR22, 0.3) for _ in range(int(seconds / step))])
    return (y / np.abs(y).max() * 0.5).astype(np.float32)


class _SKeyAt:
    """Stands in for keys.SKey at the recovered probability the real model gives on this line (C minor, 0.238)."""

    def __init__(self, key: str = "C minor", p: float = 0.238):
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


def _assert_no_confident_key(res):
    g, flags = res.key_meta["global"], res.key_meta["flags"]
    assert res.summary["no_chord_share"] >= 0.9          # precondition: the chord model hears no chords
    assert g["conf"] < 0.5 or "key:low_confidence" in flags, (
        "a random 12-tone line got a confident key", g, flags,
        {k: v.get("top", [None])[0] for k, v in res.key_meta["methods"].items()})


def test_random_pitch_line_gets_no_confident_key_stub_skey():
    y = _atonal_line()
    dur = len(y) / SR22

    def lv():                       # lv-chordia's real output on this line (probe: no-chord share 1.0)
        return [{"start_time": 0.0, "end_time": dur, "chord": "N"}]

    _assert_no_confident_key(_analyse(y, _SKeyAt(), lv))


@pytest.mark.real
def test_random_pitch_line_gets_no_confident_key_real_models(skey, tmp_path):
    from scipy.io import wavfile

    from mvh.stages.harmony import chords as C
    from mvh.testing import heavy

    y = _atonal_line()
    wav = tmp_path / "atonal22k.wav"
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
    _assert_no_confident_key(res)
