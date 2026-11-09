"""spectral stage: run(ctx). The DSP lives in ``dsp.py`` (pure functions, unit-tested on synthetic signals)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from mvh.runner.spec import StageResult

from . import dsp

HIT_BANDS = {
    # name: (energy source, refinement envelope, physical dB channel for the event's ``db``)
    "kick": ("kick", "low", "bands.kick_db"),
    "mid": ("mid", "mid", "bands.mid_db"),
    "high": ("high", "high", "bands.high_db"),
}
ONSET_ENV = {"bass": "low", "mid": "mid", "high": "high"}


def _r(x: float, nd: int = 6) -> float:
    return float(round(float(x), nd))


def _kick_gate(kick_viz_db: np.ndarray, peak_db: float, p: dict[str, Any]) -> tuple[float, str]:
    """Kick gate (dB of the viz kick band): ``max(p95 - gate_rel_db, gate_db - shortfall)`` with
    ``shortfall = max(0, gate_margin_db_ref - peak_dBFS)``.

    For a normal or loud master (sample peak above -6 dBFS) this is the plan's ``max(-46, p95 - 30)``. A quiet master
    is recognised from the overall level (sample peak), never from the kick band itself (a kick-free song would
    otherwise lower the gate to its noise floor), and viz's absolute gate is lowered by the shortfall."""
    live = kick_viz_db[kick_viz_db > -199.0]
    if live.size == 0:
        return float(p["gate_db"]), "absolute"
    p95 = float(np.percentile(live, 95))
    rel = p95 - float(p["gate_rel_db"])
    shortfall = max(0.0, -float(p["gate_margin_db"]) - peak_db)
    absg = float(p["gate_db"]) - shortfall
    g = max(rel, absg)
    mode = "relative" if g == rel and rel > absg else ("absolute" if shortfall == 0 else "quiet-master")
    return g, mode


