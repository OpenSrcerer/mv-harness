"""drums core: onset detection on one-shot signals, the DrumSep path, the classifier path, envelopes.

numpy + scipy.signal only; every function is pure and unit-tested on synthetic signals.

Onset detector (``detect``): 1 ms energy blocks; a candidate is a local maximum of the rise ratio
``post / pre`` (post = mean energy of the 3 blocks from k, pre = mean energy of blocks k-8 .. k-3), at least
``rise_db``; its level is the loudest 10 ms RMS in the 60 ms after the onset; candidates below an absolute floor
or more than ``rel_gate_db`` below the stem's own p95 hit level are dropped; within ``min_gap_ms`` the louder one
wins. The **event time is the one-shot's first sample**: the first sample in the 2 ms before the candidate block
whose |x| exceeds ``max(1.5 * max|x| of the tail before, 0.15 * attack_peak)`` (separators smear a ~30 ms
pre-echo ramp up to ~-20 dB under the attack in front of it).

DrumSep path: each sub-stem is detected on its own (kick -> kick, snare -> snare, toms -> tom, hihat -> hat,
ride/crash -> cymbal); bleed (a much quieter copy of a hit that is much louder in another sub-stem at the same
instant) is dropped; a cymbal hit 10 dB quieter in the other cymbal sub-stem within 30 ms is merged.

Classifier path (no sub-stems): onsets of the drum stem in four bands (plus a low-threshold 8-16 kHz detector for
quiet hats) are clustered into events and labelled from band-energy ratios and decay (``classify``); several
drums can share one instant (kick + hat). A tonal 160-400 Hz onset with 1.5-6 kHz attack noise is a tom; a lone
kick or snare stroke whose high bands sit well above the song's own bare-stroke floor carries a hat (excess above
7 kHz) or a ride / crash (excess in 1.5-6 kHz). Measured on the synthetic drum stem: kick, snare, tom at the
PLAN gates; hat and cymbal stay below them (hats under a snare tail and rides under strokes are not separable
from one mixed stem), so the stage marks them ``low confidence`` (see ``CLASSIFIER_RELIABLE``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = [
    "CLASSIFIER_RELIABLE",
    "DRUMS",
    "SUBSTEM_DRUM",
    "DetectParams",
    "top_ref",
    "Hit",
    "detect",
    "drumsep_hits",
    "classify",
    "velocities",
    "envelopes",
    "match_f1",
]

#: classes the classifier path delivers at the PLAN §7 gates on the synthetic drum stem; hat / cymbal / perc do not
CLASSIFIER_RELIABLE = ("kick", "snare", "tom")
DRUMS = ("kick", "snare", "hat", "tom", "cymbal", "perc")
SUBSTEM_DRUM = {"kick": "kick", "snare": "snare", "toms": "tom", "hihat": "hat", "ride": "cymbal", "crash": "cymbal"}
#: envelope release (s) per drum (exp decay to 1/e)
DECAY_S = {"kick": 0.10, "snare": 0.12, "hat": 0.06, "tom": 0.15, "cymbal": 0.35, "perc": 0.08}
FLOOR_DB = -120.0


@dataclass(frozen=True)
class DetectParams:
    rise_db: float = 2.0
    spread_k: float = 2.0
    abs_floor_db: float = -70.0
    rel_gate_db: float = 30.0
    min_gap_ms: float = 30.0
    pre_blocks: tuple[int, int] = (25, 3)  # pre window = blocks [k-25, k-3) (1 ms blocks)
    post_blocks: int = 10                  # >= half a period of a 50 Hz kick, so sin^2 ripple is no onset
    refine_back_ms: int = 4                # the sample onset is searched from 4 ms before the candidate block
    cluster_db: float = 10.0
    onset_frac: float = 0.15               # ... as the first sample above 15 % of the attack peak (above pre-echo)
    mask_ms: float = 150.0
    mask_db: float = 6.0
    mask_rise_db: float = 6.0
    level_ms: float = 10.0
    level_span_ms: float = 60.0


@dataclass
class Hit:
    t: float                 # seconds (the one-shot's first sample)
    sample: int
    drum: str
    level_db: float          # loudest 10 ms RMS after the onset (dBFS)
    peak: float              # max |x| in the 30 ms after the onset (linear)
    rise_db: float
    conf: float = 1.0
    vel: float = 0.0
    source: str = "drumsep"
    sub_stem: str | None = None
    evidence: list[str] = field(default_factory=list)


def _mono(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    return a.mean(axis=0) if a.ndim == 2 else a


def _blocks(p: np.ndarray, size: int) -> np.ndarray:
    nb = p.shape[0] // size
    e = p[: nb * size].reshape(nb, size).mean(axis=1)
    if p.shape[0] > nb * size:
        e = np.append(e, p[nb * size:].mean())
    return e


def _db(e: np.ndarray | float) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(e, 1e-14))


def top_ref(levels) -> float:
    """A stem's hit level: the 3rd-loudest candidate (robust to one or two outliers). A percentile is not: a toms
    stem can hold 8 real hits among 150 bleed candidates, and its p95 then lands on the bleed."""
    v = np.sort(np.asarray(levels, dtype=np.float64))[::-1]
    return float(v[min(2, v.size - 1)])


def _odf(m: np.ndarray, sr: int, prm: DetectParams) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    """(rise ratio dB, level dB, block size) per 1 ms block of a mono signal."""
    p = m * m
    bs = max(1, int(round(sr / 1000.0)))
    e = _blocks(p, bs)
    nb = e.shape[0]
    a0, a1 = prm.pre_blocks
    cs = np.concatenate(([0.0], np.cumsum(e)))
    k = np.arange(nb)
    pre_lo = np.clip(k - a0, 0, nb)
    pre_hi = np.clip(k - a1, 0, nb)
    pre = (cs[pre_hi] - cs[pre_lo]) / np.maximum(pre_hi - pre_lo, 1)
    post_hi = np.clip(k + prm.post_blocks, 0, nb)
    post = (cs[post_hi] - cs[k]) / np.maximum(post_hi - k, 1)
    floor_e = 10.0 ** ((prm.abs_floor_db - 30.0) / 10.0)   # a noise floor so silence -> silence is not a rise
    ratio = _db(post + floor_e) - _db(pre + floor_e)
    # level: loudest 10 ms RMS within level_span after the block
    lw = max(1, int(round(prm.level_ms)))
    csp = np.concatenate(([0.0], np.cumsum(e)))
    win = (csp[np.clip(k + lw, 0, nb)] - csp[k]) / lw
    span = max(1, int(round(prm.level_span_ms)))
    from scipy.ndimage import maximum_filter1d

    # max of win over [k, k + span): a forward-looking maximum filter
    lvl_e = maximum_filter1d(win, size=span, origin=-(span // 2), mode="nearest")
    lvl_db = _db(lvl_e)
    return ratio, lvl_db, bs, _db(post)


def level_track(x: np.ndarray, sr: int, prm: DetectParams = DetectParams()) -> np.ndarray:
    """Loudest 10 ms RMS (dB) in the 60 ms after each 1 ms block."""
    return _odf(_mono(x), sr, prm)[1]


def detect(x: np.ndarray, sr: int, prm: DetectParams = DetectParams(), drum: str = "perc",
           sub_stem: str | None = None, source: str = "drumsep") -> list[Hit]:
    """Onsets of one-shots in a (mostly) single-instrument signal. Deterministic."""
    from scipy.ndimage import maximum_filter1d

    m = _mono(x)
    n = m.shape[0]
    if n == 0 or not np.any(m):
        return []
    ratio, lvl_db, bs, post_db = _odf(m, sr, prm)
    # candidates: local maxima of the rise ratio above a per-stem threshold. A clean one-shot stem (a closed hat
    # 125 ms after an open one rises only ~2.6 dB) needs a low threshold; a separated real stem is full of slow
    # swells and artefacts. The ODF's own spread over the blocks that carry signal (p75 - p50, ~0.3-1 dB on
    # clean stems, 2-4 dB on separated ones) sets it: thr = rise_db + spread_k * max(0, spread - 1 dB).
    sig = ratio[lvl_db > prm.abs_floor_db + 10.0]
    spread = float(np.percentile(sig, 75) - np.percentile(sig, 50)) if sig.size > 100 else 0.0
    thr = prm.rise_db + prm.spread_k * max(0.0, spread - 1.0)
    rmax = maximum_filter1d(ratio, size=7, mode="nearest")
    full_post = np.arange(ratio.shape[0]) + prm.post_blocks <= ratio.shape[0]   # no onsets from a clipped window
    cand = np.flatnonzero((ratio >= thr) & (ratio >= rmax - 1e-9) & (lvl_db >= prm.abs_floor_db) & full_post)
    if cand.size == 0:
        return []
    # one candidate per local plateau: keep the first index of equal-valued neighbours
    keep = [int(cand[0])]
    for c in cand[1:]:
        if c - keep[-1] > 3:
            keep.append(int(c))
        elif ratio[c] > ratio[keep[-1]] + 1e-9:
            keep[-1] = int(c)
    cand = np.asarray(keep)
    ref = top_ref(lvl_db[cand]) if cand.size else 0.0
    cand = cand[lvl_db[cand] >= ref - prm.rel_gate_db]
    # min gap. A separator smears a pre-echo ramp (~30 ms, 20-40 dB under the attack) in front of each hit: its
    # local maxima share the 60 ms level of the real hit but not its immediate (10 ms) energy. So a candidate counts
    # only when its immediate energy is within 10 dB of the strongest candidate within the gap, and among those the
    # earliest wins (it is the attack, later maxima are inside it).
    gap = max(1, int(round(prm.min_gap_ms)))
    cl = cand.tolist()
    strong = []
    for i, c in enumerate(cl):
        lo = np.searchsorted(cand, c - gap)
        hi = np.searchsorted(cand, c + gap, side="right")
        if post_db[c] >= float(post_db[cand[lo:hi]].max()) - prm.cluster_db:
            strong.append(c)
    taken: list[int] = []
    for c in strong:
        if not taken or c - taken[-1] >= gap:
            taken.append(c)
        elif post_db[c] > post_db[taken[-1]] + prm.cluster_db:
            taken[-1] = c
    taken.sort()
    # masking: a weak, small rise shortly after a much louder hit is the ripple of its tail (beating partials,
    # a pitch glide), not a new stroke
    mask_n = int(round(prm.mask_ms))
    kept: list[int] = []
    for c in taken:
        masked = any(0 < c - q <= mask_n and lvl_db[q] >= lvl_db[c] + prm.mask_db for q in kept[-8:])
        if masked and ratio[c] < prm.mask_rise_db:
            continue
        kept.append(c)
    taken = kept
    hits: list[Hit] = []
    absm = np.abs(m)
    for c in taken:
        s0 = max(0, (c - prm.refine_back_ms) * bs)
        s_att = min(n, (c + prm.post_blocks + 5) * bs)   # the attack peak may be up to ~15 ms after an early maximum
        if s_att <= s0:
            continue
        att_peak = float(absm[s0:s_att].max())
        # the first sample that clearly exceeds what the previous tail reached (its max |x| over 5 ms)
        p0, p1 = max(0, (c - 8) * bs), max(0, (c - prm.refine_back_ms) * bs)
        pre_max = float(absm[p0:p1].max()) if p1 > p0 else 0.0
        thr = max(1.5 * pre_max, prm.onset_frac * att_peak)
        idx = np.flatnonzero(absm[s0:s_att] > thr)
        onset = s0 + int(idx[0]) if idx.size else c * bs
        pk_end = min(n, onset + int(0.03 * sr))
        peak = float(absm[onset:pk_end].max()) if pk_end > onset else 0.0
        hits.append(Hit(t=onset / sr, sample=onset, drum=drum, level_db=float(lvl_db[c]), peak=peak,
                        rise_db=float(ratio[c]), source=source, sub_stem=sub_stem))
    return hits


def detect_air(x: np.ndarray, sr: int, prm: DetectParams = DetectParams(), *, lo_hz: float = 8000.0,
               hi_hz: float = 16000.0, rise_db: float = 1.5, drum: str = "hat", sub_stem: str | None = None,
               source: str = "drumsep") -> list[Hit]:
    """Onsets in the air band (``lo_hz``-``hi_hz``) of a hi-hat stem. A hat in a separated stem sits on a broadband
    bed (open-hat wash, noise layers, separator residue) that hides its rise in the full-band energy; in the air band
    the same hit rises 8-10 dB. The detector runs at a low rise threshold (no spread adaptation); level and peak are
    read from the full-band signal so they compare with the other candidates."""
    import dataclasses

    from scipy import signal

    m = _mono(x)
    if m.shape[0] < int(0.1 * sr) or not np.any(m):
        return []
    nyq = sr / 2.0
    hi = min(hi_hz, 0.95 * nyq)
    if hi <= lo_hz * 1.2:
        return []
    y = signal.sosfiltfilt(signal.butter(4, [lo_hz / nyq, hi / nyq], btype="bandpass", output="sos"), m)
    ap = dataclasses.replace(prm, rise_db=rise_db, spread_k=0.0)
    hs = detect(y, sr, ap, drum=drum, sub_stem=sub_stem, source=source)
    if not hs:
        return []
    lvl = level_track(m, sr, prm)
    bs = max(1, int(round(sr / 1000.0)))
    absm = np.abs(m)
    for h in hs:
        k = min(h.sample // bs, lvl.shape[0] - 1)
        h.level_db = float(lvl[k])
        e = min(m.shape[0], h.sample + int(0.03 * sr))
        h.peak = float(absm[h.sample:e].max()) if e > h.sample else 0.0
        h.evidence.append("air_band")
    return hs


# ============================================================================================ DrumSep path
def drumsep_hits(subs: Mapping[str, np.ndarray], sr: int, prm: DetectParams = DetectParams(), *,
                 bleed_db: float = 18.0, bleed_rel_db: float = 12.0, bleed_window_ms: float = 8.0,
                 bleed_rise_db: float = 10.0, dull_db: float = 12.0, hat_dup_ms: float = 15.0,
                 hat_dup_decay_db: float = 6.0, strike_rise_db: float = 6.0,
                 cymbal_rise_db: float = 4.0, merge_cymbal_ms: float = 30.0,
                 merge_cymbal_db: float = 10.0, air_rise_db: float = 1.5, air_dup_ms: float = 15.0,
                 preecho_db: float = -15.0, click_rise_db: float = 12.0, cym_bright_rel_db: float = 7.5,
                 cym_decay_db: float = 6.0, snare_bleed_bright_rel_db: float = 18.5,
                 merge_cymbal_any_ms: float = 15.0, cym_gate_db: float = 12.0, tom_gate_db: float = 20.0, kit_window_s: float = 0.75,
                 cym_loose_db: float = 28.0, cym_abs_gate_db: float = 8.0, hat_dup_ring_db: float = 8.0, hat_dup_ring_conf_db: float = 12.5, ring_min_db: float = 14.0, ring_decay_db: float = 13.0,
                 ride_twin_db: float = 6.0, hat_leak_db: float = 10.0, cymbal_confirm: Sequence[float] = (),
                 confirm_ms: float = 15.0, input_rise_db: float = 3.0, input_check_below_db: float = 8.0,
                 drums_mix: np.ndarray | None = None, coinc_decay_db: float = 9.0) -> tuple[list[Hit], dict[str, Any]]:
    """Hits from DrumSep sub-stems ({'kick': x, 'snare': x, ...}). Returns (hits, stats).

    Hi-hat stem candidates come from the full-band detector and from a low-threshold 8-16 kHz detector
    (``detect_air``: a hat on a bed rises ~1 dB full-band, 8-10 dB in the air band).
    Bleed: a candidate is dropped when a stroke in another sub-stem within 60 ms is ``bleed_db`` louder (a pre-echo
    ramp or a ripple after it) and the candidate rises less than ``click_rise_db`` (or is weak for its own stem:
    <= top_ref - ``bleed_rel_db``, and < 2 x ``click_rise_db``) or, in a ride/crash stem, barely rises
    (< ``bleed_rise_db``). Coincidence of strokes means within +-``bleed_window_ms`` (their onsets, not their rings).
    Pre-echo: a candidate whose next 30 ms are ``preecho_db`` (15 dB) louder than its first 30 ms is the ramp in
    front of a stronger hit. Toms stem: hits ``tom_gate_db`` under the stem's loudest are leakage.
    Hi-hat stem shape rules (brightness = air over 1.5-6 kHz energy, decay = first to second 30 ms): a kick / snare
    stroke at the same instant with a small rise is a click (dropped); brightness more than ``snare_bleed_bright_rel_db`` under the typical one with a stroke is snare
    noise (dropped); brightness more than ``cym_bright_rel_db`` under the stem's typical brightness with a slow decay (< ``cym_decay_db``) and a large rise is a
    crash or ride DrumSep routed here (relabelled ``cymbal``), with a small rise an artefact (dropped); a hat with
    a ride / crash stroke of about the same level (``ride_twin_db``) at the same instant is that stroke's copy.
    Ride / crash stems: hits more than ``cym_gate_db`` under the stem's 2nd loudest, or ``hat_leak_db`` under a
    hi-hat stroke at the same instant, are leakage; coincident cymbal hits of different sub-stems are merged.
    Hi-hat bleed (DrumSep leaks snare noise and kick clicks into the hi-hat stem): a hi-hat candidate that
    coincides with a louder hit in another sub-stem and whose brightness (energy above 7 kHz over 1.5-6 kHz, first
    30 ms) is ``dull_db`` below the stem's typical brightness (median of its stronger half) is dropped.
    Hat duplicates: DrumSep also routes open hats into the ride/crash stems; a cymbal-stem hit within
    ``hat_dup_ms`` of a kept hi-hat hit that decays like a hat (>= ``hat_dup_decay_db`` from the first to the
    second 30 ms) is dropped (a real crash on a hat stroke keeps ringing).
    Kick and snare strokes are large transients (>= 7 dB rise on every true hit, clean or separated); a kick/snare
    candidate rising less than ``strike_rise_db`` is a separator artefact (a second bump of the same hit 50-200 ms
    later, bass leaking into the kick stem) and is dropped.
    Ride and crash stems ring (washes, sustained bells): their rise floor is ``cymbal_rise_db``. A ride / crash
    candidate that rises less than ``input_check_below_db`` (the floor before round 3) in its own stem must also be an
    event in the DrumSep INPUT (``drums_mix``, else the sum of the sub-stems): a >= ``input_rise_db`` 6-16 kHz rise there.
    A stroke DrumSep puts in a sub-stem is a stroke in its input; a low-rise "onset" with nothing in the input is energy
    moving between sub-stems. A ride / crash-stem hit at the instant of a snare / tom stroke (+-6 ms) must also decay
    like a cymbal (the 4-16 kHz drop from its first 30 ms to the 30 ms starting 150 ms later is at most ``coinc_decay_db``)
    unless the classifier on the full drum stem confirms it: a snare crack leaking into the stem dies out faster."""
    import dataclasses

    per: dict[str, list[Hit]] = {}
    refs: dict[str, float] = {}
    weak_rise: dict[str, int] = {}
    for sub in sorted(subs):
        if sub not in SUBSTEM_DRUM:
            continue
        sp = dataclasses.replace(prm, rise_db=max(prm.rise_db, cymbal_rise_db)) if SUBSTEM_DRUM[sub] == "cymbal" else prm
        h = detect(subs[sub], sr, sp, drum=SUBSTEM_DRUM[sub], sub_stem=sub, source="drumsep")
        if sub == "hihat":
            have = np.array(sorted(x.t for x in h))
            for a in detect_air(subs[sub], sr, prm, rise_db=air_rise_db, drum="hat", sub_stem=sub):
                if not (have.size and np.abs(have - a.t).min() <= air_dup_ms / 1000.0):
                    h.append(a)
            h.sort(key=lambda z: z.sample)
        if sub in ("kick", "snare"):
            n0 = len(h)
            h = [x for x in h if x.rise_db >= strike_rise_db]
            weak_rise[sub] = n0 - len(h)
        per[sub] = h
        refs[sub] = top_ref([x.level_db for x in h]) if h else FLOOR_DB
    stats: dict[str, Any] = {"candidates": {s: len(v) for s, v in per.items()}, "bleed_dropped": {}, "merged": 0,
                             "weak_rise_dropped": weak_rise}
    out: list[Hit] = []
    shape: dict[str, dict[int, tuple[float, float]]] = {}
    for sub in ("hihat", "ride", "crash"):
        if sub in per:
            shape[sub] = {h.sample: _shape(subs[sub], sr, h.sample) for h in per[sub]}
    typ_bright = None
    if per.get("hihat"):
        strong = sorted(per["hihat"], key=lambda h: -h.level_db)[: max(1, len(per["hihat"]) // 2)]
        typ_bright = float(np.median([shape["hihat"][h.sample][0] for h in strong]))
    stats["hihat_typical_brightness_db"] = round(typ_bright, 2) if typ_bright is not None else None
    stats["dull_bleed_dropped"] = 0
    stats["hat_duplicates_dropped"] = 0
    stats["preecho_dropped"] = 0
    stats["click_bleed_dropped"] = 0
    stats["relabelled_cymbal"] = 0
    stats["noise_bleed_dropped"] = 0
    # Leak gates are LOCAL: a ride / crash / tom hit is compared with the kit's own level around it (the median level of
    # the kick and snare strokes within +-kit_window_s), not with the song's loudest strokes, so a passage played softer
    # keeps its cymbals. ``rel`` is the hit's level above that local kit level.
    kit_pts = sorted((x.sample, x.level_db) for sub_ in ("kick", "snare") for x in per.get(sub_, []))
    if not kit_pts:
        kit_pts = sorted((x.sample, x.level_db) for xs in per.values() for x in xs)
    kit_s = np.array([a for a, _ in kit_pts], dtype=np.int64)
    kit_l = np.array([b for _, b in kit_pts], dtype=np.float64)
    kit_w = int(kit_window_s * sr)

    def kit_db(sample: int) -> float:
        if kit_s.size == 0:
            return 0.0
        cw = int(0.008 * sr)
        a, b = np.searchsorted(kit_s, sample - cw), np.searchsorted(kit_s, sample + cw, side="right")
        if b > a:   # a kick / snare stroke at this very instant
            return float(np.max(kit_l[a:b]))
        a, b = np.searchsorted(kit_s, sample - kit_w), np.searchsorted(kit_s, sample + kit_w, side="right")
        return float(np.max(kit_l[a:b])) if b > a else float(np.median(kit_l))

    rel_lvl = {h.sample: h.level_db - kit_db(h.sample) for sub_, xs in per.items()
               if SUBSTEM_DRUM[sub_] in ("cymbal", "tom") for h in xs}
    cym_all = [rel_lvl[x.sample] for sub_, xs in per.items() if SUBSTEM_DRUM[sub_] == "cymbal" for x in xs]
    cym_top = float(np.sort(cym_all)[-min(2, len(cym_all))]) if cym_all else FLOOR_DB   # 2nd loudest of ride + crash
    cym_ref = {sub_: cym_top for sub_ in ("ride", "crash")}
    cym_abs = {sub_: float(np.sort([x.level_db for x in xs])[-min(2, len(xs))]) for sub_, xs in per.items()
               if xs and SUBSTEM_DRUM[sub_] == "cymbal"}   # song-wide 2nd loudest stroke of the stem (the old absolute reference)
    # a cymbal rings: its 4-16 kHz energy is still there 150 ms later and dominates the low band; kick / snare leakage
    # into a ride / crash stem is a short transient (no ring), whatever its level
    ring = {h.sample: _ring(subs[sub_], sr, h.sample) for sub_, xs in per.items() if SUBSTEM_DRUM[sub_] == "cymbal" for h in xs}
    cym_conf_t = np.array(sorted(float(t) for t in cymbal_confirm), dtype=np.float64)

    def confirmed(h: Hit) -> bool:
        """A cymbal the classifier on the full drum stem also finds at this instant (+-``confirm_ms``)."""
        if cym_conf_t.size == 0:
            return False
        j = np.searchsorted(cym_conf_t, h.t)
        return any(abs(cym_conf_t[k] - h.t) <= confirm_ms / 1000.0 for k in (j - 1, j) if 0 <= k < cym_conf_t.size)

    def rings_ok(h: Hit, decay_max: float) -> bool:
        r = ring.get(h.sample)
        return r is not None and r[0] >= ring_min_db and r[1] <= decay_max

    def dup_ok(h: Hit) -> bool:
        """rings long enough not to be an open hat that DrumSep also routed into a ride / crash stem"""
        r = ring.get(h.sample)
        return r is not None and r[0] >= ring_min_db and r[1] <= (hat_dup_ring_conf_db if confirmed(h) else hat_dup_ring_db)
    tom_ref = (float(np.sort([rel_lvl[x.sample] for x in per["toms"]])[-min(3, len(per["toms"]))])
               if per.get("toms") else FLOOR_DB)
    stroke_s = np.array(sorted(x.sample for sub_ in ("kick", "snare", "toms") for x in per.get(sub_, [])), dtype=np.int64)
    stroke_l = {x.sample: x.level_db for sub_ in ("kick", "snare", "toms") for x in per.get(sub_, [])}
    snare_s = np.array(sorted(x.sample for x in per.get("snare", [])), dtype=np.int64)
    # the coincidence-decay rule targets snare crack leaking into a cymbal stem: only snare / tom strokes trigger it
    # (R5-1: a ride stroke on a kick is a real ride and must not be judged by the synthetic ride's decay)
    leak_s = np.array(sorted(x.sample for sub_ in ("snare", "toms") for x in per.get(sub_, [])), dtype=np.int64)
    co_w = int(0.006 * sr)
    co_x = max(1, int(round(bleed_window_ms * sr / 1000.0)))
    co_a = int(0.060 * sr)

    def stroke_level(sample: int, arr: np.ndarray) -> float:
        """Loudest kick / snare / tom stroke within +-6 ms of ``sample`` (FLOOR_DB when none)."""
        if arr.size == 0:
            return FLOOR_DB
        a, b = np.searchsorted(arr, sample - co_w), np.searchsorted(arr, sample + co_w, side="right")
        return max((stroke_l[int(q)] for q in arr[a:b]), default=FLOOR_DB)

    hf_in: tuple[np.ndarray, int] | None = None

    def input_event(t: float) -> bool:
        nonlocal hf_in
        if hf_in is None:
            mix = drums_mix if drums_mix is not None else _sum_subs(subs)
            hf_in = _hf_envelope_db(mix, sr)
        hf, bs = hf_in
        k = int(round(t * sr)) // bs
        if k >= hf.shape[0] or k < 26:
            return True   # no context to judge
        return float(hf[k:k + 10].mean() - hf[max(0, k - 25):k - 3].mean()) >= input_rise_db

    for sub, hs in per.items():
        dropped = 0
        for h in hs:
            if SUBSTEM_DRUM[sub] == "cymbal" and h.rise_db < input_check_below_db and not input_event(h.t):
                stats["cymbal_noinput_dropped"] = stats.get("cymbal_noinput_dropped", 0) + 1
                continue
            if sub in ("ride", "crash") and stroke_level(h.sample, leak_s) > FLOOR_DB and not confirmed(h):
                r_ = ring.get(h.sample)
                if r_ is not None and r_[1] > coinc_decay_db:
                    stats["cymbal_coinc_decay_dropped"] = stats.get("cymbal_coinc_decay_dropped", 0) + 1
                    continue
            if SUBSTEM_DRUM[sub] == "cymbal":
                hat_now = max((x.level_db for x in per.get("hihat", []) if abs(x.sample - h.sample) <= co_x),
                              default=FLOOR_DB)
                rl = rel_lvl[h.sample] - cym_ref.get(sub, FLOOR_DB)
                rings = rings_ok(h, ring_decay_db)
                abs_leak = h.level_db < cym_abs.get(sub, FLOOR_DB) - cym_abs_gate_db   # a leak is far under the kit AND under the song's strokes
                if ((rl < -cym_loose_db or (rl < -cym_gate_db and not (rings and confirmed(h)) and abs_leak))
                        or (hat_now >= h.level_db + hat_leak_db and not dup_ok(h))):
                    # a ride / crash stem is nearly silent except for its strokes: a hit far under the stem's own
                    # strokes, or a quiet copy of a louder hi-hat stroke, is leakage
                    stats["cymbal_leak_dropped"] = stats.get("cymbal_leak_dropped", 0) + 1
                    continue
            if sub == "toms" and rel_lvl[h.sample] < tom_ref - tom_gate_db:
                # a toms stem holds a few strokes of one level; hits far under them are leakage of other drums
                stats["tom_leak_dropped"] = stats.get("tom_leak_dropped", 0) + 1
                continue
            if sub in shape and shape[sub][h.sample][1] < preecho_db:
                # the energy after the candidate is far above its own first 30 ms: a separator's pre-echo ramp
                # in front of a stronger hit, not an onset
                stats['preecho_dropped'] += 1
                continue
            # the loudest stroke in another sub-stem at this instant (a candidate there within +-8 ms): energy that
            # merely rings on in another stem (a crash wash, a kick tail) is not a simultaneous stroke
            other = max((x.level_db for o, xs in per.items() if o != sub for x in xs
                         if abs(x.sample - h.sample) <= co_x), default=FLOOR_DB)
            # ... or a stroke within 60 ms (the separators smear a pre-echo ramp in front of every hit and ripple after it)
            ahead = max((x.level_db for o, xs in per.items() if o != sub for x in xs
                         if abs(x.sample - h.sample) <= co_a), default=FLOOR_DB)
            louder = ahead >= h.level_db + bleed_db
            if h.sample in rel_lvl:   # ride / crash / tom: weak for the kit around it, not for the song's loudest strokes
                weak = rel_lvl[h.sample] <= (cym_ref.get(sub, FLOOR_DB) if sub != "toms" else tom_ref) - bleed_rel_db
            else:
                weak = h.level_db <= refs[sub] - bleed_rel_db
            if louder and not (SUBSTEM_DRUM[sub] == "cymbal" and rings_ok(h, ring_decay_db)) and (h.rise_db < click_rise_db or (weak and h.rise_db < 2.0 * click_rise_db)
                           or (SUBSTEM_DRUM[sub] == "cymbal" and h.rise_db < bleed_rise_db)):
                dropped += 1
                continue
            # F-gain-2: a crash DrumSep put in the hi-hat stem (a large transient, slow decay, no snare stroke, not far
            # under the kick it lands on) is judged by the cymbal relabel below, not dropped as dull bleed: the typical
            # hat brightness moves by 1-2 dB with the separator's input level, and the synthetic final crash sat 0.6 dB
            # on the wrong side of that drop
            crash_like = (sub == "hihat" and shape["hihat"][h.sample][1] < cym_decay_db and h.rise_db >= 2.0 * click_rise_db
                          and other - h.level_db < bleed_db and stroke_level(h.sample, snare_s) <= FLOOR_DB)
            if (sub == "hihat" and typ_bright is not None and other > h.level_db and not crash_like
                    and shape["hihat"][h.sample][0] < typ_bright - dull_db):
                stats["dull_bleed_dropped"] += 1
                continue
            if sub == "hihat":
                bright, decay = shape["hihat"][h.sample]
                st_lvl = stroke_level(h.sample, stroke_s)
                if st_lvl >= h.level_db + bleed_db and h.rise_db < click_rise_db and "air_band" not in h.evidence:
                    # a kick click / snare crack leaking into the hat stem: loud elsewhere, a small rise here
                    stats["click_bleed_dropped"] += 1
                    continue
                if bright < min(0.0, typ_bright - snare_bleed_bright_rel_db) and st_lvl >= h.level_db - 12.0:
                    # noise below 7 kHz with a kick or snare stroke at the same instant: snare / kick noise
                    stats["noise_bleed_dropped"] += 1
                    continue
                if (bright < min(11.0, typ_bright - cym_bright_rel_db) and decay < cym_decay_db and "air_band" not in h.evidence
                        and stroke_level(h.sample, snare_s) <= FLOOR_DB):
                    # DrumSep routes crashes and rides (broadband, slowly decaying, dull above 7 kHz) into the
                    # hi-hat stem: a hat is bright and decays within 30-60 ms
                    if h.rise_db < click_rise_db:
                        # a cymbal stroke is a large transient; a dull, slow, weak bump is an artefact
                        stats["weak_dull_dropped"] = stats.get("weak_dull_dropped", 0) + 1
                        continue
                    h.drum = "cymbal"
                    h.evidence.append("relabelled_from_hihat_shape")
                    stats["relabelled_cymbal"] += 1
            # confidence: margin above the stem's gate and rise strength
            c_lvl = float(np.clip((h.level_db - (refs[sub] - prm.rel_gate_db)) / 15.0, 0.0, 1.0))
            c_rise = float(np.clip((h.rise_db - prm.rise_db) / 12.0, 0.0, 1.0))
            h.conf = 0.4 + 0.35 * c_lvl + 0.25 * c_rise
            if louder:
                h.conf *= 0.7
                h.evidence.append("possible_bleed")
            out.append(h)
        stats["bleed_dropped"][sub] = dropped
    # open hats routed into the ride/crash stems: drop the cymbal copy of a kept hi-hat hit that decays like a hat
    hat_t = np.array(sorted(h.t for h in out if h.sub_stem == "hihat"))
    if hat_t.size:
        keep_out = []
        for h in out:
            if h.drum == "cymbal" and h.sub_stem in shape:
                j = np.searchsorted(hat_t, h.t)
                near = any(abs(hat_t[q] - h.t) <= hat_dup_ms / 1000.0 for q in (j - 1, j) if 0 <= q < hat_t.size)
                if near and shape[h.sub_stem][h.sample][1] >= hat_dup_decay_db and not dup_ok(h):
                    stats['hat_duplicates_dropped'] += 1
                    continue
            keep_out.append(h)
        out = keep_out
    # DrumSep copies a ride stroke into the hi-hat stem as well: a hi-hat hit with a ride / crash hit of about the same
    # level at the same instant is that stroke (a hat under a ride stroke is not told apart; the cymbal wins)
    cym_t = [(x.sample, x.level_db, rings_ok(x, ring_decay_db)) for x in out if x.drum == "cymbal" and x.sub_stem in ("ride", "crash")]
    if cym_t:
        for h in out:
            if h.drum == "hat" and "air_band" not in h.evidence and any(
                    abs(sm - h.sample) <= co_x and (rg or abs(lv - h.level_db) <= ride_twin_db) for sm, lv, rg in cym_t):
                h.drum = "cymbal"
                h.evidence.append("relabelled_ride_twin")
                stats["ride_twin_relabelled"] = stats.get("ride_twin_relabelled", 0) + 1
    # merge cymbal duplicates (a crash bleeding into ride or the reverse)
    out.sort(key=lambda h: (h.t, h.drum, h.sub_stem or ""))
    merged: list[Hit] = []
    for h in out:
        if h.drum == "cymbal":
            prev = next((m for m in reversed(merged[-8:]) if m.drum == "cymbal"), None)
            if (prev is not None and prev.sub_stem != h.sub_stem
                    and (h.t - prev.t <= merge_cymbal_any_ms / 1000.0
                         or (h.t - prev.t <= merge_cymbal_ms / 1000.0 and abs(h.level_db - prev.level_db) >= merge_cymbal_db))):
                stats['merged'] += 1
                if h.level_db > prev.level_db:
                    merged[merged.index(prev)] = h
                continue
        merged.append(h)
    return merged, stats


def _shape(x: np.ndarray, sr: int, s: int) -> tuple[float, float]:
    """(brightness, decay) of a hit at sample ``s``: energy above 7 kHz over 1.5-6 kHz in the first 30 ms (dB), and
    the broadband drop from the first to the second 30 ms (dB). Local filtering (200 ms around the hit)."""
    from scipy import signal

    m = _mono(x)
    w = int(0.03 * sr)
    a, b = max(0, s - int(0.1 * sr)), min(m.shape[0], s + int(0.1 * sr))
    seg = m[a:b]
    if seg.shape[0] < 3 * w:
        return 0.0, 0.0
    nyq = sr / 2.0
    o = s - a
    air = signal.sosfiltfilt(signal.butter(4, [7000.0 / nyq, min(16000.0, 0.95 * nyq) / nyq], btype="bandpass", output="sos"), seg)
    hi = signal.sosfiltfilt(signal.butter(4, [1500.0 / nyq, 6000.0 / nyq], btype="bandpass", output="sos"), seg)

    def e(v: np.ndarray, i0: int, i1: int) -> float:
        return float(_db(np.mean(v[max(0, i0):max(i0 + 1, min(v.shape[0], i1))] ** 2)))

    return e(air, o, o + w) - e(hi, o, o + w), e(seg, o, o + w) - e(seg, o + w, o + 2 * w)


# ============================================================================================ classifier path
_BANDS = {
    "sub": (30.0, 90.0),
    "low": (90.0, 160.0),
    "body": (160.0, 400.0),
    "mid": (400.0, 1200.0),
    "hi": (1500.0, 6000.0),
    "air": (7000.0, 16000.0),
}


def _band(x: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    from scipy import signal

    nyq = sr / 2.0
    hi = min(hi, 0.95 * nyq)
    sos = signal.butter(4, [lo / nyq, hi / nyq], btype="bandpass", output="sos")
    return signal.sosfiltfilt(sos, x)


def classify(x: np.ndarray, sr: int, prm: DetectParams = DetectParams(), *,
             cluster_ms: float = 12.0, excess_air_db: float = 2.0, excess_hi_db: float = 2.5,
             excess_ring_db: float = 2.5) -> tuple[list[Hit], dict[str, Any]]:
    """Classifier path on a full drum stem. Returns (hits, stats)."""
    m = _mono(x)
    bands = {k: _band(m, sr, lo, hi) for k, (lo, hi) in _BANDS.items()}
    lowsig = bands["sub"] + bands["low"]
    hfsig = bands["hi"] + bands["air"]
    absm_full = np.abs(m)
    det = {
        "low": detect(lowsig, sr, prm, drum="kick", source="classifier"),
        "body": detect(bands["body"], sr, prm, drum="tom", source="classifier"),
        "hi": detect(bands["hi"], sr, prm, drum="snare", source="classifier"),
        "air": detect(bands["air"], sr, prm, drum="hat", source="classifier"),
    }
    # quiet hats on a bed (open-hat wash, a ringing cymbal) rise little in the band energy but clearly in 8-16 kHz
    have = np.array(sorted(h.sample for h in det["air"]), dtype=np.int64)
    for a in detect_air(m, sr, prm, source="classifier"):
        if not (have.size and np.abs(have - a.sample).min() <= int(0.015 * sr)):
            det["air"].append(a)
    # zero-phase band filters smear onsets (the 30-160 Hz band by ~10 ms): event times come from broadband
    # onsets of the stem when one is near, else from the highest band that saw the event (least smearing)
    broad = np.array([h.sample for h in detect(m, sr, prm, source="classifier")], dtype=np.int64)
    cands = sorted(((h.sample, b, h) for b, hs in det.items() for h in hs), key=lambda z: (z[0], z[1]))
    # cluster band onsets into events
    cw = int(cluster_ms * sr / 1000.0)
    events: list[list[tuple[int, str, Hit]]] = []
    for c in cands:
        if events and c[0] - events[-1][0][0] <= cw:
            events[-1].append(c)
        else:
            events.append([c])
    n = m.shape[0]
    w40 = int(0.04 * sr)
    pre_n = int(0.01 * sr)
    hits: list[Hit] = []
    rows: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"band_onsets": {b: len(v) for b, v in det.items()}, "events": len(events)}

    def energy(sig: np.ndarray, a: int, b: int) -> float:
        a, b = max(0, a), min(n, b)
        return float(np.mean(sig[a:b] ** 2)) if b > a else 0.0

    w_late = (int(0.04 * sr), int(0.12 * sr))
    w_tail = (int(0.15 * sr), int(0.30 * sr))
    w30 = int(0.03 * sr)
    starts = [min(c[0] for c in ev) for ev in events]

    def db(v: float) -> float:
        return 10 * math.log10(v + 1e-14)

    snap_lo, snap_hi = int(0.006 * sr), int(0.02 * sr)
    for ev_i, ev in enumerate(events):
        s0 = min(c[0] for c in ev)
        j = np.searchsorted(broad, s0 - snap_lo)
        if j < broad.size and broad[j] <= s0 + snap_hi:
            s = int(broad[j])
        else:
            pref = {"air": 0, "hi": 1, "body": 2, "low": 3}
            s = int(min(ev, key=lambda c: (pref[c[1]], c[0]))[0])
        bands_hit = {c[1] for c in ev}
        E = {k: energy(v, s, s + w40) for k, v in bands.items()}
        P = {k: energy(v, s - pre_n - int(0.002 * sr), s - int(0.002 * sr)) for k, v in bands.items()}
        rise = {k: db(E[k]) - db(P[k]) for k in E}
        e = {k: db(E[k]) for k in E}                                                    # first 40 ms
        # spectral shape after the first 5 ms (a kick's 3 ms click is gone; snare and hat noise remain)
        w5 = int(0.005 * sr)
        q = {k: db(energy(v, s + w5, s + w5 + w30)) for k, v in bands.items()}
        lt = {k: db(energy(v, s + w_late[0], s + w_late[1])) for k, v in bands.items()}  # 40-120 ms
        lowbody_late = db(10 ** (lt["low"] / 10) + 10 ** (lt["body"] / 10))
        labels: list[str] = []
        # kick: a low onset whose tail sits in the sub band (the pitch drop to ~50 Hz)
        kick = ("low" in bands_hit and lt["sub"] >= lowbody_late + 8.0 and max(e["sub"], e["low"]) >= e["body"] - 3.0)
        if kick:
            labels.append("kick")
        # tom: a tonal 160-400 Hz onset (body >= 15 dB over 1.5-6 kHz, sub band >= 10 dB under the body): a snare's
        # noise keeps body and 1.5-6 kHz within ~5 dB
        # (a stroke on the ring of the previous one barely rises, but it brings 1.5-6 kHz attack noise with it)
        tonal = (not kick and e["body"] - e["hi"] >= 15.0 and e["sub"] - e["body"] <= -10.0
                 and ("hi" in bands_hit or rise["body"] >= 3.0))
        # snare: noise louder in 1.5-6 kHz than above 7 kHz, with a tonal body that rises with it
        snare = (not tonal and "hi" in bands_hit and q["hi"] >= q["air"] + 0.5 and e["body"] >= e["hi"] - 15.0
                 and e["body"] - e["hi"] <= 12.0 and (rise["body"] >= 3.0 or kick))
        if snare:
            labels.append("snare")
        if tonal:
            labels.append("tom")
        # hat / cymbal: a high-frequency onset. Hats live above 7 kHz (open or closed); cymbals put their energy
        # into 1.5-7 kHz too and decay slowly (< 4 dB from the first to the second 30 ms)
        if {"air", "hi"} & bands_hit:
            hf = hfsig
            dec = db(energy(hf, s, s + w30)) - db(energy(hf, s + w30, s + 2 * w30))
            qr = {k: q[k] - db(P[k]) for k in ("hi", "air")}   # rise of the post-click spectrum
            if bands_hit == {"air"} and not kick and not snare:
                # an onset only above 7 kHz, nothing in the other bands: a hat (open or closed)
                labels.append("hat")
            elif "air" in bands_hit and qr["air"] >= 1.0 and (q["air"] >= q["hi"] + 8.0 or (q["air"] >= q["hi"] + 3.0 and qr["air"] >= qr["hi"] + 1.0)):
                labels.append("hat")
            elif q["hi"] >= q["air"] - 6.0 and dec < 4.0 and qr["hi"] >= 1.5 and not snare:
                labels.append("cymbal")
            elif snare and ev_i + 1 < len(starts) and starts[ev_i + 1] - s > w_tail[1]:
                # a cymbal under a snare: still ringing after the snare's noise has died away
                tail = db(energy(hf, s + w_tail[0], s + w_tail[1]))
                if tail >= db(energy(hf, s, s + w40)) - 12.0:
                    labels.append("cymbal")
        if not labels:
            continue
        # a kick or snare stroke with no hat / cymbal label: ratios of its high bands to its own body, for the
        # template-excess pass below (the ring window is only used when no other event starts inside it)
        feat = None
        base = "kick" if labels == ["kick"] else ("snare" if labels == ["snare"] else None)
        if base and not ({"hat", "cymbal"} & set(labels)):
            ref_e = db(10 ** (e["sub"] / 10) + 10 ** (e["low"] / 10)) if base == "kick" else e["body"]
            clear = ev_i + 1 >= len(starts) or starts[ev_i + 1] - s > int(0.32 * sr)
            ring = (db(energy(bands["hi"], s + int(0.15 * sr), s + int(0.30 * sr))) - ref_e) if clear else None
            feat = (e["air"] - ref_e, e["hi"] - ref_e, ring)
        rows.append({"s": s, "labels": labels, "e": e, "rise": rise, "base": base, "feat": feat})
    # Template excess (hat / ride / crash under a kick or snare). The kick and snare samples of a song keep their
    # spectral balance, so a stroke's high bands relative to its own body sit near a floor (the low percentile over
    # the song's strokes, which are mostly bare); a stroke well above it carries another source: 1.5-6 kHz excess or
    # a ring after 150 ms means a ride / crash, excess only above 7 kHz a hat.
    stats["template_excess"] = {}
    for base in ("kick", "snare"):
        rs = [r for r in rows if r["base"] == base and r["feat"] is not None]
        if len(rs) < 8:
            continue
        ta = float(np.percentile([r["feat"][0] for r in rs], 20))
        th = float(np.percentile([r["feat"][1] for r in rs], 20))
        rr = [r["feat"][2] for r in rs if r["feat"][2] is not None]
        tr_ = float(np.percentile(rr, 20)) if len(rr) >= 8 else None
        added = {"hat": 0, "cymbal": 0}
        for r in rs:
            ex_a, ex_h = r["feat"][0] - ta, r["feat"][1] - th
            ex_r = (r["feat"][2] - tr_) if (tr_ is not None and r["feat"][2] is not None) else 0.0
            if ex_h >= excess_hi_db or ex_r >= excess_ring_db:
                r["labels"].append("cymbal")
                r["extra"] = "cymbal"
            elif ex_a >= excess_air_db:
                r["labels"].append("hat")
                r["extra"] = "hat"
            else:
                continue
            added[r["extra"]] += 1
        stats["template_excess"][base] = {"template_air_db": round(ta, 2), "template_hi_db": round(th, 2), **added}
    for r in rows:
        s, labels, e, rise = r["s"], r["labels"], r["e"], r["rise"]
        # sample onset: the earliest band onset of the event
        onset = s
        absm = absm_full
        pk = float(absm[onset:min(n, onset + int(0.03 * sr))].max()) if onset < n else 0.0
        for lab in labels:
            band = {"kick": lowsig, "tom": bands["body"] if e["body"] >= e["low"] else bands["low"],
                    "snare": bands["hi"], "hat": bands["air"], "cymbal": hfsig}[lab]
            seg = band[onset:min(n, onset + int(0.06 * sr))]
            lvl_db = 10 * math.log10(float(np.mean(seg ** 2)) + 1e-14) if seg.size else FLOOR_DB
            bpk = float(np.abs(seg).max()) if seg.size else 0.0
            r_ = max(rise.get(k, 0.0) for k in {"kick": ("sub",), "tom": ("low", "body"), "snare": ("hi",),
                                                 "hat": ("air",), "cymbal": ("hi", "air")}[lab])
            extra = r.get("extra") == lab
            hits.append(Hit(t=onset / sr, sample=onset, drum=lab, level_db=lvl_db, peak=bpk or pk, rise_db=r_,
                            conf=float((0.3 if extra else 0.35 + 0.4 * np.clip((r_ - prm.rise_db) / 15.0, 0.0, 1.0))),
                            source="classifier", evidence=["template_excess"] if extra else []))
    hits.sort(key=lambda h: (h.t, DRUMS.index(h.drum)))
    stats["hits"] = {d: sum(1 for h in hits if h.drum == d) for d in DRUMS}
    return hits, stats


# ============================================================================================ post
def velocities(hits: Sequence[Hit], pct: float = 98.0) -> dict[str, float]:
    """vel = peak / p98(peak) of the same drum class, clipped to [0, 1]. Returns the reference per drum."""
    refs: dict[str, float] = {}
    for d in DRUMS:
        pk = [h.peak for h in hits if h.drum == d and h.peak > 0]
        if pk:
            refs[d] = float(np.percentile(pk, pct))
    for h in hits:
        r = refs.get(h.drum, 0.0)
        h.vel = float(np.clip(h.peak / r, 0.0, 1.0)) if r > 0 else 0.0
    return refs


def envelopes(hits: Sequence[Hit], n_frames: int, rate: int = 100) -> dict[str, np.ndarray]:
    """Velocity-scaled 100 Hz envelopes per drum (flash rule: the peak at floor(t*rate) and ceil(t*rate), then an
    exponential release of DECAY_S[drum])."""
    from mvh.contract.conventions import flash_samples

    out = {d: np.zeros(n_frames, dtype=np.float64) for d in DRUMS}
    for h in hits:
        env = out[h.drum]
        i0, i1 = flash_samples(h.t, rate)
        tau = DECAY_S[h.drum]
        span = int(math.ceil(tau * rate * 7))
        idx = np.arange(i1, min(n_frames, i1 + span + 1))
        if idx.size:
            vals = h.vel * np.exp(-np.maximum(idx / rate - h.t, 0.0) / tau)
            vals[idx <= i1] = h.vel
            np.maximum.at(env, idx, vals)
        if 0 <= i0 < n_frames:
            env[i0] = max(env[i0], h.vel)
    return {d: np.clip(v, 0.0, 1.0).astype(np.float32) for d, v in out.items()}


def match_f1(est: Sequence[float], ref: Sequence[float], tol: float) -> tuple[float, float, float, int]:
    """Greedy one-to-one matching (time-sorted) within ``tol``; returns (f1, precision, recall, matches)."""
    e = sorted(est)
    r = sorted(ref)
    used = [False] * len(r)
    j0 = 0
    tp = 0
    for t in e:
        while j0 < len(r) and r[j0] < t - tol:
            j0 += 1
        best = None
        for j in range(j0, len(r)):
            if r[j] > t + tol:
                break
            if not used[j] and (best is None or abs(r[j] - t) < abs(r[best] - t)):
                best = j
        if best is not None:
            used[best] = True
            tp += 1
    p = tp / len(e) if e else (1.0 if not r else 0.0)
    rc = tp / len(r) if r else (1.0 if not e else 0.0)
    f = 2 * p * rc / (p + rc) if p + rc > 0 else 0.0
    return f, p, rc, tp


def _sum_subs(subs: Mapping[str, np.ndarray]) -> np.ndarray:
    """Mono sum of the drum sub-stems (an estimate of the DrumSep input)."""
    ms = [_mono(v) for k, v in subs.items() if k in SUBSTEM_DRUM]
    n = min(m.shape[0] for m in ms)
    return np.sum([m[:n] for m in ms], axis=0)


def _hf_envelope_db(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """6-16 kHz energy in 1 ms bins (dB) and the bin size in samples."""
    from scipy import signal

    nyq = sr / 2.0
    y = signal.sosfiltfilt(signal.butter(4, [6000.0 / nyq, min(16000.0, 0.95 * nyq) / nyq], btype="bandpass", output="sos"),
                           _mono(x))
    bs = max(1, int(round(sr / 1000.0)))
    e = (y[: y.size // bs * bs] ** 2).reshape(-1, bs).mean(axis=1)
    return 10.0 * np.log10(e + 1e-14), bs


def _ring(x: np.ndarray, sr: int, s: int) -> tuple[float, float]:
    """(high-over-low, decay) of a ride / crash candidate at sample ``s``: 4-16 kHz energy over 100-1000 Hz energy in the
    first 30 ms (dB), and the 4-16 kHz drop from the first 30 ms to the 30 ms starting 150 ms later (dB). A cymbal rings
    (small drop, bright); kick / snare bleed is a transient (large drop) or dull."""
    from scipy import signal

    m = _mono(x)
    a, b = max(0, s - int(0.08 * sr)), min(m.shape[0], s + int(0.3 * sr))
    seg = m[a:b]
    w = int(0.03 * sr)
    o = s - a
    if seg.shape[0] < o + int(0.18 * sr) + w:
        return 0.0, 99.0   # too close to the end of the stem to see the ring
    nyq = sr / 2.0
    hi = signal.sosfiltfilt(signal.butter(4, [4000.0 / nyq, min(16000.0, 0.95 * nyq) / nyq], btype="bandpass", output="sos"), seg)
    lo = signal.sosfiltfilt(signal.butter(4, [100.0 / nyq, 1000.0 / nyq], btype="bandpass", output="sos"), seg)

    def e(v: np.ndarray, i0: int) -> float:
        return float(_db(np.mean(v[i0:i0 + w] ** 2)))

    h0 = e(hi, o)
    return h0 - e(lo, o), h0 - e(hi, o + int(0.15 * sr))
