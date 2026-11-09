"""Support for the R-DSP review tests of M1 (spectral, loudness, dynamics).

* ``viz_causal``: runs the REAL viz/js/audio.js ``AudioEngine.update()`` under Node, frame by frame at a browser frame
  rate, fed with the AnalyserNode data a browser would deliver (causal block of the last fftSize samples of the mono
  down-mix, Web Audio Blackman window, |X|/N, 20 log10). This is the independent reference for "viz-port fidelity".
* ``run_spectral`` / ``run_all``: the M1 stages in-process through the builder's FakeCtx harness (tests/synth/m1).
* small synthetic signal builders with exact truth (one-shots from tests/synth/dsp, the generator of the contract
  fixture song).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
VIZ_AUDIO_JS = REPO.parent / "viz" / "js" / "audio.js"
SYNTH = REPO / "tests" / "contract" / "synth"
SR = 44100


def node() -> str | None:
    return shutil.which("node")


def have_viz() -> bool:
    return node() is not None and VIZ_AUDIO_JS.is_file()


# ------------------------------------------------------------------------------------------------ causal viz
def analyser_frames(x: np.ndarray, sr: int, fps: tuple[int, int] = (60, 1), n_fft: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """What a Web Audio AnalyserNode (fftSize n_fft, smoothingTimeConstant 0) returns at frame k (now = (k+1)/fps):
    per-bin dB of the last n_fft samples of the mono down-mix 0.5 (L + R), and those samples."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    mono = 0.5 * (x[0] + x[1]) if x.shape[0] > 1 else x[0]
    num, den = fps
    n_frames = int(np.floor(mono.size / sr * num / den))
    a = 0.16
    i = np.arange(n_fft)
    w = (1 - a) / 2 - 0.5 * np.cos(2 * np.pi * i / n_fft) + a / 2 * np.cos(4 * np.pi * i / n_fft)
    pad = np.concatenate([np.zeros(n_fft), mono])
    db = np.empty((n_frames, n_fft // 2), np.float32)
    tm = np.empty((n_frames, n_fft), np.float32)
    for k in range(n_frames):
        end = int(round((k + 1) * den / num * sr)) + n_fft  # index in pad
        blk = pad[end - n_fft : end]
        X = np.fft.rfft(blk * w)[: n_fft // 2] / n_fft
        mag = np.abs(X)
        with np.errstate(divide="ignore"):
            db[k] = np.where(mag > 0, 20 * np.log10(np.maximum(mag, 1e-300)), -1000.0)
        tm[k] = blk
    return db, tm


def viz_causal(x: np.ndarray, sr: int, work: Path, fps: tuple[int, int] = (60, 1), time_domain: bool = True) -> dict[str, Any]:
    """Run viz/js/audio.js causally on the signal; returns per-frame arrays (numpy) incl. registered hits."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    db, tm = analyser_frames(x, sr, fps)
    fb = work / "frames.bin"
    with open(fb, "wb") as fh:
        nt = tm.shape[1] if time_domain else 0
        np.array([sr, db.shape[0], db.shape[1], nt, fps[0], fps[1]], dtype="<i4").tofile(fh)
        inter = (np.concatenate([db, tm], axis=1) if time_domain else db).astype("<f4")
        inter.tofile(fh)
    oj = work / "viz_out.json"
    r = subprocess.run([node(), str(HERE / "viz_causal.cjs"), str(VIZ_AUDIO_JS), str(fb), str(oj)], capture_output=True,
                       timeout=600, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    with open(oj, encoding="utf-8") as fh:
        out = json.load(fh)
    return {k: np.asarray(v, dtype=np.float64) for k, v in out.items()}


def frame_times(mask: np.ndarray, t: np.ndarray) -> np.ndarray:
    return t[np.asarray(mask) > 0.5]


# ------------------------------------------------------------------------------------------------ stages
def run_spectral(x: np.ndarray, sr: int, out: Path, params: dict | None = None):
    from tests.synth.m1.harness import run_m1

    r = run_m1(x, sr, Path(out), stages=("spectral",), params={"spectral": params} if params else None)
    return r["ctx"]["spectral"]


def run_all(x: np.ndarray, sr: int, out: Path, bars: list[dict] | None = None, audio_path: Path | None = None):
    from tests.synth.m1.harness import run_m1

    r = run_m1(x, sr, Path(out), bars=bars, audio_path=audio_path)
    return r


def f1(est, ref, tol: float) -> tuple[float, float, float]:
    """Greedy one-to-one matching within +-tol (nearest first): (F1, precision, recall)."""
    est = sorted(float(e) for e in est)
    ref = sorted(float(r) for r in ref)
    pairs = sorted((abs(e - r), i, j) for i, e in enumerate(est) for j, r in enumerate(ref) if abs(e - r) <= tol)
    ue, ur = set(), set()
    for _, i, j in pairs:
        if i not in ue and j not in ur:
            ue.add(i)
            ur.add(j)
    tp = len(ue)
    p = tp / len(est) if est else 0.0
    r_ = tp / len(ref) if ref else 0.0
    return (2 * p * r_ / (p + r_) if p + r_ else 0.0), p, r_


# ------------------------------------------------------------------------------------------------ signals
def kicks_over_bass(duration_s: float = 24.0, bpm: float = 120.0, bass_gain: float = 0.6, kick_gain: float = 0.9,
                    sr: int = SR) -> tuple[np.ndarray, list[float]]:
    """Four-on-the-floor kick one-shots (the contract fixture's kick, tests/synth/dsp.kick, faded tail) over one
    sustained bass note per bar that starts with the downbeat kick (the fixture's bars 3-4 / 13-15 texture; gains as in
    tests/synth/song/render.py). Truth = the kicks' first samples."""
    from tests.synth import dsp

    x = np.zeros((2, int(duration_s * sr)))
    ref: list[float] = []
    beat = 60.0 / bpm
    bar = 4 * beat
    t = 0.5
    b = 0
    roots = [33, 29, 36, 31]
    k = min(int(0.45 * sr), int(0.15 * sr))
    while t + bar < duration_s - 0.6:
        for s in range(4):
            i = int(round((t + s * beat) * sr))
            kk = dsp.kick(0.95, sr)
            kk[kk.size - k :] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))
            dsp.place(x, dsp.pan(kk * kick_gain, 0.0), i)
            ref.append(i / sr)
        dsp.place(x, dsp.pan(dsp.bass_note(roots[b % 4], bar * 0.95, 0.8, sr) * bass_gain, 0.0), int(round(t * sr)))
        t += bar
        b += 1
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, ref


def synth_song() -> tuple[np.ndarray, int, dict[str, Any], list[dict]]:
    from mvh.io import audio as aio

    d = aio.decode(SYNTH / "_intermediate" / "ingest" / "canonical.wav")
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        truth = json.load(fh)
    with open(SYNTH / "events" / "bars.json", encoding="utf-8") as fh:
        bars = json.load(fh)["items"]
    return np.asarray(d.samples, dtype=np.float64), int(d.sr), truth, bars


def breakdown_drop_song(sr: int = SR, seed: int = 5) -> tuple[np.ndarray, float]:
    """44 s at 120 BPM (2 s bars): full groove 0-12 s, a pad-only breakdown 12-28 s (no drums, no bass), THE DROP at
    28.0 s (crash + kick + sub bass + full groove to 44 s). No silence before the drop (the Versatile case: breakdown
    straight into the drop). Returns (audio, drop time)."""
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded

    dur = 44.0
    x = np.zeros((2, int(dur * sr)))
    beat = 0.5

    def put(sig, t, g=1.0):
        dsp.place(x, sig * g, int(round(t * sr)))

    def groove(t0, t1, kg, hg, bg, sg):
        t, k = t0, 0
        while t < t1 - 1e-9:
            put(_faded(dsp.kick(0.9, sr, seed=1), sr), t, kg)
            put(dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr), 0.3), t + beat / 2, hg)
            if k % 2 == 1:
                put(_faded(dsp.snare(0.8, sr, seed=2), sr), t, sg)
            if k % 2 == 0:
                put(dsp.bass_note([33, 36][(k // 4) % 2], 0.9, 0.8, sr), t, bg)
            t += beat
            k += 1

    groove(0.0, 12.0, 0.7, 0.2, 0.5, 0.4)
    for t in np.arange(0.0, 28.0, 4.0):
        for m in (57, 60, 64):
            put(dsp.pad_note(m, 4.0, 0.5, sr), t, 0.5)
    put(dsp.pan(dsp.crash(1.0, 2.5, sr), 0.0), 28.0, 0.5)
    groove(28.0, 44.0, 1.0, 0.3, 0.9, 0.55)
    x += 10 ** (-80 / 20) * np.random.default_rng(seed).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, 28.0


# ------------------------------------------------------------------------------------------------ round 2 signals
def kicks_bass_hats(hats: str = "16ths", bass_gain: float = 0.6, bpm: float = 120.0, hat_gain: float = 0.3,
                    duration_s: float = 24.0, sr: int = SR) -> tuple[np.ndarray, list[float]]:
    """``kicks_over_bass`` plus closed hats (the fixture's hihat one-shot): '16ths', 'offbeat' (the house off-beat hat)
    or 'none'. bass_gain 0 leaves the bass out. Truth = the kicks' first samples."""
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded

    x = np.zeros((2, int(duration_s * sr)))
    ref: list[float] = []
    beat = 60.0 / bpm
    bar = 4 * beat
    t, b = 0.5, 0
    roots = [33, 29, 36, 31]
    k = int(0.15 * sr)
    steps = {"16ths": [q / 4 for q in range(16)], "offbeat": [q + 0.5 for q in range(4)], "none": []}[hats]
    while t + bar < duration_s - 0.6:
        for s in range(4):
            i = int(round((t + s * beat) * sr))
            kk = dsp.kick(0.95, sr)
            kk[kk.size - k :] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))
            dsp.place(x, dsp.pan(kk * 0.9, 0.0), i)
            ref.append(i / sr)
        if bass_gain > 0:
            dsp.place(x, dsp.pan(dsp.bass_note(roots[b % 4], bar * 0.95, 0.8, sr) * bass_gain, 0.0), int(round(t * sr)))
        for q in steps:
            dsp.place(x, dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr) * hat_gain, 0.3), int(round((t + q * beat) * sr)))
        t += bar
        b += 1
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, ref


