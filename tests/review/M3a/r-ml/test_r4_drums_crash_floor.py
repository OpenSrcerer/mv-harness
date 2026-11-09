"""R-ML review M3a round 4, finding R4-1: the round-3 fix (``cymbal_rise_db`` 8 -> 4 in ``drums.core.drumsep_hits``)
lowers the rise floor of the CRASH stem as well as the ride stem, and on real songs the crash stem's low-rise
candidates are DrumSep artefacts: they have no high-frequency event in the DrumSep INPUT (the drums stem the
sub-stems were separated from) and sit on the 16th-note grid no more often than random instants.

Measured on the integrator's max runs (out/_wip/integrator/<slug>, CPU DrumSep per D47) with the fixer's rerun
(out/_wip/fixer-m3a-r3/<slug>): jeremy cymbals 169 -> 275, of the 116 added 81 come from the crash stem; those 81 show a
>= 3 dB 6-16 kHz rise in the drums stem at 6 % of the hits (random instants: 9 %), and sit within 20 ms of a 16th
position at 16 % (chance 28 %), while the 35 added ride hits are real (71 % / 69 %). megafauna: 34 added crash hits,
6 % / 21 %. A cymbal stroke that DrumSep puts in a sub-stem is a stroke in its input; a crash-stem "onset" with
nothing in the input is energy moving between sub-stems.

The test re-runs ``drumsep_hits`` (as the drums stage does, with the classifier's cymbal confirmations) on the
integrator's sub-stems and requires that the ride / crash hits that rise less than 8 dB in their own sub-stem (the
hits the lowered floor admits) be an event in the drums stem at least half of the time. Reads real-song stems
(numbers only, no lyrics); skips when the integrator folder is absent. About 1-2 min.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[4]
RUNS = REPO / "out" / "_wip" / "integrator"
SUBS = ("kick", "snare", "toms", "hihat", "ride", "crash")


def _load(folder: Path, rel: str) -> tuple[np.ndarray, int]:
    from mvh.io import audio as aio
    from mvh.io.wav import read_wav

    p = folder / rel
    wav = p.with_suffix(".wav")
    if wav.is_file():
        x, sr = read_wav(wav)
        return np.asarray(x, np.float64).mean(axis=0), sr
    d = aio.decode(p)
    return np.asarray(d.samples, np.float64).mean(axis=0), d.sr


def _hf_db(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    from scipy import signal

    y = signal.sosfiltfilt(signal.butter(4, [6000 / (sr / 2), 16000 / (sr / 2)], btype="bandpass", output="sos"), x)
    bs = int(round(sr / 1000))
    e = (y[: y.size // bs * bs] ** 2).reshape(-1, bs).mean(axis=1)
    return 10 * np.log10(e + 1e-14), bs


@pytest.mark.parametrize("slug", ["jeremy", "megafauna"])
def test_low_rise_cymbal_hits_are_events_in_the_drumsep_input(slug):
    from mvh.stages.drums import core

    folder = RUNS / slug
    if not (folder / "stems" / "drums" / "crash.flac").is_file() or not (folder / "events" / "beats.json").is_file():
        pytest.skip(f"no integrator run in {folder}")
    subs, sr = {}, 44100
    for s in SUBS:
        subs[s], sr = _load(folder, f"stems/drums/{s}.flac")
    drums, _ = _load(folder, "stems/drums.flac")
    prm = core.DetectParams()
    ch, _ = core.classify(drums, sr, prm)
    hits, _ = core.drumsep_hits(subs, sr, prm, cymbal_confirm=[h.t for h in ch if h.drum == "cymbal"])
    low = [h for h in hits if h.drum == "cymbal" and h.sub_stem in ("ride", "crash") and h.rise_db < 8.0]
    if len(low) < 10:
        return   # the floor admits (almost) nothing below 8 dB: nothing to judge
    hf, bs = _hf_db(drums, sr)

    def rise(t: float) -> float:
        k = int(round(t * sr)) // bs
        return float(hf[k:k + 10].mean() - hf[max(0, k - 25):k - 3].mean())

    with open(folder / "events" / "beats.json", encoding="utf-8") as fh:
        beats = np.array([b["t"] for b in json.load(fh)["items"]])
    grid = np.sort(np.concatenate([beats[:-1] + (beats[1:] - beats[:-1]) * q / 4 for q in range(4)] + [beats[-1:]]))

    def on_grid(t: float) -> bool:
        j = np.searchsorted(grid, t)
        return min(abs(grid[k] - t) for k in (j - 1, j) if 0 <= k < grid.size) <= 0.020

    ev = np.array([rise(h.t) >= 3.0 for h in low])
    crash = [h for h in low if h.sub_stem == "crash"]
    ibi = float(np.median(np.diff(beats)))
    msg = (f"{slug}: {len(low)} ride/crash hits rise < 8 dB in their sub-stem ({len(crash)} from the crash stem); "
           f"only {ev.mean():.2f} of them have a >= 3 dB 6-16 kHz rise in the drums stem (DrumSep input); "
           f"crash-stem ones {np.mean([rise(h.t) >= 3.0 for h in crash]) if crash else float('nan'):.2f}; "
           f"on the 16th grid {np.mean([on_grid(h.t) for h in low]):.2f} (chance {40.0 / (ibi / 4 * 1000):.2f}); "
           f"cymbals total {sum(h.drum == 'cymbal' for h in hits)}")
    assert ev.mean() >= 0.5, msg
