# ruff: noqa: E501  (long numeric tables / docstrings)
"""Pure-numpy pitch logic of the vocals stage (owner M3b): arbitration, gating, octave repair, note segmentation,
phrases, range statistics, register and the eased pitch01 curve. All arrays are on the 100 Hz contract grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

RATE = 100


def hz_to_midi(hz: np.ndarray) -> np.ndarray:
    hz = np.asarray(hz, np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(hz > 0, 69.0 + 12.0 * np.log2(np.maximum(hz, 1e-9) / 440.0), np.nan)


def midi_to_hz(m: np.ndarray | float) -> np.ndarray:
    return 440.0 * 2.0 ** ((np.asarray(m, np.float64) - 69.0) / 12.0)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[(start, end_exclusive)] of True runs."""
    m = np.asarray(mask, bool).astype(np.int8)
    d = np.diff(np.concatenate([[0], m, [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def to_grid(t_src: np.ndarray, v: np.ndarray, n: int, fill: float = np.nan) -> np.ndarray:
    """Nearest-sample resampling of a frame series onto the 100 Hz grid (frame i at i / 100 s)."""
    t_src = np.asarray(t_src, np.float64)
    if t_src.size == 0:
        return np.full(n, fill)
    idx = np.clip(np.searchsorted(t_src, np.arange(n) / RATE), 0, t_src.size - 1)
    prev = np.clip(idx - 1, 0, t_src.size - 1)
    tt = np.arange(n) / RATE
    pick = np.where(np.abs(t_src[prev] - tt) < np.abs(t_src[idx] - tt), prev, idx)
    return np.asarray(v, np.float64)[pick]


@dataclass
class Arbitration:
    midi: np.ndarray       # fractional MIDI, NaN unvoiced
    conf: np.ndarray       # 0..1
    both: int              # frames where both trackers were voiced
    agree: float           # fraction of those within 1 semitone
    octave: float          # fraction an octave apart (RMVPE kept)


def arbitrate(rm_midi: np.ndarray, rm_conf: np.ndarray, sw_midi: np.ndarray | None, sw_conf: np.ndarray | None,
              gate: float = 0.3, sw_gate: float = 0.9) -> Arbitration:
    """RMVPE is the arbiter (docs/SPIKE.md): a frame is voiced when RMVPE conf >= gate; its pitch is RMVPE's. SwiftF0 is
    the second opinion: agreement within a semitone keeps full confidence, an octave disagreement x0.85, any other
    disagreement x0.7. SwiftF0 never makes a frame voiced on its own (rap: never used for presence)."""
    rm = np.asarray(rm_midi, np.float64)
    rc = np.clip(np.asarray(rm_conf, np.float64), 0, 1)
    voiced = (rc >= gate) & np.isfinite(rm)
    midi = np.where(voiced, rm, np.nan)
    conf = rc.copy()
    both, agree, octv = 0, 0.0, 0.0
    if sw_midi is not None and sw_conf is not None:
        sv = (np.asarray(sw_conf) >= sw_gate) & np.isfinite(sw_midi)
        b = voiced & sv
        both = int(b.sum())
        if both:
            dm = rm[b] - np.asarray(sw_midi)[b]
            ok = np.abs(dm) < 1.0
            oc = np.abs(np.abs(dm) - 12.0) < 1.0
            agree, octv = float(ok.mean()), float(oc.mean())
            f = np.ones(both)
            f[oc] = 0.85
            f[~ok & ~oc] = 0.7
            conf[np.flatnonzero(b)] *= f
    return Arbitration(midi, conf, both, agree, octv)


def fix_octave_islands(midi: np.ndarray, max_len: int = 15) -> np.ndarray:
    """Within a voiced run, a short island (<= max_len frames) an octave away from both neighbours is folded back."""
    m = np.asarray(midi, np.float64).copy()
    for a, b in runs(np.isfinite(m)):
        seg = m[a:b]
        if seg.size < 3:
            continue
        r = np.round(seg)
        # islands of frames whose rounded pitch jumps by ~12 from the previous frame
        i = 1
        while i < seg.size:
            d = seg[i] - seg[i - 1]
            if abs(abs(d) - 12) < 1.5:
                j = i
                while j + 1 < seg.size and abs(seg[j + 1] - seg[j]) < 1.5:
                    j += 1
                if j - i + 1 <= max_len and j + 1 < seg.size and abs(abs(seg[j + 1] - seg[j]) - 12) < 1.5:
                    seg[i:j + 1] -= np.sign(d) * 12
                i = j + 1
            else:
                i += 1
        del r
        m[a:b] = seg
    return m


def drop_short(midi: np.ndarray, min_frames: int = 5) -> np.ndarray:
    m = np.asarray(midi, np.float64).copy()
    for a, b in runs(np.isfinite(m)):
        if b - a < min_frames:
            m[a:b] = np.nan
    return m


def median_filter_voiced(midi: np.ndarray, k: int = 5) -> np.ndarray:
    m = np.asarray(midi, np.float64)
    out = m.copy()
    h = k // 2
    for a, b in runs(np.isfinite(m)):
        seg = m[a:b]
        for i in range(seg.size):
            out[a + i] = np.median(seg[max(0, i - h): i + h + 1])
    return out


def segment_notes(midi: np.ndarray, level_db: np.ndarray | None = None, conf: np.ndarray | None = None,
                  tol: float = 0.75, hold: int = 4, min_frames: int = 8, dip_db: float = 9.0) -> list[dict]:
    """Notes from a 100 Hz f0 track: within voiced runs a note continues while the (5-frame median) pitch stays within
    ``tol`` semitones of the note's running median; a deviation held for ``hold`` frames starts a new note; a level dip of
    ``dip_db`` (syllable boundary) also splits. Returns [{t, d, midi, median, conf, i0, i1}]."""
    sm = median_filter_voiced(midi, 5)
    notes: list[dict] = []
    for a, b in runs(np.isfinite(sm)):
        cuts = [a]
        if level_db is not None and b - a > 2 * min_frames:
            lv = np.asarray(level_db[a:b], np.float64)
            for i in range(min_frames, lv.size - min_frames):
                w = lv[i - min_frames: i + min_frames + 1]
                if lv[i] == w.min() and min(lv[i - min_frames: i].max(), lv[i + 1: i + min_frames + 1].max()) - lv[i] >= dip_db:
                    cuts.append(a + i)
        cuts.append(b)
        for s0, s1 in zip(cuts[:-1], cuts[1:]):
            i = s0
            while i < s1:
                start = i
                ref = float(np.median(sm[i: min(s1, i + 3)]))
                dev = 0
                j = i + 1
                while j < s1:
                    if abs(sm[j] - ref) > tol:
                        dev += 1
                        if dev >= hold:
                            j -= hold - 1
                            break
                    else:
                        dev = 0
                        ref = float(np.median(sm[start: j + 1]))
                    j += 1
                end = min(j, s1)
                if end - start >= min_frames:
                    seg = np.asarray(midi[start:end], np.float64)
                    med = float(np.nanmedian(seg))
                    q = int(round(med))
                    stab = float(np.mean(np.abs(seg - med) <= 0.5))
                    c = float(np.nanmean(conf[start:end])) if conf is not None else 1.0
                    notes.append({"t": start / RATE, "d": (end - start) / RATE, "midi": q, "median": med,
                                  "conf": max(0.0, min(1.0, c * (0.5 + 0.5 * stab))), "i0": start, "i1": end})
                i = max(end, start + 1)
    return notes


def phrases(midi: np.ndarray, gap_s: float = 0.45, min_s: float = 0.3) -> list[tuple[int, int]]:
    """Voiced runs joined across rests shorter than gap_s; [(i0, i1)] with i1 exclusive."""
    rs = runs(np.isfinite(midi))
    out: list[list[int]] = []
    for a, b in rs:
        if out and (a - out[-1][1]) / RATE < gap_s:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out if (b - a) / RATE >= min_s]


REGISTERS_MALE = ((50.0, "bass"), (58.0, "baritone"), (999.0, "tenor"))
REGISTERS_FEMALE = ((64.0, "alto"), (69.0, "mezzo"), (999.0, "soprano"))


def register_of(median_midi: float, female_share: float) -> str:
    """Coarse voice type (low confidence): male/female from CED, then the median sung pitch."""
    table = REGISTERS_FEMALE if female_share > 0.5 else REGISTERS_MALE
    for hi, name in table:
        if median_midi < hi:
            return name
    return table[-1][1]


def sustained_extremes(notes: Sequence[dict], f0_hz: np.ndarray, min_note_s: float = 0.15,
                       min_total_s: float = 0.3, join_gap_s: float = 0.12) -> tuple[dict | None, dict | None]:
    """Lowest and highest sustained notes: among notes >= min_note_s, the lowest/highest MIDI pitch whose total sustained
    time is >= min_total_s (falls back to the extreme single note). Each: {midi, name, hz, t}."""
    from mvh.stages.notes.post import note_name

    # same-pitch notes split only by a short unvoiced consonant count as one held note
    spans: list[dict] = []
    for nt in sorted(notes, key=lambda x: x["t"]):
        if spans and spans[-1]["midi"] == nt["midi"] and nt["t"] - (spans[-1]["t"] + spans[-1]["d"]) <= join_gap_s:
            sp = spans[-1]
            sp["d"] = nt["t"] + nt["d"] - sp["t"]
            sp["i1"] = nt["i1"]
        else:
            spans.append({"t": nt["t"], "d": nt["d"], "midi": nt["midi"], "i0": nt["i0"], "i1": nt["i1"]})
    cand = [n for n in spans if n["d"] >= min_note_s]
    if not cand:
        return None, None
    tot: dict[int, float] = {}
    for n in cand:
        tot[n["midi"]] = tot.get(n["midi"], 0.0) + n["d"]
    ok = sorted(m for m, s in tot.items() if s >= min_total_s) or sorted(tot)

    def pick(m: int) -> dict:
        best = max((n for n in cand if n["midi"] == m), key=lambda n: (n["d"], -n["t"]))
        hz = np.asarray(f0_hz[best["i0"]: best["i1"]], np.float64)
        hz = hz[np.isfinite(hz)]
        return {"midi": int(m), "name": note_name(int(m)), "hz": round(float(np.median(hz)) if hz.size else float(midi_to_hz(m)), 2),
                "t": round(best["t"], 3)}

    return pick(ok[0]), pick(ok[-1])


def pitch01(midi: np.ndarray, lo: float, hi: float, ease_s: float = 0.15) -> np.ndarray:
    """(midi - lo) / (hi - lo) clipped to 0..1 where voiced; held through gaps; at each voicing onset the held value
    ramps linearly to the new value over the last ``ease_s`` of the gap (the whole gap when shorter), so the curve never
    jumps and never holds NaN (0 when nothing is voiced)."""
    m = np.asarray(midi, np.float64)
    n = m.size
    v = np.isfinite(m)
    if not v.any() or not np.isfinite(lo) or not np.isfinite(hi):
        return np.zeros(n, np.float32)
    x = np.where(v, np.clip((m - lo) / max(hi - lo, 1e-6), 0.0, 1.0), np.nan)
    out = np.empty(n)
    first = int(np.flatnonzero(v)[0])
    out[:first] = x[first]
    last = x[first]
    k = max(1, int(round(ease_s * RATE)))
    i = first
    while i < n:
        if v[i]:
            out[i] = x[i]
            last = x[i]
            i += 1
            continue
        j = i
        while j < n and not v[j]:
            j += 1
        out[i:j] = last
        if j < n:  # ease into the next voiced value
            L = min(k, j - i)
            out[j - L: j] = last + (x[j] - last) * (np.arange(1, L + 1) / (L + 1))
        i = j
    return out.astype(np.float32)


def level_db_100hz(y: np.ndarray, sr: int, n: int, win_s: float = 0.04) -> np.ndarray:
    """Centred RMS level (dBFS, floor -120) at 100 Hz."""
    p = np.asarray(y, np.float64) ** 2
    c = np.concatenate([[0.0], np.cumsum(p)])
    h = max(1, int(round(win_s * sr / 2)))
    ctr = np.round(np.arange(n) * sr / RATE).astype(np.int64)
    a, b = np.clip(ctr - h, 0, p.size), np.clip(ctr + h, 0, p.size)
    e = (c[b] - c[a]) / np.maximum(b - a, 1)
    return np.maximum(10 * np.log10(np.maximum(e, 1e-12)), -120.0)
