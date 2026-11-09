"""Synthetic test signals for the M1 stages (spectral, loudness, dynamics) with exact ground truth.

* ``groove``: kick / snare / hat one-shots (tests.synth.dsp) on a syncopated pattern with varying velocities, over an
  optional sustained bass line, pad and noise floor. Truth = the one-shots' first samples (PLAN §7.2 "event time =
  the one-shot's sample onset").
* ``dynamics_song``: a 64 s arrangement with an intro, a quiet breakdown, a 16 s build (rising level, riser, snare
  roll), a full stop into digital silence, a drop (impact), a loud plateau, a final hit and a 4 s decay tail.
  Truth = section times, the impact/stop/silence/decay-tail times and the expected level ordering.

All audio is float64 stereo [2, n] at 44.1 kHz unless ``sr`` is given.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from tests.synth import dsp

SR = 44100


def _faded(x: np.ndarray, sr: int, fade_s: float = 0.15) -> np.ndarray:
    """The tests.synth.dsp one-shots end abruptly (a kick still has ~-20 dB left after its 0.45 s): fade the last 150 ms
    with a raised cosine so the truncation does not add a click (a spurious onset) after every hit."""
    y = np.array(x, dtype=np.float64, copy=True)
    k = min(y.shape[-1], int(fade_s * sr))
    y[..., y.shape[-1] - k :] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))
    return y


def _kick_pattern(bars: int, bpm: float, offset_s: float, syncopated: bool, rng: np.random.Generator,
                  dense: bool = False) -> list[tuple[float, float]]:
    """(time, velocity) of kicks: four on the floor plus syncopated 16ths (and dense 16th runs)."""
    beat = 60.0 / bpm
    out = []
    for b in range(bars):
        t0 = offset_s + b * 4 * beat
        steps = [0, 4, 8, 12]
        if syncopated:
            steps += [[3, 10], [6, 14], [7], [11, 15]][b % 4]
        if dense and b % 4 == 3:
            steps += [13, 14, 15]
        for s in sorted(set(steps)):
            v = 0.95 if s % 4 == 0 else float(rng.uniform(0.45, 0.8))
            out.append((t0 + s * beat / 4, v))
    return out


def groove(duration_s: float = 24.0, *, bpm: float = 124.0, offset_s: float = 0.5, bass: bool = True, pad: bool = True,
           hats: bool = True, snares: bool = True, syncopated: bool = True, dense: bool = False,
           gain_db: float = 0.0, sr: int = SR, seed: int = 11) -> tuple[np.ndarray, int, dict[str, Any]]:
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * sr))
    x = np.zeros((2, n))
    bars = int((duration_s - offset_s - 0.6) / (4 * 60.0 / bpm))
    beat = 60.0 / bpm
    kicks = _kick_pattern(bars, bpm, offset_s, syncopated, rng, dense)
    truth: dict[str, Any] = {"kick": [], "snare": [], "hat": [], "bass_notes": [], "bpm": bpm}
    for t, v in kicks:
        i = int(round(t * sr))
        dsp.place(x, _faded(dsp.kick(v, sr, seed=1 + i % 7), sr) * 0.9, i)
        truth["kick"].append({"t": i / sr, "vel": v})
    if snares:
        for b in range(bars):
            for s in (4, 12):
                t = offset_s + b * 4 * beat + s * beat / 4
                i = int(round(t * sr))
                v = float(rng.uniform(0.6, 0.9))
                dsp.place(x, _faded(dsp.snare(v, sr, seed=2 + i % 5), sr) * 0.55, i)
                truth["snare"].append({"t": i / sr, "vel": v})
    if hats:
        for b in range(bars):
            for s in range(0, 16, 2):
                t = offset_s + b * 4 * beat + s * beat / 4
                i = int(round(t * sr))
                v = 0.8 if s % 4 == 2 else 0.5
                dsp.place(x, dsp.pan(_faded(dsp.hihat(v, False, sr, seed=4 + i % 3), sr) * 0.3, 0.3), i)
                truth["hat"].append({"t": i / sr, "vel": v})
    if bass:
        # sustained bass notes that change on off-beats (sub energy that the kick detector must ignore)
        notes = [33, 33, 36, 31]
        for b in range(bars):
            for h in range(2):
                t = offset_s + b * 4 * beat + (h * 2 + 0.5) * beat
                i = int(round(t * sr))
                dsp.place(x, dsp.bass_note(notes[(b * 2 + h) % 4], 1.6 * beat, 0.8, sr) * 0.6, i)
                truth["bass_notes"].append(i / sr)
    if pad:
        for b in range(0, bars, 2):
            t = offset_s + b * 4 * beat
            for m in (57, 60, 64):
                dsp.place(x, dsp.pad_note(m, 8 * beat, 0.5, sr) * 0.6, int(round(t * sr)))
    x += 10 ** (-70 / 20) * np.random.default_rng(seed + 1).standard_normal(x.shape)  # noise floor
    pk = float(np.max(np.abs(x)))
    x *= 10 ** (-1.0 / 20) / pk * 10 ** (gain_db / 20)
    return x, sr, truth


def dynamics_song(sr: int = SR, seed: int = 21) -> tuple[np.ndarray, int, dict[str, Any]]:
    """64 s at 120 BPM (2 s bars). Sections (s): intro 0-8 (light groove, -14 dB), main 8-24 (full groove),
    breakdown 24-32 (pad only, no drums, no bass), build 32-46 (snare roll + riser + rising level), stop 46 ->
    digital silence 46-48, drop 48 (impact: crash + kick + sub) loud plateau 48-60, final hit 60 then decay tail to 64."""
    rng = np.random.default_rng(seed)
    dur = 64.0
    n = int(dur * sr)
    x = np.zeros((2, n))
    beat = 0.5

    def put(sig, t, g=1.0):
        dsp.place(x, sig * g, int(round(t * sr)))

    def groove_bars(t0, t1, kick_g, hats_g, bass_g, snare_g):
        t = t0
        k = 0
        while t < t1 - 1e-9:
            put(_faded(dsp.kick(0.9, sr, seed=1), sr), t, kick_g)
            if hats_g:
                put(dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr), 0.3), t + beat / 2, hats_g)
            if snare_g and k % 2 == 1:
                put(_faded(dsp.snare(0.8, sr, seed=2), sr), t, snare_g)
            if bass_g and k % 2 == 0:
                put(dsp.bass_note([33, 36][(k // 4) % 2], 0.9, 0.8, sr), t, bass_g)
            t += beat
            k += 1

    # intro: light groove at -14 dB
    groove_bars(0.0, 8.0, 0.2, 0.06, 0.0, 0.0)
    # main: full groove
    groove_bars(8.0, 24.0, 0.8, 0.25, 0.5, 0.45)
    # pad through intro/main/breakdown
    for t in np.arange(0.0, 32.0, 4.0):
        for m in (57, 60, 64):
            put(dsp.pad_note(m, 4.0, 0.5, sr), t, 0.6 if t < 24 else 0.45)
    # build 32-46: snare roll accelerating + riser, rising gain
    t = 32.0
    while t < 46.0 - 1e-9:
        frac = (t - 32.0) / 14.0
        step = beat if frac < 0.4 else beat / 2 if frac < 0.75 else beat / 4
        put(_faded(dsp.snare(0.5 + 0.5 * frac, sr, seed=2), sr), t, 0.08 + 0.4 * frac)
        t += step
    rs = dsp.riser(14.0, sr)
    put(dsp.pan(rs, 0.0), 32.0, 0.35)
    # digital silence 46-48: cut everything at 46
    x[:, int(46.0 * sr) : int(48.0 * sr)] = 0.0
    # drop at 48: crash + loud groove with sub bass
    put(dsp.pan(dsp.crash(1.0, 2.5, sr), 0.0), 48.0, 0.5)
    groove_bars(48.0, 60.0, 1.0, 0.3, 0.9, 0.55)
    # final hit at 60 (kick + crash + low chord), then a 4 s decay tail
    put(_faded(dsp.kick(1.0, sr, seed=1), sr), 60.0, 1.0)
    put(dsp.pan(dsp.crash(1.0, 4.0, sr), 0.0), 60.0, 0.45)
    for m in (45, 52, 57):
        put(dsp.pan(dsp.piano_note(m, 3.9, 0.9, sr), 0.0), 60.0, 0.5)
    x[:, int(63.95 * sr):] *= np.linspace(1, 0, n - int(63.95 * sr))[None, :]
    x += 10 ** (-80 / 20) * rng.standard_normal(x.shape)
    x[:, int(46.0 * sr) : int(48.0 * sr)] = 0.0
    x *= 10 ** (-1.0 / 20) / float(np.max(np.abs(x)))
    truth = {
        "sections": [("intro", 0.0, 8.0), ("main", 8.0, 24.0), ("breakdown", 24.0, 32.0), ("build", 32.0, 46.0),
                     ("silence", 46.0, 48.0), ("drop", 48.0, 60.0), ("tail", 60.0, 64.0)],
        "impacts": [8.0, 48.0],  # main groove entry, the drop (the final hit at 60 is quieter than the plateau)
        "stops": [46.0],
        "silences": [(46.0, 48.0)],
        "decay_tails": [(60.0, 64.0)],
        "bars": [{"bar": k + 1, "t": 2.0 * k, "d": 2.0} for k in range(32)],
        "louder_than": [("drop", "main"), ("main", "breakdown"), ("main", "intro"), ("drop", "breakdown")],
    }
    return x, sr, truth


def f1(est: list[float], ref: list[float], tol: float) -> tuple[float, float, float, list[float]]:
    """Greedy one-to-one matching within +-tol: (F1, precision, recall, matched errors est - ref)."""
    est = sorted(est)
    ref = sorted(ref)
    used = [False] * len(est)
    errs = []
    j0 = 0
    for r in ref:
        best, bi = tol + 1e-12, -1
        for j in range(j0, len(est)):
            d = est[j] - r
            if d < -tol:
                j0 = j + 1
                continue
            if d > tol:
                break
            if not used[j] and abs(d) < best:
                best, bi = abs(d), j
        if bi >= 0:
            used[bi] = True
            errs.append(est[bi] - r)
    tp = len(errs)
    p = tp / len(est) if est else 0.0
    r_ = tp / len(ref) if ref else 0.0
    f = 2 * p * r_ / (p + r_) if p + r_ else 0.0
    return f, p, r_, errs
