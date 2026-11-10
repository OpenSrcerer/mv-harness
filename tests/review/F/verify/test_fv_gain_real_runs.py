"""fverify F-V3 / F-V4 (major): checks on the finished runs of the gain fix (out/_wip/ffix-gain, current code with
separate_hq forced) against the W4 reference runs (out/_wip/w4fix-analysis-r2, pre-fix code).

F-V3: DrumSep at the analysis level costs cymbal accuracy on a quiet (-20 LUFS) mix. On the 44.1 kHz synthetic song the
cymbal F1 against ground truth fell 0.895 -> 0.778 (-12 dB copy 0.919 -> 0.833); on the 48 kHz copy it fell below the
PLAN gate (0.686 < 0.7, tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py, which passed at the W4 final gate).
F-V4: W4V2-GAIN-VOCALS is still open: vocal phrases of MEGAFAUNA -12 / -20 dB copies keep IoU 0.788 (lyrics alignment,
CR-F-gain-2)."""

from __future__ import annotations

import json
import sys

import pytest
from fv_support import GAIN, REPO, W4, cover_iou, events, has

pytestmark = pytest.mark.real


def _cym_f1(folder):
    sys.path.insert(0, str(REPO / "tests" / "review" / "M3a" / "r-ml"))
    from m3a_rml_util import scores, truth

    with open(folder / "events" / "drum_hits.json", encoding="utf-8") as fh:
        return scores(json.load(fh)["items"], truth()["drum_hits"])["cymbal"]


@pytest.mark.parametrize("name", ["synth_base", "synth_gm12"])
def test_fv_synthetic_cymbals_do_not_regress(name):
    new, old = GAIN / name, W4 / name
    if not (has(new, "drum_hits") and has(old, "drum_hits")):
        pytest.skip("needs both run folders")
    a, b = _cym_f1(old), _cym_f1(new)
    assert b >= a - 0.05, f"{name}: cymbal F1 vs truth {a:.3f} (W4) -> {b:.3f} (DrumSep at the analysis level, F-gain-1)"


@pytest.mark.parametrize("name", ["megafauna_gm12", "megafauna_gm20"])
def test_fv_megafauna_vocal_phrases_survive_a_gain_change(name):
    base, g = GAIN / "megafauna", GAIN / name
    if not (has(base, "vocal_phrases") and has(g, "vocal_phrases")):
        pytest.skip("needs the ffix-gain runs")
    iou = cover_iou(events(base, "vocal_phrases"), events(g, "vocal_phrases"))
    assert iou >= 0.9, f"{name}: vocal phrase coverage IoU {iou:.3f} vs megafauna (lyrics alignment, CR-F-gain-2)"
