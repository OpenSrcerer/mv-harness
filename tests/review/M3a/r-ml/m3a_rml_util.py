"""Scoring helpers for the M3a R-ML review tests (numpy only)."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SYNTH = REPO / "tests" / "contract" / "synth"
TOL = 0.010  # PLAN §7 (kick events +-10 ms; the builder's tests use it for every drum)


def truth() -> dict:
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)


def f1(est, ref, tol=TOL) -> float:
    from mvh.stages.drums import core

    return core.match_f1(list(est), list(ref), tol)[0]


def scores(items, ref_hits, drums=("kick", "snare", "hat", "tom", "cymbal"), tol=TOL) -> dict[str, float]:
    return {d: round(f1([it["t"] for it in items if it["drum"] == d],
                        [h["t"] for h in ref_hits if h["drum"] == d], tol), 3) for d in drums}
MONO_SPAN = (17, 29)  # s: the mono excerpt (chorus duet, then the build)


def oracle_substems():
    """The generator's clean DrumSep-style sub-stems (mono float64) and their rate."""
    import numpy as np

    from mvh.io import audio as aio

    subs, sr = {}, 44100
    for s in ("kick", "snare", "toms", "hihat", "ride", "crash"):
        d = aio.decode(SYNTH / "stems" / "drums" / f"{s}.flac")
        subs[s], sr = d.samples.mean(axis=0, dtype=np.float64), d.sr
    return subs, sr
