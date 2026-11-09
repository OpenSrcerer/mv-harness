"""R-ML review M3a round 5, finding R5-1: the round-4 rule M3a-R4-3 (``coinc_decay_db`` in ``drums.core.drumsep_hits``)
drops real ride strokes that coincide with a KICK.

The rule is justified as "snare crack leaking into the ride / crash stem dies out faster than a cymbal", and on the
synthetic song every hit it drops is indeed at a snare stroke with the snare stem louder in 4-16 kHz than the copy
(0.5 / 9.5 / 16.5 / 30.875 s: truth = snare). But it fires on ANY kick / snare / tom stroke within +-6 ms, with a
threshold (9 dB of 4-16 kHz decay from the first 30 ms to 150-180 ms) tuned on the synthetic ride sample. Real ride
sounds decay faster than that: MEGAFAUNA's kept ride hits that are not at a drum stroke decay > 9 dB 88 % of the time
(median 17.4 dB), Jeremy's 25 %. So a real ride stroke that lands on a kick is dropped unless the full-stem classifier
happens to confirm it. A kick has no 4-16 kHz energy to leak: at the dropped hits the ride stem is 10-37 dB above the
kick stem and 18-37 dB above the snare stem in 4-16 kHz, its 4-16 kHz waveform correlates 0.91-0.95 with the drums
stem (the DrumSep input) and not with the snare stem (-0.82..0.27).

The test re-runs ``drumsep_hits`` exactly as the drums stage does (classifier cymbal confirmations, the drums stem as
``drums_mix``) on the integrator's sub-stems, with and without the rule, and requires that the rule remove no hit that
is (a) at no snare / tom hit (+-8 ms; so only a kick can have triggered the rule), (b) at least 3 dB louder in 4-16 kHz
(first 40 ms) than the kick stem (not a misrouted kick click) and (c) at least 10 dB louder there than the snare stem.
Fails now: MEGAFAUNA 161.97 / 166.54 / 171.12 s, Jeremy 66.71 / 191.86 s. Numbers only. About 1-2 min.
"""
from __future__ import annotations

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
        try:
            x, sr = read_wav(wav)
            return np.asarray(x, np.float64).mean(axis=0), sr
        except ValueError:
            pass
    d = aio.decode(p.with_suffix(".flac"))
    return np.asarray(d.samples, np.float64).mean(axis=0), d.sr


def _hf(x: np.ndarray, sr: int) -> np.ndarray:
    from scipy import signal

    return signal.sosfiltfilt(signal.butter(4, [4000 / (sr / 2), 16000 / (sr / 2)], btype="bandpass", output="sos"), x)


@pytest.mark.parametrize("slug", ["megafauna", "jeremy"])
def test_coincidence_decay_rule_does_not_drop_kick_coincident_rides(slug):
    from mvh.stages.drums import core

    folder = RUNS / slug
    if not (folder / "stems" / "drums" / "ride.flac").is_file():
        pytest.skip(f"no integrator run in {folder}")
    subs, sr = {}, 44100
    for s in SUBS:
        subs[s], sr = _load(folder, f"stems/drums/{s}")
    drums, _ = _load(folder, "stems/drums")
    prm = core.DetectParams()
    ch, _ = core.classify(drums, sr, prm)
    conf = [h.t for h in ch if h.drum == "cymbal"]
    cur, st = core.drumsep_hits(subs, sr, prm, cymbal_confirm=conf, drums_mix=drums)
    off, _ = core.drumsep_hits(subs, sr, prm, cymbal_confirm=conf, drums_mix=drums, coinc_decay_db=1e9)
    kept = np.array(sorted(h.t for h in cur if h.drum == "cymbal"))
    lost = [h for h in off if h.drum == "cymbal" and (kept.size == 0 or np.abs(kept - h.t).min() > 0.010)]
    hf = {s: _hf(subs[s], sr) for s in ("kick", "snare", "ride", "crash")}
    n = int(0.040 * sr)

    def db(s: str, s0: int) -> float:
        return float(10 * np.log10(np.mean(hf[s][s0:s0 + n] ** 2) + 1e-20))

    st_t = np.array(sorted(h.t for h in off if h.drum in ("snare", "tom")))
    bad = []
    for h in lost:
        if st_t.size and np.abs(st_t - h.t).min() <= 0.008:
            continue   # a snare / tom stroke: the leak the rule is meant for
        own = db(h.sub_stem, h.sample)
        sn, kk = db("snare", h.sample), db("kick", h.sample)
        if own - kk >= 3.0 and own - sn >= 10.0:
            bad.append(f"{h.t:.3f}s {h.sub_stem} rise {h.rise_db:.1f} dB, 4-16 kHz {own - sn:.0f} dB over snare / "
                       f"{own - kk:.0f} dB over kick")
    assert not bad, (f"{slug}: the coincidence-decay rule (M3a-R4-3) dropped {len(bad)} of its {len(lost)} hits although "
                     f"they sit on a kick only and are louder in 4-16 kHz than the kick and snare stems (real ride / crash strokes, "
                     f"not snare leakage): {bad}")