def kicks_on_a_grid(times: list[float], kind: str = "fixture", crash_every_s: float | None = None,
                    crash_gain: float = 0.5, sr: int = SR) -> np.ndarray:
    """Kick one-shots at ``times`` ('fixture' = tests/synth/dsp.kick with a faded tail; 'tight' = a 70 ms-decay kick
    with the same 3 ms 1.5 kHz click, as a metal double-bass kick), optionally under a crash cymbal (tests/synth/dsp.crash,
    2.5 s) struck every ``crash_every_s`` (a rock chorus wash)."""
    from scipy import signal as ss
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded

    dur = times[-1] + 1.5
    x = np.zeros((2, int(dur * sr)))

    def tight() -> np.ndarray:
        n = int(0.3 * sr)
        tt = np.arange(n) / sr
        f = 55.0 + 100.0 * np.exp(-tt / 0.02)
        body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / 0.07)
        hp = ss.butter(4, 1500, "highpass", fs=sr, output="sos")
        click = ss.sosfilt(hp, np.random.default_rng(3).standard_normal(n)) * np.exp(-tt / 0.003) * 0.35
        z = body + click
        return 0.9 * z / np.max(np.abs(z))

    for t in times:
        k = _faded(dsp.kick(0.95, sr), sr) if kind == "fixture" else tight()
        dsp.place(x, dsp.pan(k, 0.0), int(round(t * sr)))
    if crash_every_s:
        t = 0.3
        while t < dur - 1.0:
            dsp.place(x, dsp.pan(dsp.crash(1.0, 2.5, sr) * crash_gain, 0.0), int(t * sr))
            t += crash_every_s
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x


