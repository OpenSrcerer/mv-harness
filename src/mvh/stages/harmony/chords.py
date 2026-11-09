"""Chord timeline: lv-chordia decode (or the template + Viterbi fallback), snapped to beats, with chroma-based
verification (confidence, bass pitch class) per segment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from . import theory as T
from .chroma import ChromaFrames, aggregate


@dataclass
class Seg:
    t: float
    d: float
    root: int | None
    quality: str
    bass: int | None = None
    label: str = "N"
    spelling: str | None = None      # root spelling used by lv-chordia ('Bb'), kept for the label
    conf: float = 0.5
    beat_index: int | None = None

    @property
    def end(self) -> float:
        return self.t + self.d


# ------------------------------------------------------------------------------------------ lv-chordia
def run_lv_chordia(wav_path, chord_dict: str = "submission") -> list[dict[str, Any]]:
    """lv-chordia's 5-model ensemble on a float32 WAV we wrote (22.05 kHz mono). Checkpoints are bundled in the wheel."""
    import contextlib
    import io

    from lv_chordia.chord_recognition import chord_recognition

    with contextlib.redirect_stderr(io.StringIO()):
        return chord_recognition(str(wav_path), chord_dict)


def segs_from_lv(res: Sequence[Mapping[str, Any]], duration: float) -> list[Seg]:
    out: list[Seg] = []
    for r in sorted(res, key=lambda r: float(r["start_time"])):
        t0, t1 = float(r["start_time"]), min(float(r["end_time"]), duration)
        if t1 - t0 < 1e-4:
            continue
        label = str(r["chord"])
        root, q, bass = T.parse_harte(label)
        spelling = label.split(":")[0].split("/")[0] if root is not None else None
        out.append(Seg(t0, t1 - t0, root, q, bass, T.harte_label(root, q, spelling), spelling))
    return _cover(out, duration)


def _cover(segs: list[Seg], duration: float) -> list[Seg]:
    """Gapless timeline over [0, duration): gaps and the tail become N."""
    out: list[Seg] = []
    t = 0.0
    for s in segs:
        if s.t > t + 1e-4:
            out.append(Seg(t, s.t - t, None, "N", None, "N"))
        elif s.t < t:  # overlap: trim
            s = Seg(t, s.end - t, s.root, s.quality, s.bass, s.label, s.spelling, s.conf)
            if s.d <= 1e-4:
                continue
        out.append(s)
        t = s.end
    if duration - t > 1e-4:
        if out and out[-1].quality == "N":
            out[-1].d += duration - t
        else:
            out.append(Seg(t, duration - t, None, "N", None, "N"))
    return out


# ------------------------------------------------------------------------------------------ beat snapping
def snap_to_beats(segs: list[Seg], beats: Sequence[Mapping[str, Any]], duration: float, max_frac: float = 0.5) -> list[Seg]:
    """Move every chord boundary to the nearest beat (at most ``max_frac`` of the local beat interval away), drop segments
    that collapse, merge equal neighbours. Boundaries with no beat in range keep their time."""
    if not segs:
        return segs
    bt = np.array(sorted(float(b["t"]) for b in beats), float)
    if bt.size < 2:
        return _merge_equal(segs)
    starts = [s.t for s in segs]
    new_starts = [0.0]
    for t in starts[1:]:
        i = int(np.searchsorted(bt, t))
        cands = [j for j in (i - 1, i) if 0 <= j < bt.size]
        j = min(cands, key=lambda j: abs(bt[j] - t))
        local = bt[min(j + 1, bt.size - 1)] - bt[max(j - 1, 0)]
        local = local / 2 if local > 0 else 0.5
        new_starts.append(float(bt[j]) if abs(bt[j] - t) <= max_frac * local else t)
    out: list[Seg] = []
    for k, s in enumerate(segs):
        t0 = new_starts[k]
        t1 = new_starts[k + 1] if k + 1 < len(segs) else duration
        if t1 - t0 < 1e-4:
            continue  # collapsed onto the next boundary
        out.append(Seg(t0, t1 - t0, s.root, s.quality, s.bass, s.label, s.spelling, s.conf))
    return _merge_equal(out)


def _merge_equal(segs: list[Seg]) -> list[Seg]:
    out: list[Seg] = []
    for s in segs:
        if out and out[-1].root == s.root and out[-1].quality == s.quality and out[-1].bass == s.bass:
            out[-1].d = s.end - out[-1].t
        else:
            out.append(Seg(s.t, s.d, s.root, s.quality, s.bass, s.label, s.spelling, s.conf))
    return out


