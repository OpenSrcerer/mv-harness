# ruff: noqa: E501
"""Scoring helpers for the M2 stages against the synthetic ground truth (tests/contract/synth/_truth/truth.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from mvh.stages.rhythm.fusion import f_measure

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"


def truth() -> dict[str, Any]:
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)


def ev(out: Path, name: str) -> list[dict[str, Any]]:
    from mvh.contract import catalog
    ed = catalog.event_def(name)
    with open(Path(out) / ed.file, encoding="utf-8") as fh:
        return json.load(fh)["items"]


def rhythm_scores(out: Path, tr: dict[str, Any] | None = None) -> dict[str, Any]:
    tr = tr or truth()
    beats = ev(out, "beats")
    bars = ev(out, "bars")
    t_beats = [b for b in tr["beats"] if b["in_pulse"]]
    est_all = [b["t"] for b in beats]
    # beats where the truth has a pulse (scoring the estimate's beats inside the truth pulse regions)
    regions = [(r["t"], r["end"]) for r in tr["pulse_regions"] if r["in_pulse"]]

    def inside(t):
        return any(a - 0.035 <= t < b - 0.035 for a, b in regions)

    est_in = [t for t in est_all if inside(t)]
    f_beats = f_measure(est_in, [b["t"] for b in t_beats], 0.07)
    t_down = [b["t"] for b in tr["beats"] if b["beat_in_bar"] == 1 and b["in_pulse"] and b["bar"] > 0]
    e_down = [b["t"] for b in beats if b["beat_in_bar"] == 1 and inside(b["t"]) and b["bar"] > 0]
    f_down = f_measure(e_down, t_down, 0.07)
    with open(Path(out) / "meta" / "tempo.json", encoding="utf-8") as fh:
        tempo = json.load(fh)
    # timing error of matched beats
    tb = np.array([b["t"] for b in t_beats])
    errs = [abs(t - tb[np.argmin(np.abs(tb - t))]) for t in est_in]
    pickup = [b for b in beats if b["bar"] == 0]
    b16 = [b for b in bars if abs(b["t"] - 31.0) < 0.07]
    # pulse agreement per truth beat
    agree = []
    for b in tr["beats"]:
        j = int(np.argmin(np.abs(np.array(est_all) - b["t"])))
        if abs(est_all[j] - b["t"]) < 0.07:
            agree.append(beats[j]["in_pulse"] == b["in_pulse"])
        else:
            agree.append(False)
    return {"f_beats": round(f_beats, 4), "f_downbeats": round(f_down, 4), "tempo_err": round(abs(tempo["bpm"] - tr["bpm"]), 3),
            "median_abs_err_ms": round(1000 * float(np.median(errs)), 2) if errs else None,
            "p95_abs_err_ms": round(1000 * float(np.percentile(errs, 95)), 2) if errs else None,
            "pickup_beats": len(pickup), "pickup_t": pickup[0]["t"] if pickup else None,
            "pickup_beat_in_bar": pickup[0]["beat_in_bar"] if pickup else None,
            "bar16_beats_in_bar": b16[0]["beats_in_bar"] if b16 else None, "bar16_n": b16[0]["n_beats"] if b16 else None,
            "pulse_agreement": round(float(np.mean(agree)), 3), "meter_changes": tempo["meter"]["changes"],
            "n_beats": len(beats), "truth_n_beats": len(tr["beats"])}
