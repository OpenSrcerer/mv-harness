"""Lyric coverage as voice evidence (CR-M3b-1) and the lead-stem pick when the karaoke split is suspect."""

from __future__ import annotations

import numpy as np

from mvh.stages.instruments.lead import p95_db, pick_lead_stem
from mvh.stages.vocals import _lyric_mask


class _Up:
    def __init__(self, doc):
        self.doc = doc

    def json(self, rel):
        assert rel == "lyrics/lyrics.json"
        if self.doc is None:
            raise RuntimeError("missing")
        return self.doc


class _Ctx:
    def __init__(self, doc=None, lead=None, voc=None):
        self.doc, self.stems = doc, {"lead_vocals": lead, "vocals": voc}

    def upstream(self, name):
        assert name == "lyrics"
        return _Up(self.doc)

    def audio(self, name, sr=None, mono=False):
        class A:
            pass

        a = A()
        a.samples = np.asarray(self.stems[name], np.float32)[None, :]
        return a


def test_lyric_mask_pads_lines_and_ignores_instrumental():
    doc = {"instrumental": False, "grade": "B", "lines": [{"t": 1.0, "d": 2.0}, {"t": 10.0, "d": 1.0}]}
    m, k = _lyric_mask(_Ctx(doc), 1500, 0.1, [])
    assert k == 2 and m[100] and m[85 + 20] is np.True_ and not m[50] and m[1050] and not m[500]
    assert abs(m.sum() / 100 - (2.2 + 1.2)) < 0.03
    m2, k2 = _lyric_mask(_Ctx({"instrumental": True, "lines": [{"t": 1.0, "d": 2.0}]}), 1500, 0.1, [])
    assert k2 == 0 and not m2.any()


def test_lyric_mask_is_empty_when_lyrics_unreadable():
    w: list[str] = []
    m, k = _lyric_mask(_Ctx(None), 500, 0.1, w)
    assert k == 0 and not m.any() and w


def test_pick_lead_stem_falls_back_to_vocals_when_lead_is_nearly_silent():
    rng = np.random.default_rng(0)
    voc = (0.2 * rng.standard_normal(16000 * 3)).astype(np.float32)
    quiet, loud = 1e-4 * voc, 0.9 * voc
    assert pick_lead_stem(_Ctx(lead=quiet, voc=voc))[0] == "vocals"
    assert pick_lead_stem(_Ctx(lead=loud, voc=voc))[0] == "lead_vocals"
    assert p95_db(np.zeros(100, np.float32)) == -180.0


def test_lyric_mask_ignores_unaligned_lines():
    lines = [{"t": 1.0, "d": 2.0, "conf": 0.0, "timing_source": "interpolated"},
             {"t": 5.0, "d": 2.0, "conf": 0.5, "timing_source": "lrclib_line"},
             {"t": 9.0, "d": 2.0, "conf": 0.0, "timing_source": "ctc"},
             {"t": 13.0, "d": 1.0, "conf": 0.4, "timing_source": "ctc"}]
    mask, k = _lyric_mask(_Ctx({"instrumental": False, "grade": "B", "lines": lines}), 2000, 0.0, [])
    assert k == 1 and mask[1350] and not mask[200] and not mask[600] and not mask[1000]


def test_lyric_mask_needs_acoustic_support_beyond_the_aligner():
    """R-ML-M3b-r5-1: grade-D lines that no ASR heard are not voice evidence; an ASR match >= 0.3 (G1) is."""
    lines = [{"t": 1.0, "d": 2.0, "conf": 0.2, "timing_source": "ctc"}]
    w: list[str] = []
    m, k = _lyric_mask(_Ctx({"instrumental": False, "grade": "D", "lines": lines}), 500, 0.0, w)
    assert k == 0 and not m.any() and w
    doc = {"instrumental": False, "grade": "D", "lyrics_match_score": 0.12, "lines": lines}
    assert _lyric_mask(_Ctx(doc), 500, 0.0, [])[1] == 0
    doc = {"instrumental": False, "grade": "D", "gate": {"checks": {"G1": {"value": 0.57}}}, "lines": lines}
    assert _lyric_mask(_Ctx(doc), 500, 0.0, [])[1] == 1