def assign_beat_index(segs: list[Seg], beats: Sequence[Mapping[str, Any]], tol_frac: float = 0.35) -> None:
    bt = np.array([float(b["t"]) for b in beats], float)
    bi = [int(b["beat_index"]) for b in beats]
    if not bt.size:
        return
    order = np.argsort(bt)
    bt = bt[order]
    bi = [bi[i] for i in order]
    for s in segs:
        i = int(np.searchsorted(bt, s.t))
        cands = [j for j in (i - 1, i) if 0 <= j < bt.size]
        j = min(cands, key=lambda j: abs(bt[j] - s.t))
        local = (bt[min(j + 1, bt.size - 1)] - bt[max(j - 1, 0)]) / 2 or 0.5
        s.beat_index = bi[j] if abs(bt[j] - s.t) <= tol_frac * local else None


# ------------------------------------------------------------------------------------------ template + Viterbi
def beat_windows(beats: Sequence[Mapping[str, Any]], duration: float, hop_s: float = 0.5) -> list[tuple[float, float]]:
    bt = sorted({round(float(b["t"]), 6) for b in beats if 0.0 <= float(b["t"]) < duration})
    if len(bt) < 4:
        bt = list(np.arange(0.0, duration, hop_s))
    edges = [0.0] + [t for t in bt if t > 0.0] + [duration]
    return [(a, b) for a, b in zip(edges[:-1], edges[1:]) if b - a > 1e-3]


