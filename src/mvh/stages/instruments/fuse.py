# ruff: noqa: E501  (long numeric tables / docstrings)
"""Pure-numpy fusion of tagger and stem evidence into 1 Hz instrument curves and segments (owner M3b).

No model code here, so the rules are unit-testable on synthetic evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .vocab import HIPHOP_CONTEXT, RAP, SINGING, SPEECH, Inst

ON, OFF = 0.5, 0.35        # segment hysteresis on the fused probability
MIN_SEG_S = 2.0            # shortest segment
MAX_GAP_S = 2.0            # gaps up to this are bridged
OFF_ANCHOR_WEIGHT = 0.6   # tag weight on a non-anchor stem for an instrument the separator gives its own stem
STYLE_FLOOR = 0.05        # minimum summed singing+speech+rap evidence for a style label
INACTIVE_TAG_CAP = 0.6     # an anchored instrument whose stem is silent is believed at most this much


def window_activity(active_100hz: np.ndarray | None, n_frames: int, win_s: float = 4.0, hop_s: float = 1.0) -> np.ndarray:
    """Fraction of each 1 Hz window [i - win/2, i + win/2) in which a 100 Hz 0/1 activity curve is on."""
    if active_100hz is None:
        return np.zeros(n_frames, np.float32)
    a = (np.asarray(active_100hz, np.float64) > 0.5).astype(np.float64)
    c = np.concatenate([[0.0], np.cumsum(a)])
    out = np.zeros(n_frames, np.float32)
    h = int(round(win_s * 100 / 2))
    for i in range(n_frames):
        ctr = int(round(i * hop_s * 100))
        lo, hi = max(0, ctr - h), min(a.size, ctr + h)
        out[i] = (c[hi] - c[lo]) / (2 * h) if hi > lo else 0.0
    return out


def scale(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((np.asarray(x, np.float64) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)


def median3(x: np.ndarray) -> np.ndarray:
    if x.size < 3:
        return x.copy()
    p = np.concatenate([[x[0]], x, [x[-1]]])
    return np.median(np.stack([p[:-2], p[1:-1], p[2:]]), axis=0)


@dataclass
class Evidence:
    p: np.ndarray          # fused probability [n]
    tag: np.ndarray        # tagger evidence 0..1 [n]
    stem: np.ndarray       # anchor-stem activity fraction 0..1 [n] (zeros when no anchor)
    tag_src: np.ndarray    # index into ``sources`` of the strongest tag per frame
    sources: list[str]


def tag_evidence(inst: Inst, ced: Mapping[str, np.ndarray], label_idx: Sequence[int]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """(evidence 0..1, argmax source index, sources) from the CED probabilities of the mix and the inst's stems."""
    sources = [s for s in ("mix", *inst.stems) if s in ced]
    vals = []
    for s in sources:
        v = ced[s][:, label_idx].max(axis=1).astype(np.float64)
        if s == "mix":
            w = inst.mix_weight
        elif inst.anchor and s != inst.anchor and s not in ("vocals", "lead_vocals"):
            w = OFF_ANCHOR_WEIGHT  # an instrument with its own stem is less believed when tagged on another stem
        else:
            w = 1.0
        vals.append(v * w)
    if not vals:
        return np.zeros(0), np.zeros(0, np.int64), sources
    m = np.stack(vals)
    return scale(m.max(axis=0), inst.lo, inst.hi), m.argmax(axis=0), sources


def fuse(inst: Inst, e_tag: np.ndarray, e_stem: np.ndarray | None, parent_p: np.ndarray | None = None) -> np.ndarray:
    """The fusion rule (documented in docs/contract/decisions/M3b.md):
    anchored:  p = s * (w + (1 - w) * tag) + (1 - s) * min(tag, INACTIVE_TAG_CAP)   (s = anchor-stem activity fraction)
    otherwise: p = tag;  sub-types: p = min(p, parent p)."""
    tag = np.asarray(e_tag, np.float64)
    if inst.anchor and e_stem is not None:
        s = np.asarray(e_stem, np.float64)
        w = inst.stem_weight
        p = s * (w + (1 - w) * tag) + (1 - s) * np.minimum(tag, INACTIVE_TAG_CAP)
    else:
        p = tag
    if parent_p is not None:
        p = np.minimum(p, parent_p)
    return np.clip(median3(p), 0.0, 1.0).astype(np.float32)


def segments_1hz(p: np.ndarray, duration_s: float, on: float = ON, off: float = OFF, min_s: float = MIN_SEG_S,
                 max_gap_s: float = MAX_GAP_S) -> list[tuple[int, int]]:
    """Hysteresis segments on a 1 Hz curve: [(first frame, last frame)], gaps <= max_gap bridged, short ones dropped."""
    runs: list[list[int]] = []
    cur = None
    for i, v in enumerate(p):
        if cur is None and v >= on:
            cur = [i, i]
        elif cur is not None:
            if v >= off:
                cur[1] = i
            else:
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] - 1 <= max_gap_s:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    return [(a, b) for a, b in merged if (b - a + 1) >= min_s]


def frames_to_span(a: int, b: int, duration_s: float) -> tuple[float, float]:
    """1 Hz frames a..b cover [a - 0.5, b + 0.5) s, clipped to the song."""
    t0 = max(0.0, a - 0.5)
    t1 = min(duration_s, b + 0.5)
    return t0, max(t1, t0 + 0.01)


