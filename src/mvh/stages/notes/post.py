"""Note post-processing shared by the notes and vocals stages (owner M3b): monophonic reduction, activity masking,
velocities from the stem level, note names and per-source statistics. Pure numpy."""

from __future__ import annotations

from typing import Sequence

import numpy as np

NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
Note = tuple[float, float, int, float]  # (t_on, t_off, midi, amplitude/conf)


def note_name(m: int) -> str:
    """MIDI -> name with C4 = 60 (CONTRACT §4)."""
    return f"{NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def monophonic(notes: Sequence[Note], min_d: float = 0.05) -> list[Note]:
    """One note at a time: at overlaps the stronger note wins; the weaker one is trimmed (or dropped when it would be
    shorter than ``min_d``). An octave/fifth 'ghost' starting with a stronger note is removed (bass harmonics)."""
    ns = sorted(notes, key=lambda n: (n[0], -n[3]))
    out: list[list] = []
    for t0, t1, m, a in ns:
        if out:
            p = out[-1]
            if t0 < p[1]:  # overlap with the previous kept note
                if abs(t0 - p[0]) < 0.04:  # simultaneous onsets: keep the stronger (prefer the lower on near ties)
                    if a > p[3] * 1.15 or (a >= p[3] * 0.87 and m < p[2]):
                        out[-1] = [t0, t1, m, a]
                    continue
                if a >= p[3] * 0.6 or t1 > p[1]:
                    p[1] = t0  # cut the previous note at this onset
                    if p[1] - p[0] < min_d:
                        out.pop()
                else:
                    continue  # a weak note inside a stronger one
        out.append([t0, t1, m, a])
    return [(float(a), float(b), int(m), float(x)) for a, b, m, x in out if b - a >= min_d]


def activity_fraction(t0: float, t1: float, active_100hz: np.ndarray | None) -> float:
    if active_100hz is None or active_100hz.size == 0:
        return 1.0
    a = int(np.floor(t0 * 100))
    b = max(a + 1, int(np.ceil(t1 * 100)))
    seg = active_100hz[max(0, a): min(active_100hz.size, b)]
    return float(np.mean(seg > 0.5)) if seg.size else 0.0


def mask_by_activity(notes: Sequence[Note], active_100hz: np.ndarray | None, min_frac: float = 0.5,
                     pad_s: float = 0.1) -> list[Note]:
    """Drop notes that lie mostly where the stem is inactive (PLAN §5: notes are masked by activity)."""
    if active_100hz is None:
        return list(notes)
    return [n for n in notes if activity_fraction(n[0] - pad_s, n[1] + pad_s, active_100hz) >= min_frac]


