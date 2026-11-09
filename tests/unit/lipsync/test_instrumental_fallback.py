"""lipsync M5-D49 (seam S07): when lyrics says instrumental (no lines, no words, no voices) the ungated wordless
fallback is kept only for a substantial wordless vocal (>= instrumental_fallback_min_s in total), so a vocal chop
does not open the mouth. Runs the stage on the synthetic song's stems with an instrumental lyrics stub; no models
(visemes and phonemes off)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"


def _instrumental_upstream(h) -> None:
    h.materialise("lyrics")
    h.materialise("voices")
    lp = h.stage_dir("lyrics") / "lyrics" / "lyrics.json"
    doc = json.loads(lp.read_text(encoding="utf-8"))
    doc.update(lines=[], words=[], instrumental=True, grade=None)
    lp.write_text(json.dumps(doc), encoding="utf-8")
    for p in (h.stage_dir("voices") / "events").glob("voice_spans.json"):
        ev = json.loads(p.read_text(encoding="utf-8"))
        ev["items"] = []
        p.write_text(json.dumps(ev), encoding="utf-8")
    vp = h.stage_dir("voices") / "meta" / "voices.json"
    if vp.is_file():
        vm = json.loads(vp.read_text(encoding="utf-8"))
        vm["voices"] = []
        vp.write_text(json.dumps(vm), encoding="utf-8")


@pytest.mark.parametrize("min_s,opens", [(1000.0, False), (8.0, True)], ids=["chop_suppressed", "vocalise_kept"])
def test_instrumental_fallback(tmp_path, min_s, opens):
    from tests.synth.m5.harness import Harness

    h = Harness(SYNTH, tmp_path)
    _instrumental_upstream(h)
    rec = h.run("lipsync", stub_deps=("lyrics", "voices"),
                params={"visemes": False, "phonemes": False, "instrumental_fallback_min_s": min_s})
    mo = h.curve("lipsync", "vocal.mouth_open")
    fb = rec["result"]["summary"]["ungated_fallback_s"]
    if opens:
        assert fb >= 8.0 and float(mo.max()) > 0.1     # the synth lead sings ~40 s: a vocalise keeps the fallback
    else:
        assert fb == 0 and float(np.max(mo)) == 0.0