def snap_to_activity(t0: float, t1: float, active_100hz: np.ndarray | None, reach_s: float = 1.5) -> tuple[float, float]:
    """Move segment edges to the nearest on/off edge of a 100 Hz activity curve within ``reach_s``."""
    if active_100hz is None:
        return t0, t1
    a = (np.asarray(active_100hz) > 0.5).astype(np.int8)
    d = np.diff(np.concatenate([[0], a, [0]]))
    ons, offs = np.flatnonzero(d == 1) / 100.0, np.flatnonzero(d == -1) / 100.0
    if ons.size:
        k = np.argmin(np.abs(ons - t0))
        if abs(ons[k] - t0) <= reach_s:
            t0 = float(ons[k])
    if offs.size:
        k = np.argmin(np.abs(offs - t1))
        if abs(offs[k] - t1) <= reach_s and offs[k] > t0:
            t1 = float(offs[k])
    return t0, t1


def pitch_sustain(midi_16ms: np.ndarray, voiced: np.ndarray, n_frames: int, win_s: float = 4.0,
                  hop_s: float = 0.016, min_run_s: float = 0.12, tol: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """(sustain ratio, voiced seconds) per 1 Hz window from a frame-wise pitch track.

    A voiced frame is 'sustained' when it lies in a run of >= min_run_s whose pitch stays within +-tol semitones of the
    run's median (vibrato of +-40 cents passes). Singing holds notes (high ratio); speech and rap glide (low ratio)."""
    m = np.asarray(midi_16ms, np.float64)
    v = np.asarray(voiced, bool) & np.isfinite(m)
    sus = np.zeros(m.size, bool)
    k = max(2, int(round(min_run_s / hop_s)))
    i = 0
    while i < m.size:
        if not v[i]:
            i += 1
            continue
        j = i
        while j + 1 < m.size and v[j + 1] and abs(m[j + 1] - m[j]) < 0.7:
            j += 1
        seg = m[i:j + 1]
        # split the voiced run into stable pieces around a running median
        s0 = 0
        while s0 < seg.size:
            e = s0
            while e + 1 < seg.size and abs(seg[e + 1] - np.median(seg[s0:e + 2])) <= tol:
                e += 1
            if e - s0 + 1 >= k:
                sus[i + s0: i + e + 1] = True
            s0 = e + 1
        i = j + 1
    cv = np.concatenate([[0], np.cumsum(v)])
    cs = np.concatenate([[0], np.cumsum(sus)])
    ratio = np.zeros(n_frames)
    vsec = np.zeros(n_frames)
    for f in range(n_frames):
        lo = int(max(0, round((f - win_s / 2) / hop_s)))
        hi = int(min(m.size, round((f + win_s / 2) / hop_s)))
        if hi <= lo:
            continue
        nv = cv[hi] - cv[lo]
        vsec[f] = nv * hop_s
        ratio[f] = (cs[hi] - cs[lo]) / nv if nv > 0 else 0.0
    return ratio, vsec


def vocal_style_shares(ced_lead: np.ndarray, ced_mix: np.ndarray | None, idx: Mapping[str, int],
                       sustain: np.ndarray | None = None, voiced_s: np.ndarray | None = None) -> np.ndarray:
    """Per-frame style shares [n, 3] (singing, speech, rap), rows summing to 1 (0 rows where no voice cue).

    rap = max(Rapping on the lead stem, Rapping on the mix); speech over a hip-hop context (Rapping / Hip hop music on the
    mix, PLAN §5 'never use SwiftF0 for presence on rap') is moved to rap, because CED tags rap on an isolated vocal stem
    mostly as Speech (bench-music §5: newton-vs-nye vocals Speech .55, Rapping .06)."""
    def mx(P: np.ndarray, labels: Sequence[str]) -> np.ndarray:
        return P[:, [idx[x] for x in labels]].max(axis=1).astype(np.float64)

    sing = mx(ced_lead, SINGING)
    speech = mx(ced_lead, SPEECH)
    rap = mx(ced_lead, RAP)
    if ced_mix is not None:
        rap = np.maximum(rap, mx(ced_mix, RAP))
        ctx = mx(ced_mix, HIPHOP_CONTEXT)
        # song-level context too: one rap battle has a hip-hop context everywhere, even in sparse windows
        song_ctx = float(np.percentile(ctx, 75)) if ctx.size else 0.0
        hh = np.clip((np.maximum(ctx, song_ctx) - 0.1) / 0.15, 0.0, 1.0)  # Hip hop >= .25 = full rap context
    else:
        hh = np.zeros_like(speech)
    rap_eff = np.maximum(rap, speech * hh)
    speech_eff = speech * (1.0 - hh)
    if sustain is not None and voiced_s is not None:
        # pitch evidence (sustained notes = singing) where the window has >= 0.4 s of voiced frames
        s_p = np.clip((np.asarray(sustain) - 0.25) / 0.35, 0.0, 1.0)
        has = np.asarray(voiced_s) >= 0.4
        sing = np.where(has, sing * (0.5 + s_p), sing)
        speech_eff = np.where(has, speech_eff * (1.5 - s_p), speech_eff)
        rap_eff = np.where(has, rap_eff * (1.5 - s_p), rap_eff)
    m = np.stack([sing, speech_eff, rap_eff], axis=1)
    tot = m.sum(axis=1, keepdims=True)
    # below STYLE_FLOOR total vocal-label evidence the style is unknown (normalising noise would invent a style)
    return np.where(tot >= STYLE_FLOOR, m / np.maximum(tot, 1e-9), 0.0)


def smooth_labels(lab: np.ndarray, k: int = 5) -> np.ndarray:
    """Majority vote over a centred window of k frames (labels -1 = none stay none)."""
    out = lab.copy()
    h = k // 2
    for i in range(lab.size):
        if lab[i] < 0:
            continue
        w = lab[max(0, i - h): i + h + 1]
        w = w[w >= 0]
        out[i] = np.bincount(w).argmax() if w.size else lab[i]
    return out