def onset_levels_db(notes: Sequence[Note], y: np.ndarray, sr: int, win_s: float = 0.06) -> np.ndarray:
    """Peak RMS (dBFS) of the stem in [t_on, t_on + win] per note."""
    out = np.full(len(notes), -120.0)
    w = max(1, int(win_s * sr))
    hop = max(1, w // 4)
    for i, (t0, _t1, _m, _a) in enumerate(notes):
        s = int(t0 * sr)
        seg = y[max(0, s): s + w + hop * 3]
        if seg.size < 8:
            continue
        frames = [seg[k: k + hop] for k in range(0, max(1, seg.size - hop + 1), hop)]
        e = max(float(np.mean(np.square(f, dtype=np.float64))) for f in frames if f.size)
        out[i] = 10 * np.log10(max(e, 1e-12))
    return out


def velocities(levels_db: np.ndarray, amp: np.ndarray) -> np.ndarray:
    """0..1 velocity: stem level at the onset normalised per source (p05..p99 -> 0.15..1), blended with the model
    amplitude so that notes of equal level but weaker evidence read slightly softer."""
    if levels_db.size == 0:
        return levels_db
    lo, hi = np.percentile(levels_db, 5), np.percentile(levels_db, 99)
    lv = np.clip((levels_db - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    v = 0.15 + 0.85 * (0.8 * lv + 0.2 * np.clip(amp, 0, 1))
    return np.clip(v, 0.0, 1.0)


def stats(items: Sequence[dict], duration_s: float) -> dict:
    """notes.json per-source statistics (CONTRACT files/notes_index)."""
    if not items:
        return {"count": 0, "lowest": None, "highest": None, "pc_histogram": [0.0] * 12, "density_per_s": 0.0}
    ms = np.array([it["midi"] for it in items], int)
    pc = np.bincount(ms % 12, minlength=12).astype(float)
    pc /= pc.sum()
    return {"count": int(ms.size), "lowest": int(ms.min()), "highest": int(ms.max()),
            "pc_histogram": [round(float(x), 4) for x in pc],
            "density_per_s": round(float(ms.size / max(duration_s, 1e-9)), 4)}


def audio_onsets(y: np.ndarray, sr: int, fmax: float | None = None) -> np.ndarray:
    """Onset times (s) of a stem from a fine spectral-flux envelope (librosa, ~2.9 ms hop at 22.05 kHz), used to refine
    model note onsets (basic-pitch frames are 11.6 ms and its onsets jitter by tens of ms on sustained bass)."""
    import librosa

    hop = 64
    S = np.abs(librosa.stft(np.asarray(y, np.float32), n_fft=1024, hop_length=hop, center=True))
    if fmax:
        S = S[: int(np.ceil(fmax / (sr / 1024))) + 1]
    env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S, ref=np.max), sr=sr, hop_length=hop, lag=2,
                                       max_size=3)
    fr = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units="frames", backtrack=False,
                                    pre_max=8, post_max=8, pre_avg=30, post_avg=30, delta=0.07 * float(env.max(initial=1)),
                                    wait=12)
    return librosa.frames_to_time(fr, sr=sr, hop_length=hop)


def snap_onsets(notes: Sequence[Note], onsets: np.ndarray, reach_s: float = 0.07) -> list[Note]:
    """Move each note onset to the nearest audio onset within ``reach_s`` (offsets unchanged)."""
    if onsets is None or len(onsets) == 0:
        return list(notes)
    out = []
    for t0, t1, m, a in notes:
        k = int(np.argmin(np.abs(onsets - t0)))
        if abs(onsets[k] - t0) <= reach_s and onsets[k] < t1 - 0.02:
            t0 = float(onsets[k])
        out.append((t0, t1, m, a))
    out.sort(key=lambda n: (n[0], n[2]))
    return out


def merge_fragments(notes: Sequence[Note], onsets: np.ndarray | None, max_gap: float = 0.03, short: float = 0.13,
                    near: float = 0.035) -> list[Note]:
    """Merge contiguous same-pitch notes when one of them is a short fragment and no audio onset sits at the join
    (a re-triggered decode of one sustained note); drop short octave-below 'ghosts' at the tail of a note."""
    ns = sorted(notes, key=lambda n: (n[0], n[2]))
    out: list[list] = []
    for t0, t1, m, a in ns:
        if out:
            p = out[-1]
            joined = abs(t0 - p[1]) <= max_gap and m == p[2]
            frag = (p[1] - p[0]) < short or (t1 - t0) < short
            hit = onsets is not None and len(onsets) and float(np.min(np.abs(np.asarray(onsets) - t0))) <= near
            if joined and frag and not hit:
                p[1] = max(p[1], t1)
                p[3] = max(p[3], a)
                continue
        out.append([t0, t1, m, a])
    res = []
    for i, (t0, t1, m, a) in enumerate(out):
        if (t1 - t0) < short and i > 0:
            q = out[i - 1]
            if q[2] - m == 12 and t0 <= q[1] + max_gap and i + 1 < len(out) and out[i + 1][0] - t1 <= max_gap:
                continue  # octave-below ghost between two notes
        res.append((float(t0), float(t1), int(m), float(a)))
    return res