def run(ctx) -> StageResult:
    p = dict(ctx.params)
    audio = ctx.audio("mix")
    x = np.asarray(audio.samples, dtype=np.float64)
    sr = int(audio.sr)
    if x.ndim == 1:
        x = x[None, :]
    warnings: list[str] = []
    notes: list[str] = []
    if x.shape[0] > 2:
        warnings.append(f"{x.shape[0]} channels: spectral uses the first two (L, R)")
    L = x[0]
    R = x[1] if x.shape[0] > 1 else x[0]
    mono = 0.5 * (L + R)

    ctx.log.info("spectral: STFT pass (%d samples at %d Hz)", L.size, sr)
    fr = dsp.analyse_frames(x[:2], sr)
    bm = dsp.band_map(sr, fr.n_fft)
    vv = dsp.viz_values(fr, bm)
    n = fr.t.size
    live = fr.total_ms > 1e-12

    ctx.log.info("spectral: 400 Hz refinement envelopes")
    envs = {b: dsp.env_db(dsp.band_envelope(mono, sr, *dsp.REFINE_BANDS[b])) for b in dsp.REFINE_BANDS}
    scores = {b: dsp.onset_score(envs, b) for b in ("low", "mid", "high")}

    ch: dict[str, np.ndarray] = {}
    meta: dict[str, dict[str, Any]] = {}

    def twin(cid: str, db: np.ndarray, floor: float = dsp.DB_FLOOR) -> None:
        ch[cid + "_db"] = np.maximum(db, floor)
        v, lo, hi = dsp.pnorm(db, floor=floor)
        ch[cid] = v
        meta[cid] = {"norm": {"lo": lo, "hi": hi}}

    # ---------------------------------------------------------------- physical bands (dBFS, mean square)
    for cid, db in fr.phys_db.items():
        twin(cid, db)
    # ---------------------------------------------------------------- viz-compatible values
    for b in ("bass", "mid", "high"):
        ch[f"bands.{b}_viz"] = np.clip(vv.smooth[b], 0.0, 1.0)
    ch["bands.level"] = np.clip(vv.level, 0.0, 1.0)

    # ---------------------------------------------------------------- hit envelopes and events
    gate_db, gate_mode = _kick_gate(fr.kick_viz_db, 20.0 * math.log10(max(float(np.max(np.abs(x))), 1e-9)), p)
    hit_summary: dict[str, Any] = {}
    shifts: dict[str, int] = {}
    for name, (src, env_band, db_ch) in HIT_BANDS.items():
        e = vv.kick_e if src == "kick" else vv.energy[src]
        hr = dsp.hit_envelope(
            e,
            gate_db=gate_db if name == "kick" else None,
            threshold=float(p["hit_threshold"]),
            release_s=float(p["hit_release_s"]),
            median_ref_s=float(p["median_ref_s"]),
        )
        kick_ev: list[dsp.KickEvidence] = []
        if name == "kick":
            kp = {k: float(p[f"kick_{k}"]) for k in dsp.KICK_DEFAULTS if f"kick_{k}" in p}
            pairs = dsp.select_kick_events(hr, mono, sr, kp)
            events = [h for h, _ in pairs]
            kick_ev = [e for _, e in pairs]
        else:
            events = dsp.select_hit_events(
                hr, scores[env_band], envs[env_band], x_min=float(p["event_x_min"]),
                viz_rise_db=float(p["event_rise_db"]), weak_rise_db=float(p["event_weak_rise_db"]),
            )
        raw, released, shift = dsp.aligned_envelopes(hr, events, float(p["hit_release_s"]))
        shifts[name] = shift
        ch[f"hits.{name}"] = np.clip(released, 0.0, 1.5)
        ch[f"hits.{name}_raw"] = np.clip(raw, 0.0, 1.5)
        band_db = ch[db_ch]
        items = []
        for h in events:
            a = max(0, int(math.floor(h.t * dsp.RATE)))
            z = min(n - 1, int(math.ceil(h.t_peak * dsp.RATE)) + 1)
            items.append(
                {
                    "t": _r(h.t),
                    "t_peak": _r(h.t_peak),
                    "strength": _r(min(h.x, float(p["strength_cap"])), 4),
                    "db": _r(float(np.max(band_db[a : z + 1])) if z >= a else float(band_db[min(a, n - 1)]), 2),
                    "env": _r(h.v, 4),
                    "rise_db": _r(h.rise_db, 2),
                    "viz": bool(h.viz_hit),
                }
            )
            if name == "kick":
                items[-1]["kick_conf"] = kick_ev[len(items) - 1].conf()
        ctx.writer.events(
            f"hits.{name}",
            items,
            fields={
                "env": {"unit": "0..1", "type": "number", "description": "hit envelope value at the hit (hits.<band> flash)"},
                "rise_db": {"unit": "dB", "type": "number",
                            "description": ("onset score: ripple-robust dB step of the 90-200 Hz band + half the 1.5-5 kHz click step"
                                            if name == "kick" else "onset score: dB step of the 400 Hz band (+ click) envelope")},
                **({"kick_conf": {"unit": "0..1", "type": "number",
                                  "description": "drum-kick evidence: swept attack (burst, pitch drop, click), acoustic body "
                                                 "(30-150 Hz onset decaying within 90 ms) or beater click on a low-band onset; "
                                                 "bass notes, snares and vocals read low"}}
                   if name == "kick" else {}),
                "viz": {"unit": None, "type": "boolean",
                        "description": "viz's causal one-hit-per-note logic registers this hit too"},
            },
        )
        dur = max(L.size / sr, 1e-9)
        hit_summary[name] = {
            "n": len(items),
            "per_min": round(60.0 * len(items) / dur, 1),
            "viz_hits": int(sum(1 for h in events if h.viz_hit)),
            **({"routes": {r: int(sum(1 for e in kick_ev if e.route == r)) for r in dsp.KICK_ROUTES}} if name == "kick" else {}),
            "lag_frames": shift,
        }

    # ---------------------------------------------------------------- flux and onsets
    onset_summary: dict[str, int] = {}
    for b in ("bass", "mid", "high"):
        flux = dsp.band_flux(vv.norm, bm.ranges[f"flux_{b}"])
        res = dsp.flux_onsets(flux, vv.smooth[b], b, window_s=float(p["onset_window_s"]))
        v, lo, hi = dsp.pnorm(flux)
        ch[f"flux.{b}"] = v
        meta[f"flux.{b}"] = {"norm": {"lo": lo, "hi": hi}}
        edb = envs[ONSET_ENV[b]]
        sc = scores[ONSET_ENV[b]]
        refined: list[tuple[float, float]] = []
        lags = []
        pend = []
        for it in res.items:
            tk = it["i"] / dsp.RATE
            r = dsp.refine_onset(sc, edb, tk - float(p["onset_search_before_s"]), tk + float(p["onset_search_after_s"]))
            if r is not None and r[2] >= float(p["onset_rise_db"]):
                refined.append((r[0], it["strength"]))
                lags.append(tk - r[0])
            else:
                pend.append((tk, it["strength"]))
        lag = float(np.median(lags)) if lags else 0.0
        refined += [(tk - lag, s) for tk, s in pend]
        refined.sort()
        items = []
        gap = dsp.ONSET_GAP_S[b] * 0.5
        for t, s in refined:
            if items and t - items[-1]["t"] < gap:
                if s > items[-1]["strength"]:
                    items[-1] = {"t": _r(max(t, 0.0)), "strength": _r(s, 4)}
                continue
            items.append({"t": _r(max(t, 0.0)), "strength": _r(s, 4)})
        ctx.writer.events(f"onsets.{b}", items)
        onset_summary[b] = len(items)

    # ---------------------------------------------------------------- timbre and stereo
    cen = np.where(live, fr.centroid_hz, 0.0)
    rol = np.where(live, fr.rolloff_hz, 0.0)
    ch["timbre.centroid_hz"] = cen
    v, lo, hi = dsp.pnorm(cen, floor=0.0)
    ch["timbre.centroid"] = v
    meta["timbre.centroid"] = {"norm": {"lo": lo, "hi": hi}}
    ch["timbre.rolloff_hz"] = rol
    v, lo, hi = dsp.pnorm(rol, floor=0.0)
    ch["timbre.rolloff"] = v
    meta["timbre.rolloff"] = {"norm": {"lo": lo, "hi": hi}}
    ch["timbre.flatness"] = np.where(live, fr.flatness, 0.0)
    ch["timbre.slope_db_oct"] = dsp.spectral_slope(fr.log_band_db, bm.centres_hz, live=live)
    ch["stereo.width"] = fr.width
    ch["stereo.balance"] = fr.balance
    ch["stereo.correlation"] = fr.correlation

    for k in list(ch):
        a = np.asarray(ch[k], dtype=np.float64)
        if a.size != n or not np.all(np.isfinite(a)):
            raise ValueError(f"spectral: channel {k} has {a.size} frames or non-finite values")
        ch[k] = a.astype(np.float32)
    ctx.writer.curves("core", ch, meta=meta)

    # ---------------------------------------------------------------- spectrum128 (viz bands, u8)
    spec = np.round(255.0 * np.clip(vv.bands, 0.0, 1.0)).astype(np.uint8)
    ctx.writer.matrix(
        "spectrum128",
        spec,
        meta={
            "band_edges_hz": [float(e) for e in bm.edges_hz],
            "gain": round(vv.gain, 6),
            "fft_size": fr.n_fft,
            "db_range": [dsp.MIN_DB, dsp.MAX_DB],
            "tilt_db_per_oct": dsp.TILT_DB_PER_OCT,
        },
    )

    # ---------------------------------------------------------------- summary / provenance
    quiet = int(np.sum(~live))
    if gate_mode == "quiet-master":
        warnings.append(f"quiet master: kick gate set relative to the song ({gate_db:.1f} dB) instead of viz's -46 dB")
    notes += [
        "offline non-causal port of viz/js/audio.js (centred 100 Hz frames, Web Audio Blackman, |X|/N, mono down-mix)",
        f"per-song viz gain {vv.gain:.4f} replaces the 6 s AGC (p99.5 of the per-frame band maximum -> 0.95)",
        f"hit reference: centred +-{float(p['median_ref_s']):g} s median of attack sizes; kick gate {gate_db:.1f} dB ({gate_mode})",
        "mid/high hit events: viz attacks (v > 0.3, re-arm ignored) or weaker attacks (x >= event_x_min) with a crisp onset, "
        "timed on 400 Hz zero-phase band envelopes (steepest dB rise); kick events: low-band onsets judged on kick evidence "
        "(routes: swept attack = 90-250 Hz burst + pitch drop of the added 30-160 Hz energy or a 1.5-5 kHz click; sidechain duck; "
        "acoustic body = 30-150 Hz onset decaying within 90 ms; clicky body over a bass; 808; roll), no refractory, faint "
        "thumps judged against the local mix level; envelopes shifted by the median lag "
        f"(frames kick/mid/high = {shifts['kick']}/{shifts['mid']}/{shifts['high']}) and flashed at each onset",
        "band dBFS = 10 log10(mean square) of mid + side (a full-scale sine reads -3.01 dBFS); viz values use the mid only",
    ]
    summary = {
        "viz_gain": round(vv.gain, 4),
        "fft_size": fr.n_fft,
        "kick_gate_db": round(gate_db, 2),
        "hits": hit_summary,
        "onsets": onset_summary,
        "centroid_median_hz": round(float(np.median(cen[live])) if live.any() else 0.0, 1),
        "width_median": round(float(np.median(fr.width[live])) if live.any() else 0.0, 3),
        "silent_frames": quiet,
    }
    conf = 0.9 if hit_summary["kick"]["n"] or hit_summary["mid"]["n"] else 0.6
    return StageResult(
        status="ok",
        summary=summary,
        warnings=warnings,
        provenance={"notes": notes, "method": {"gate_mode": gate_mode, "envelope_shift_frames": shifts}},
        confidence=conf,
    )
