"""Kick quality gate and the agent-facing kick source (user decision UD2; CR-M1-4, seam S06).

DrumSep's kick sub-stem is the best kick timeline on most songs (Newton, Versatile, Jeremy, the synthetic song: it agrees
with the mix's low band within 30 ms on 0.90-0.99 of the hits both ways), but on some productions it is mostly bleed:
on MEGAFAUNA 43 % of its inter-kick gaps sit on the 71 ms 32nd-hat grid, the median kick vel is 0.14 (0.72-0.89
elsewhere) and the kick of the intro and build sections sits in the SNARE sub-stem (its 30-120 Hz band dominates its
150-400 Hz band by 12-20 dB), while the kick stem there carries hat / percussion bleed only.

``gate_kicks`` (run on the DrumSep path, before velocities):

* every kick-stem onset is measured in its own stem's 30-120 Hz band: the level of the 30 ms after the onset and the
  rise over the 45-5 ms before it; the song's kick reference is the ``ref_pct`` percentile of those levels;
* an onset whose low band does not rise (< ``rise_min_db``) is not a kick stroke (a hat click, a tail ripple);
* an onset on a hat onset (+-``hat_ms``) while the kick stem is quiet (< reference - ``quiet_db``) is hat bleed;
* an onset far under the song's kicks (< reference - ``floor_db``) is bleed;
* recovery: a SNARE-stem hit whose 30-120 Hz band dominates its 150-400 Hz band by >= ``recover_shape_db``, rises
  >= ``recover_rise_db`` and is within ``recover_level_db`` of the kick reference is a kick DrumSep put in the snare
  stem: it is relabelled ``kick`` (a snare is never bass-dominant by 10 dB). A snare-stem hit that is not bass-dominant
  but carries a kick-level 30-120 Hz burst (>= reference - ``layered_level_db``) that the mix's hits.kick confirms within
  ``merge_ms`` is a kick layered under the snare: a kick row is ADDED at its onset and the snare row stays.
  A TOMS-stem hit needs the same and also a fast decay (>= ``tom_decay_db`` from the first 30 ms to 80-110 ms: a floor
  tom rings) and a mix kick (hits.kick) within ``merge_ms``. A recovered hit with a kept kick within ``merge_ms`` is
  left alone.

``choose_source`` scores the drum-stem kick per song (velocity distribution, grid regularity = the share of inter-kick
gaps under 100 ms, the share of candidate rows the gate kept, low-band rise) and the agreement of the two timelines, and
picks the agent-facing source: ``drums`` (events/drum_hits, drum = kick) when the drums stage produced kicks that pass
the check, else ``mix`` (events/hits.kick, lower quality). numpy + scipy only; pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .core import Hit

__all__ = ["KickGateParams", "SourceParams", "LowFeat", "low_features", "gate_kicks", "agreement", "choose_source"]

KICK_BAND = (30.0, 120.0)
BODY_BAND = (150.0, 400.0)


@dataclass(frozen=True)
class KickGateParams:
    rise_min_db: float = 3.0       # 30-120 Hz rise (30 ms after vs 45-5 ms before) of a kick stroke
    ref_pct: float = 90.0          # the song's kick reference: this percentile of the kick-stem rows' 30-120 Hz level
    quiet_db: float = 10.0         # on a hat onset: dropped when the 30-120 Hz level is this far under the reference
    floor_db: float = 20.0         # dropped anywhere when this far under the reference
    hat_ms: float = 10.0           # "on a hat onset"
    recover_level_db: float = 12.0  # recovered snare / tom hit: 30-120 Hz level >= reference - this
    recover_shape_db: float = 10.0  # ... 30-120 Hz over 150-400 Hz (a kick's spectrum)
    recover_rise_db: float = 6.0    # ... 30-120 Hz rise
    tom_decay_db: float = 10.0      # toms only: 30-120 Hz drop from the first 30 ms to 80-110 ms (a floor tom rings)
    layered_level_db: float = 10.0  # snare stem, not kick-shaped: a kick-level 30-120 Hz burst (>= reference - this) that
    #                                 hits.kick confirms within merge_ms is a kick layered under the snare (a row is added)
    merge_ms: float = 30.0          # a recovered hit next to a kept kick is the same stroke; toms need a mix kick this close


@dataclass(frozen=True)
class SourceParams:
    tol_ms: float = 30.0            # agreement tolerance (UD2)
    vel_median_min: float = 0.3     # check: median kick vel (bleed rows are faint: MEGAFAUNA's raw stem 0.14)
    fast_gap_max: float = 0.25      # check: share of inter-kick gaps < fast_gap_s (32nd-hat bleed: MEGAFAUNA's raw stem 0.43)
    fast_gap_s: float = 0.1
    kept_min: float = 0.4           # check: share of the kick-stem candidate rows the gate kept
    agree_low: float = 0.75         # QA flag when min(mix_in_drums, drums_in_mix) is below this
    # W4A-ACAP: a separated drum stem without a single kick. The mix kick replaces it only when it is a real kick track
    # (>= mix_min_n events and >= mix_min_per_min per minute); otherwise agents get no kicks (an a cappella's plosives
    # must not become a kick timeline). The QA flag needs >= flag_min_n mix events.
    mix_min_n: int = 8
    mix_min_per_min: float = 4.0
    flag_min_n: int = 3


@dataclass
class LowFeat:
    level_db: float   # 30-120 Hz mean power, 30 ms after the onset (dBFS)
    rise_db: float    # ... minus the mean power of the 45-5 ms before
    body_db: float    # 150-400 Hz mean power, 30 ms after the onset
    decay_db: float   # 30-120 Hz: first 30 ms minus 80-110 ms


def _band(x: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    from scipy import signal

    nyq = sr / 2.0
    sos = signal.butter(4, [lo / nyq, min(hi, 0.95 * nyq) / nyq], btype="bandpass", output="sos")
    return signal.sosfiltfilt(sos, np.asarray(x, dtype=np.float64))


def _win_db(y2c: np.ndarray, sr: int, t: float, a: float, b: float) -> float:
    """Mean power (dB) of the signal whose squared cumulative sum is ``y2c`` over [t + a, t + b) seconds."""
    n = y2c.size - 1
    i0 = int(np.clip(round((t + a) * sr), 0, n))
    i1 = int(np.clip(round((t + b) * sr), 0, n))
    if i1 <= i0:
        return -140.0
    return float(10.0 * np.log10(max((y2c[i1] - y2c[i0]) / (i1 - i0), 1e-14)))


def _cum2(y: np.ndarray) -> np.ndarray:
    return np.concatenate(([0.0], np.cumsum(y * y)))


def low_features(x: np.ndarray, sr: int, times: Sequence[float]) -> list[LowFeat]:
    """30-120 Hz level / rise / decay and 150-400 Hz level of a (mono) sub-stem at each onset time."""
    if not len(times):
        return []
    m = np.asarray(x, dtype=np.float64)
    if m.ndim == 2:
        m = m.mean(axis=0)
    lo = _cum2(_band(m, sr, *KICK_BAND))
    bo = _cum2(_band(m, sr, *BODY_BAND))
    out = []
    for t in times:
        lv = _win_db(lo, sr, t, 0.0, 0.03)
        # mean power of the 45-5 ms before (the loudest 5 ms of it was tried: it drops real kicks re-struck on a long
        # 808 tail on Newton / Versatile; ticks on a kick's tail are masked by the onset detector already)
        out.append(LowFeat(level_db=lv, rise_db=lv - _win_db(lo, sr, t, -0.045, -0.005), body_db=_win_db(bo, sr, t, 0.0, 0.03),
                           decay_db=lv - _win_db(lo, sr, t, 0.08, 0.11)))
    return out


def _near(arr: np.ndarray, t: float, tol: float) -> bool:
    if arr.size == 0:
        return False
    j = int(np.searchsorted(arr, t))
    return any(abs(float(arr[k]) - t) <= tol for k in (j - 1, j) if 0 <= k < arr.size)


def gate_kicks(hits: list[Hit], subs: Mapping[str, np.ndarray], sr: int, prm: KickGateParams = KickGateParams(),
               mix_kicks: Sequence[float] = ()) -> tuple[list[Hit], dict[str, Any]]:
    """The kick quality gate and the recovery of mislabelled low hits (see the module doc). Returns (hits, stats);
    stats["low_rise_share"] is the share of kick-stem candidates whose low band rises."""
    kick_rows = [h for h in hits if h.drum == "kick" and h.sub_stem == "kick"]
    stats: dict[str, Any] = {"candidates": len(kick_rows), "dropped": {"no_low_rise": 0, "on_hat_quiet": 0, "faint": 0},
                             "recovered": {"snare": 0, "toms": 0}, "ref_db": None, "low_rise_share": None}
    if "kick" not in subs or not kick_rows:
        return hits, stats
    raw_t = np.array(sorted(h.t for h in kick_rows))
    stats["raw_fast_gap_share"] = round(float(np.mean(np.diff(raw_t) < 0.1)), 3) if raw_t.size > 1 else None
    feats = low_features(subs["kick"], sr, [h.t for h in kick_rows])
    lv = np.array([f.level_db for f in feats])
    ref = float(np.percentile(lv, prm.ref_pct))
    stats["ref_db"] = round(ref, 2)
    stats["low_rise_share"] = round(float(np.mean([f.rise_db >= prm.rise_min_db for f in feats])), 3)
    hats = np.array(sorted(h.t for h in hits if h.drum == "hat"))
    drop: set[int] = set()
    for h, f in zip(kick_rows, feats):
        reason = None
        if f.rise_db < prm.rise_min_db:
            reason = "no_low_rise"
        elif f.level_db < ref - prm.floor_db:
            reason = "faint"
        elif f.level_db < ref - prm.quiet_db and _near(hats, h.t, prm.hat_ms / 1000.0):
            reason = "on_hat_quiet"
        if reason:
            stats["dropped"][reason] += 1
            drop.add(id(h))
        else:
            h.evidence.append("low_band_rise")
    out = [h for h in hits if id(h) not in drop]
    kept_t = np.array(sorted(h.t for h in out if h.drum == "kick"))
    mix_t = np.array(sorted(float(t) for t in mix_kicks))
    tol = prm.merge_ms / 1000.0
    added: list[Hit] = []
    for sub in ("snare", "toms"):
        rows = [h for h in out if h.sub_stem == sub and h.drum in ("snare", "tom")]
        if sub not in subs or not rows:
            continue
        for h, f in zip(rows, low_features(subs[sub], sr, [h.t for h in rows])):
            if f.rise_db < prm.recover_rise_db or _near(kept_t, h.t, tol):
                continue
            kick_shaped = f.level_db >= ref - prm.recover_level_db and f.level_db - f.body_db >= prm.recover_shape_db
            if sub == "toms":
                if kick_shaped and f.decay_db >= prm.tom_decay_db and _near(mix_t, h.t, tol):
                    h.drum = "kick"
                    h.evidence.append("recovered_from_toms_low_band")
                    stats["recovered"]["toms"] += 1
                continue
            if kick_shaped:
                # the snare stem's hit IS a kick (bass-dominant by >= recover_shape_db: no snare is)
                h.drum = "kick"
                h.evidence.append("recovered_from_snare_low_band")
                stats["recovered"]["snare"] += 1
            elif f.level_db >= ref - prm.layered_level_db and _near(mix_t, h.t, tol):
                # a kick layered under the snare in the snare stem: a kick-level 30-120 Hz burst that the mix's low band
                # also shows as a kick; the snare row stays, a kick row is added at the same onset
                k = Hit(t=h.t, sample=h.sample, drum="kick", level_db=h.level_db, peak=h.peak, rise_db=f.rise_db, conf=h.conf,
                        source=h.source, sub_stem=h.sub_stem, evidence=["recovered_layered_from_snare_low_band", "mix_kick_agrees"])
                added.append(k)
                stats["recovered"]["snare_layered"] = stats["recovered"].get("snare_layered", 0) + 1
    out = out + added
    return out, stats


def agreement(a: Sequence[float], b: Sequence[float], tol: float) -> float | None:
    """Share of the times in ``a`` with a time of ``b`` within ``tol`` (None when ``a`` is empty)."""
    aa = np.sort(np.asarray(a, dtype=np.float64))
    bb = np.sort(np.asarray(b, dtype=np.float64))
    if aa.size == 0:
        return None
    if bb.size == 0:
        return 0.0
    j = np.searchsorted(bb, aa)
    d = np.full(aa.size, np.inf)
    for k in (j - 1, j):
        ok = (k >= 0) & (k < bb.size)
        d[ok] = np.minimum(d[ok], np.abs(bb[k[ok]] - aa[ok]))
    return float(np.mean(d <= tol + 1e-9))


def _r(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(float(x), n)


def choose_source(path: str, kicks: Sequence[Hit], gate: Mapping[str, Any] | None, mix: Sequence[Mapping[str, Any]] | None,
                  prm: SourceParams = SourceParams(), duration_s: float | None = None) -> dict[str, Any]:
    """Reliability of the two kick timelines and the agent-facing choice (the ``kick`` block of meta/drums.json).

    ``path``: the drums path (drumsep | classifier | none); ``kicks``: the final kick rows (vel set); ``gate``: the gate
    stats (DrumSep path); ``mix``: the hits.kick items (None when spectral has no kick events file)."""
    kt = np.array(sorted(h.t for h in kicks))
    vel = np.array([h.vel for h in kicks])
    mix_t = [float(i["t"]) for i in (mix or [])]
    tol = prm.tol_ms / 1000.0
    gaps = np.diff(kt)
    drums: dict[str, Any] = {
        "path": path, "n": int(kt.size),
        "vel_median": _r(float(np.median(vel))) if vel.size else None,
        "fast_gap_share": _r(float(np.mean(gaps < prm.fast_gap_s))) if gaps.size else None,
    }
    if gate:
        cand = int(gate.get("candidates") or 0)
        rec = sum((gate.get("recovered") or {}).values())
        drums["candidates"] = cand
        drums["kept_share"] = _r((kt.size - rec) / cand) if cand else None
        drums["low_rise_share"] = gate.get("low_rise_share")
        drums["raw_fast_gap_share"] = gate.get("raw_fast_gap_share")
        drums["dropped"] = dict(gate.get("dropped") or {})
        drums["recovered"] = dict(gate.get("recovered") or {})
    mixd: dict[str, Any] = {"n": len(mix_t)}
    if mix:
        conf = [float(i["kick_conf"]) for i in mix if isinstance(i.get("kick_conf"), (int, float))]
        if conf:
            mixd["kick_conf_median"] = _r(float(np.median(conf)))
    agree = {"tol_ms": prm.tol_ms, "mix_in_drums": _r(agreement(mix_t, kt, tol)), "drums_in_mix": _r(agreement(kt, mix_t, tol))}
    vals = [v for v in (agree["mix_in_drums"], agree["drums_in_mix"]) if v is not None]
    agree["min"] = min(vals) if len(vals) == 2 else None
    stem_kickless = path != "none" and kt.size == 0
    if stem_kickless and len(mix_t) >= prm.flag_min_n:
        # W4A-ACAP: the drum stem was separated and holds no kick while the mix shows kick events: the two timelines
        # disagree completely (before, drums_in_mix = None hid it and no QA flag was raised)
        agree["min"] = agree["mix_in_drums"]
    agree["low"] = bool(agree["min"] is not None and agree["min"] < prm.agree_low)
    agree["threshold"] = prm.agree_low

    fails: list[str] = []
    if path == "none":
        fails.append("no drum stem")
    elif kt.size == 0:
        fails.append("no kick in the drum stems")
    else:
        if drums["vel_median"] is not None and drums["vel_median"] < prm.vel_median_min:
            fails.append(f"median kick vel {drums['vel_median']} < {prm.vel_median_min}")
        if drums["fast_gap_share"] is not None and drums["fast_gap_share"] > prm.fast_gap_max:
            fails.append(f"{drums['fast_gap_share']:.0%} of the kick gaps < {int(prm.fast_gap_s * 1000)} ms (hat-grid bleed)")
        if drums.get("kept_share") is not None and drums["kept_share"] < prm.kept_min:
            fails.append(f"the bleed gate kept only {drums['kept_share']:.0%} of the kick-stem onsets")
    drums["checks_failed"] = fails
    per_min = len(mix_t) / max(1e-9, duration_s / 60.0) if duration_s else None
    mix_is_kick_track = len(mix_t) >= prm.mix_min_n and (per_min is None or per_min >= prm.mix_min_per_min)
    if stem_kickless and not mix_is_kick_track:
        # a separated drum stem with no kick and only a few mix 'kicks' (plosives, bass onsets): no agent kicks
        source = "drums"
        reason = (f"the drum stem ({path}) holds no kick and the mix shows only {len(mix_t)} unconfirmed kick event(s) "
                  f"(< {prm.mix_min_n}, or < {prm.mix_min_per_min:g}/min): no agent-facing kicks")
        return {"kick_source": source, "reason": reason, "drums": drums, "mix": mixd, "agreement": agree}
    if not fails:
        source = "drums"
        reason = f"drum-stem kick ({path}) passes the quality check"
        if agree["low"]:
            reason += f"; the mix low band agrees only {agree['min']:.0%} (sidechain / masking: the stem is preferred)"
    elif mix_t:
        source = "mix"
        reason = "drum-stem kick rejected: " + "; ".join(fails) + " -> hits.kick from the mix (lower quality)"
    else:
        source = "drums" if path != "none" else "mix"
        reason = "; ".join(fails) + "; the mix has no kick events either"
    return {"kick_source": source, "reason": reason, "drums": drums, "mix": mixd, "agreement": agree}