def grid_times(bpm: float, per_beat: int, n_bars: int, start: float = 0.5) -> list[float]:
    step = 60.0 / bpm / per_beat
    return [start + i * step for i in range(4 * per_beat * n_bars)]


def kick_stem_attacks(path: Path, rise_db: float = 20.0, top_db: float = 6.0) -> list[float]:
    """Unambiguous kicks in a DrumSep kick sub-stem: the <= 300 Hz level (2.5 ms RMS) rises >= rise_db over the 17.5 ms
    before and peaks within top_db of the stem's p99.5 level (70 ms hold-off)."""
    from scipy import signal as ss

    from mvh.io import audio as aio

    d = aio.decode(path)
    x = np.asarray(d.samples, np.float64)
    sr = int(d.sr)
    m = x.mean(axis=0) if x.ndim > 1 else x
    lo = ss.sosfiltfilt(ss.butter(4, 300, "lowpass", fs=sr, output="sos"), m)
    hop = int(0.0025 * sr)
    n = lo.size // hop
    e = 20 * np.log10(np.sqrt(np.mean(lo[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12))
    top = float(np.percentile(e, 99.5))
    out: list[float] = []
    i = 8
    while i < e.size - 16:
        pre = float(e[i - 8 : i - 1].mean())
        pk = float(e[i : i + 12].max())
        if pk - pre >= rise_db and pk >= top - top_db and e[i] - e[i - 1] > 3.0:
            out.append(i * hop / sr)
            i += int(0.07 / (hop / sr))
        else:
            i += 1
    return out


# ------------------------------------------------------------------------------------------------ round 3
def bass_riff_kicks(bpm: float = 128.0, bars: int = 8, bass_steps=range(16), hat_steps=range(16), bass_gain: float = 0.5,
                    hat_gain: float = 0.3, kick_steps=(0, 4, 8, 12), staccato: float = 0.8,
                    sr: int = SR) -> tuple[np.ndarray, list[float]]:
    """Four-on-the-floor fixture kicks over a staccato 16th-note bass riff (A1 A1 A2 A1 C2 A1 A2 G1: the rock / EDM
    gallop) with closed 16th hats. Truth = the kicks' first samples."""
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded

    beat = 60.0 / bpm
    s16 = beat / 4
    x = np.zeros((2, int((0.5 + bars * 4 * beat + 1.0) * sr)))
    ref: list[float] = []
    notes = [33, 33, 45, 33, 36, 33, 45, 31]
    k = int(0.15 * sr)
    for b in range(bars):
        t0 = 0.5 + b * 4 * beat
        for s in kick_steps:
            i = int(round((t0 + s * s16) * sr))
            kk = dsp.kick(0.95, sr)
            kk[kk.size - k :] *= 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))
            dsp.place(x, dsp.pan(kk * 0.9, 0.0), i)
            ref.append(i / sr)
        for s in bass_steps:
            dsp.place(x, dsp.pan(dsp.bass_note(notes[s % 8], s16 * staccato, 0.8, sr) * bass_gain, 0.0), int(round((t0 + s * s16) * sr)))
        for s in hat_steps:
            dsp.place(x, dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr) * hat_gain, 0.3), int(round((t0 + s * s16) * sr)))
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, ref
