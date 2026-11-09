"""HPSS + CQT chroma (harmony stage, PLAN §5).

One constant-Q transform of the harmonic part gives three views, all on the same frame grid:
``chroma``   [12, T]  pitch-class energy of C2..B7 (what chords and keys are scored on),
``bass``     [12, T]  pitch-class energy of C1..F#3 (bass line; inversions),
``energy``   [T]      frame energy of the harmonic part (silence masking, weights).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SR = 22050
HOP = 256                      # 86.13 fps: close to the 100 Hz output curve, divisible by 2**(n_octaves-1)
BPO = 36                       # three bins per semitone
N_OCT = 7                      # C1 (32.7 Hz) .. B7
CHROMA_LO_SEMI = 12            # C2: below this the CQT cannot resolve semitones, bass handles it
BASS_HI_SEMI = 31              # up to G3 (196 Hz)


@dataclass
class ChromaFrames:
    chroma: np.ndarray         # [12, T] linear magnitude (not normalised)
    bass: np.ndarray           # [12, T]
    energy: np.ndarray         # [T] harmonic RMS per frame
    times: np.ndarray          # [T] frame centres (s)
    tuning: float              # estimated tuning offset in semitones (-0.5..0.5)
    sr: int = SR
    hop: int = HOP

    @property
    def fps(self) -> float:
        return self.sr / self.hop

    def mask(self, floor_db: float = -45.0) -> np.ndarray:
        """Frames louder than floor_db relative to the 95th percentile energy (silence/pre-roll excluded)."""
        e = self.energy
        ref = np.percentile(e, 95) if e.size else 0.0
        if ref <= 1e-9:
            return np.zeros_like(e, dtype=bool)
        return e > ref * 10 ** (floor_db / 20)


def harmonic_part(y: np.ndarray, margin: float = 2.0) -> np.ndarray:
    import librosa

    return librosa.effects.harmonic(y, margin=margin)


def compute_chroma(y: np.ndarray, sr: int = SR, hop: int = HOP, margin: float = 2.0) -> ChromaFrames:
    """HPSS then CQT, folded to pitch classes. ``y`` mono float32 at ``sr``."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # librosa: n_fft too large for very short input, empty tuning set on silence
        return _compute_chroma(y, sr, hop, margin)


def _compute_chroma(y: np.ndarray, sr: int, hop: int, margin: float) -> ChromaFrames:
    import librosa

    y = np.asarray(y, np.float32)
    h = harmonic_part(y, margin)
    fmin = float(librosa.note_to_hz("C1"))
    try:
        tuning = float(librosa.estimate_tuning(y=h, sr=sr, bins_per_octave=12))
    except Exception:  # noqa: BLE001  (silent/degenerate input)
        tuning = 0.0
    if not np.isfinite(tuning):
        tuning = 0.0
    cqt = np.abs(librosa.cqt(h, sr=sr, hop_length=hop, fmin=fmin, n_bins=N_OCT * BPO, bins_per_octave=BPO,
                             tuning=tuning * BPO / 12.0, filter_scale=1.0, res_type="soxr_hq")).astype(np.float64)
    # semitone s (0 = C1) sits at bin 3 s; sum the centre bin and half of its neighbours (3-bin triangular window)
    n_semi = N_OCT * 12
    semi = np.zeros((n_semi, cqt.shape[1]))
    for s in range(n_semi):
        k = 3 * s
        acc = cqt[k].copy()
        if k > 0:
            acc += 0.5 * cqt[k - 1]
        if k + 1 < cqt.shape[0]:
            acc += 0.5 * cqt[k + 1]
        semi[s] = acc
    chroma = np.zeros((12, semi.shape[1]))
    bass = np.zeros((12, semi.shape[1]))
    for s in range(CHROMA_LO_SEMI, n_semi):
        chroma[s % 12] += semi[s]
    for s in range(0, BASS_HI_SEMI + 1):
        bass[s % 12] += semi[s]
    # harmonic RMS per frame on the same grid
    rms = librosa.feature.rms(y=h, frame_length=2048, hop_length=hop, center=True)[0]
    t = chroma.shape[1]
    if rms.shape[0] < t:
        rms = np.pad(rms, (0, t - rms.shape[0]))
    energy = rms[:t].astype(np.float64)
    times = np.arange(t) * hop / sr
    return ChromaFrames(chroma, bass, energy, times, tuning, sr, hop)


def normalise_frames(c: np.ndarray, how: str = "max") -> np.ndarray:
    """Per-frame normalisation of [12, T]; silent frames stay 0."""
    if how == "max":
        d = c.max(axis=0, keepdims=True)
    else:
        d = c.sum(axis=0, keepdims=True)
    return np.where(d > 1e-12, c / np.maximum(d, 1e-12), 0.0)


def aggregate(cf: ChromaFrames, t0: float = 0.0, t1: float | None = None, weight_energy: bool = True,
              which: str = "chroma") -> np.ndarray:
    """A 12-vector summarising [t0, t1): per-frame L1-normalised chroma weighted by sqrt(frame energy), silence skipped."""
    m = cf.mask()
    a = int(np.searchsorted(cf.times, t0, "left"))
    b = cf.chroma.shape[1] if t1 is None else int(np.searchsorted(cf.times, t1, "left"))
    if b <= a:
        return np.zeros(12)
    src = cf.chroma if which == "chroma" else cf.bass
    c = normalise_frames(src[:, a:b], "sum")
    w = m[a:b].astype(np.float64)
    if weight_energy:
        w = w * np.sqrt(cf.energy[a:b] / (np.percentile(cf.energy[m], 95) + 1e-12)) if m.any() else w
    return (c * w[None, :]).sum(axis=1)


def to_curve_100hz(cf: ChromaFrames, n_out: int, rate_hz: float = 100.0) -> np.ndarray:
    """Max-normalised chroma at ``rate_hz`` (sample i centred at i / rate): [12, n_out] float32 in 0..1.

    Frames more than 45 dB under the song's 95th-percentile harmonic energy (digital silence, pre-roll) are 0."""
    cn = normalise_frames(cf.chroma, "max")
    cn = np.where(cf.mask()[None, :], cn, 0.0)
    tq = np.arange(n_out) / rate_hz
    out = np.zeros((12, n_out), np.float32)
    for pc in range(12):
        out[pc] = np.interp(tq, cf.times, cn[pc]).astype(np.float32)
    return np.clip(out, 0.0, 1.0)