def template_decode(cf: ChromaFrames, windows: Sequence[tuple[float, float]], self_prob: float = 0.85,
                    qualities: tuple[str, ...] = ("maj", "min")) -> list[Seg]:
    """Beat-synchronous chroma -> 24 triad templates (+ N) with a sticky Viterbi."""
    bank, ids = T.template_bank(qualities)
    n = len(ids) + 1
    feats = np.zeros((len(windows), 12))
    e_rel = np.zeros(len(windows))
    ref_e = np.percentile(cf.energy[cf.mask()], 95) if cf.mask().any() else 1.0
    for i, (a, b) in enumerate(windows):
        feats[i] = aggregate(cf, a, b, weight_energy=False)
        lo, hi = int(np.searchsorted(cf.times, a)), max(int(np.searchsorted(cf.times, b)), int(np.searchsorted(cf.times, a)) + 1)
        e_rel[i] = float(cf.energy[lo:hi].mean() / (ref_e + 1e-12)) if hi > lo else 0.0
    norms = np.linalg.norm(feats, axis=1, keepdims=True)
    fz = np.where(norms > 1e-12, feats / np.maximum(norms, 1e-12), 0.0)
    cos = fz @ bank.T                                       # [W, 24]
    em = np.zeros((len(windows), n))
    em[:, :-1] = 14.0 * cos
    # N wins where nothing chord-like is present (best triad cosine below ~0.6) or the window is silent
    em[:, -1] = 14.0 * 0.60
    em[(norms[:, 0] < 1e-9) | (e_rel < 0.01), -1] += 20.0
    stay = np.log(self_prob)
    move = np.log((1 - self_prob) / (n - 1))
    delta = em[0].copy()
    back = np.zeros((len(windows), n), int)
    for t in range(1, len(windows)):
        best = int(np.argmax(delta))
        stay_s = delta + stay
        move_s = delta[best] + move
        take_move = move_s > stay_s
        back[t] = np.where(take_move, best, np.arange(n))
        delta = np.where(take_move, move_s, stay_s) + em[t]
    path = np.zeros(len(windows), int)
    path[-1] = int(np.argmax(delta))
    for t in range(len(windows) - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    segs = []
    for (a, b), k in zip(windows, path):
        if k == n - 1:
            segs.append(Seg(a, b - a, None, "N", None, "N"))
        else:
            r, q = ids[k]
            segs.append(Seg(a, b - a, r, q, None, T.harte_label(r, q)))
    return _merge_equal(segs)


def segs_to_labels(segs: Sequence[Seg], windows: Sequence[tuple[float, float]]) -> list[tuple[int | None, str]]:
    """Label (root, quality) active at each window centre."""
    out = []
    for a, b in windows:
        m = (a + b) / 2
        hit = next((s for s in segs if s.t <= m < s.end), None)
        out.append((hit.root, hit.quality) if hit else (None, "N"))
    return out


# ------------------------------------------------------------------------------------------ verification
def _triad_family(q: str) -> str:
    if q in ("min", "min7", "min9"):
        return "min"
    if q in ("dim", "dim7", "hdim7"):
        return "dim"
    if q == "aug":
        return "aug"
    return "maj"


def verify_segments(segs: list[Seg], cf: ChromaFrames, fallback: Sequence[Seg] | None, windows: Sequence[tuple[float, float]] | None) -> None:
    """Fill ``conf`` and ``bass`` of every segment from the chroma evidence (in place).

    conf = 0.6 * chroma margin (chosen chord template vs the best other triad template) + 0.4 * agreement with the
    independent template decode over the segment's beats. N segments score by how un-chord-like the chroma is."""
    bank, ids = T.template_bank(("maj", "min"))
    ref_e = np.percentile(cf.energy[cf.mask()], 95) if cf.mask().any() else 1.0
    fb_labels = segs_to_labels(fallback, windows) if fallback and windows else None
    for s in segs:
        v = aggregate(cf, s.t, s.end, weight_energy=False)
        nv = np.linalg.norm(v)
        a, b = int(np.searchsorted(cf.times, s.t)), int(np.searchsorted(cf.times, s.end))
        e = float(cf.energy[a:max(b, a + 1)].mean() / (ref_e + 1e-12)) if cf.energy.size else 0.0
        cosv = (v / nv) @ bank.T if nv > 1e-12 else np.zeros(len(ids))
        if s.root is None:
            tonal = float(cosv.max()) if nv > 1e-12 else 0.0
            s.conf = float(np.clip(0.9 - 1.6 * max(tonal - 0.55, 0.0) - (0.0 if e < 0.05 else 0.15 * min(e, 1.0)), 0.1, 0.95))
            s.bass = None
            continue
        if nv <= 1e-12:
            s.conf = 0.1
        else:
            fam = _triad_family(s.quality)
            # root evidence: the best triad template on the chosen root against the best on any other root; quality
            # evidence: the chosen family against the other family on the same root (chroma is root-heavy, so the
            # root term carries more weight than the maj/min term)
            best_by_root = np.array([max(cosv[i] for i, (r, _q) in enumerate(ids) if r == root) for root in range(12)])
            root_m = float(best_by_root[s.root] - np.max(np.delete(best_by_root, s.root)))
            root_term = float(np.clip(0.5 + 3.0 * root_m, 0.0, 1.0))
            if fam in ("maj", "min"):
                other_fam = "min" if fam == "maj" else "maj"
                ci = {(r, q): cosv[i] for i, (r, q) in enumerate(ids)}
                quality_term = float(np.clip(0.5 + 4.0 * (ci[(s.root, fam)] - ci[(s.root, other_fam)]), 0.0, 1.0))
            else:
                quality_term = 0.5
            chroma_conf = 0.7 * root_term + 0.3 * quality_term
            agree = None
            if fb_labels is not None and windows:
                idx = [i for i, (wa, wb) in enumerate(windows) if wa >= s.t - 1e-6 and wb <= s.end + 1e-6]
                if idx:
                    agree = float(np.mean([1.0 if fb_labels[i][0] == s.root else 0.0 for i in idx]))
            s.conf = float(np.clip(0.6 * chroma_conf + 0.4 * (agree if agree is not None else chroma_conf), 0.05, 0.99))
        # bass pitch class
        bv = aggregate(cf, s.t, s.end, weight_energy=False, which="bass")
        tones = T.chord_tones(s.root, s.quality)
        bs = bv.sum()
        new_bass = s.root
        if bs > 0:
            share = bv / bs
            pc = int(np.argmax(share))
            if s.bass is not None and share[s.bass] >= 0.5 * share[pc] and share[s.bass] >= 0.15:
                new_bass = s.bass                      # lv-chordia's inversion, confirmed by the bass line
            elif pc in tones and share[pc] >= 0.30:
                new_bass = pc
            elif share[pc] >= 0.55 and pc not in tones:
                new_bass = pc                          # a clear non-chord bass (slash chord)
        s.bass = new_bass


def to_items(segs: Sequence[Seg]) -> list[dict[str, Any]]:
    out = []
    for s in segs:
        out.append({"t": round(s.t, 6), "d": round(s.d, 6), "label": T.harte_label(s.root, s.quality, s.spelling) if s.root is not None else "N",
                    "root_pc": s.root, "quality": s.quality if s.root is not None else "N", "bass_pc": s.bass if s.root is not None else None,
                    "conf": round(float(np.clip(s.conf, 0, 1)), 3), "beat_index": s.beat_index})
    return out


def no_chord_share(segs: Sequence[Seg], duration: float) -> float:
    return float(sum(s.d for s in segs if s.root is None) / max(duration, 1e-9))


def chord_histogram(segs: Sequence[Seg]) -> dict[str, float]:
    h: dict[str, float] = {}
    for s in segs:
        h[s.label] = h.get(s.label, 0.0) + s.d
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))
