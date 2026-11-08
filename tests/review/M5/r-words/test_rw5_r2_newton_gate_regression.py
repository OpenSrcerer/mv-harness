# ruff: noqa: E501
"""R-WORDS M5 round 2 (major, regression from the A2 fix): newton, the stress test, drops from grade B to C.

The A2 fix (M5-D31) raised the emission context floor from 2 s to 6 s per side (``align.MIN_CTX_S``). The measured
gate G1-G8 (docs/spike/bench-words.md §5) was calibrated on the SPIKE recipe, "30 s windows with 2 s of context each
side", where newton grades B with G2 0.777 and G4 0.083. With 6 s of context the MMS token scores change everywhere
(mean |delta log p| 0.2-1.1 per frame, not only near seams), and on newton many more words fall under the score
cut-offs although their timing does not change:

=======================  ==========  =========  ========================================================
alignment only (probe)   G4 hard     G2 cov     word start vs LCS-matched whisper word (p >= 0.5, 382 words)
=======================  ==========  =========  ========================================================
ctx 2, no seam clamp     0.094       0.778      within 0.3 s 0.963, > 1 s: 3
ctx 6, no seam clamp     0.167       0.694      within 0.3 s 0.963, > 1 s: 6
ctx 6 + seam clamp (now) 0.186       0.694      within 0.3 s 0.942, > 1 s: 9
=======================  ==========  =========  ========================================================

End to end (this round's run of the stage on real-newton-vs-nye, LRCLIB 3921433, offset -1.305): grade C, fails
G2 0.683 (< 0.75) and G4 0.198 (> 0.12), "lyrics grade C: check the alignment in the viewer", confidence 0.5;
round 1 (2 s context): grade B, G2 0.763, G4 0.099. Jeremy moves the other way (G4 0.072 -> 0.057), so the gate
now measures the emission recipe, not the alignment. Fix: keep the SPIKE recipe (2 s) for the gate's scores, or
re-calibrate G2/G4 on the four W0 songs with the new recipe (and record it in SPIKE/decisions), or use overlapping
windows that keep the 2 s recipe's central frames and only replace the seam frames.

Opt-in (real song, real model): ``-m real`` or ``MVH_REAL_TESTS=1``. Prints numbers only, never lyric text.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.real

REPO = Path(__file__).resolve().parents[4]
STEM = REPO / "tests" / "contract" / "real-newton-vs-nye" / "stems" / "lead_vocals.flac"
LRCLIB = REPO / "tests" / ".cache" / "real" / "newton-vs-nye" / "http" / "get_no_album.json"


@pytest.fixture(scope="module")
def newton_alignment():
    if not (STEM.is_file() and LRCLIB.is_file()):
        pytest.skip("real newton stem / cached LRCLIB answer not present")
    from tests.synth.m5.harness import slot

    from mvh.io import audio as aio
    from mvh.runner import models
    from mvh.stages.lyrics import align as A
    from mvh.stages.lyrics import core as C
    from mvh.stages.lyrics import grade as G
    from mvh.stages.lyrics import text as T

    entry = json.loads(LRCLIB.read_text(encoding="utf-8"))
    assert entry["id"] == 3921433
    src = T.parse_lrc(entry["syncedLyrics"])
    lead = aio.decode(STEM, sr=16000, mono=True).samples[0]
    h = models.handle("mms_fa")
    with slot("r-words-m5-r2:review-test", threads=6):
        al = A.MmsAligner(next(iter(h.files.values())), 6)
        logp = al.emissions(lead, 30.0, 2.0)          # the stage defaults (window_s, context_s)
    tm = T.TokenMaker(al.dictionary, "en")
    lines = [C._mk_line(ln["text"], t=ln.get("t"), end=ln.get("end"), words_src=ln.get("words"), speaker=None,
                        backing=ln.get("backing", False), order=i, tm=tm) for i, ln in enumerate(src["lines"])]
    starts, ends = C._expected(lines, len(lead) / 16000.0)
    toks = [x["toks"] for x in lines]
    back = [x["backing"] for x in lines]
    res, _ = A.align_groups(logp, starts, ends, toks, offset=0.0, backing=back)
    devs = [r[0]["start"] - x["src_t"] for x, r in zip(lines, ([a for a in rr if a is not None] for rr in res))
            if r and np.mean([a["score"] for a in r]) >= 0.1]
    off = float(np.median(devs))
    if abs(off) > G.THRESHOLDS["offset_apply"]:
        res, _ = A.align_groups(logp, starts, ends, toks, offset=off, backing=back)
    n = sum(len(x["words"]) for x in lines)
    scores = [r["score"] for rr in res for r in rr if r is not None]
    g2 = sum(1 for s in scores if s >= 0.10) / n
    g4 = sum(1 for rr in res for r in rr if r is None or r["score"] < 0.01) / n
    return {"offset": off, "G2": g2, "G4": g4}


def test_newton_offset_is_found(newton_alignment):
    assert abs(newton_alignment["offset"] - (-1.33)) < 0.1


def test_newton_alignment_scores_stay_in_the_calibrated_gate(newton_alignment):
    g2, g4 = newton_alignment["G2"], newton_alignment["G4"]
    assert g2 >= 0.75 and g4 <= 0.12, (f"newton (SPIKE: grade B, G2 0.777, G4 0.083) now aligns with G2 {g2:.3f} (>= 0.75) "
                                       f"and G4 {g4:.3f} (<= 0.12): the 6 s emission context moved the scores the gate was "
                                       f"calibrated on")
